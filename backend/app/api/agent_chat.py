"""Unified Agent Chat: SSE streaming endpoint with LLM tool-calling loop.

POST /api/v1/agent/chat-stream — multi-round agent with observable pipeline events.

Event schema (every event carries these top-level fields):
    run_id      — unique ID for this agent run
    step_id     — monotonic step counter
    event       — event type (step / tool_call / tool_result / answer / error / done)
    tool_name   — tool being called (empty for non-tool steps)
    elapsed_ms  — wall-clock ms since run start
    status      — running | success | error
    data        — event-type-specific payload
"""

import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.agent.tools import execute_tool, get_openai_tools
from app.api.dependencies import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.observability.agent_metrics import record_agent_failure, record_agent_run
from app.observability.agent_metrics import record_tool_call as record_tool_metric
from app.services.agent_llm_client import AgentLLMClient
from app.services.memory_search import preload_memories
from app.services.prompt_guard import guard_wrap
from app.services.skill_matcher import match_skill_for_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["Agent Chat"])


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="用户消息")
    conversation_history: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="历史消息列表 [{role, content}]，用于多轮上下文",
    )


SYSTEM_PROMPT = """你是一个智能穿搭助手。你可以帮助用户管理衣橱、查看天气、推荐搭配、根据情绪推荐穿搭风格等。

你有以下工具可以使用：
- list_wardrobe: 查看用户的衣橱列表
- search_wardrobe: 按条件搜索衣橱单品
- get_weather: 查询城市天气信息
- recommend_outfits: 根据单品推荐搭配方案
- mood_recommend: 根据情绪推荐穿搭风格和颜色
- list_mood_types: 查看所有支持的情绪类型
- search_memory: 搜索用户的穿搭记忆/笔记
- add_memory: 保存用户的穿搭记忆/笔记
- list_collections: 查看用户的套装收藏

使用规则：
1. 优先使用工具获取真实数据，不要编造信息
2. 如果用户问衣橱相关问题，先用 list_wardrobe 或 search_wardrobe
3. 如果用户问天气，用 get_weather
4. 如果用户想要搭配推荐，用 recommend_outfits
5. 如果用户提到心情/情绪，用 mood_recommend
6. 回答要简洁、友好、实用
7. 用中文回答"""


# ── SSE event builder ───────────────────────────────────────────────────────


def _agent_event(
    event_type: str,
    *,
    run_id: str,
    step_id: int,
    tool_name: str = "",
    elapsed_ms: int = 0,
    status: str = "running",
    data: Any = None,
) -> str:
    """Build a structured SSE event string."""
    payload: Dict[str, Any] = {
        "run_id": run_id,
        "step_id": step_id,
        "event": event_type,
        "tool_name": tool_name,
        "elapsed_ms": elapsed_ms,
        "status": status,
    }
    if data is not None:
        payload["data"] = data
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _ms_since(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


def _agent_llm_config_error(api_base: str, api_key: str) -> Optional[str]:
    """Return an actionable error when the Agent LLM is not configured."""
    base = (api_base or "").strip()
    key = (api_key or "").strip()
    if not base:
        return (
            "AI 助手尚未配置模型接口。请在 backend/.env 中设置 "
            "AI_RECOMMENDER_API_BASE_URL、AI_RECOMMENDER_API_KEY 和 AI_RECOMMENDER_MODEL。"
        )
    if not base.startswith(("http://", "https://")):
        return "AI_RECOMMENDER_API_BASE_URL 必须以 http:// 或 https:// 开头。"
    if not key:
        return "AI 助手尚未配置 API Key。请在 backend/.env 中设置 AI_RECOMMENDER_API_KEY。"
    return None


# ── Agent loop ──────────────────────────────────────────────────────────────


async def _run_agent_loop(
    *,
    user_message: str,
    conversation_history: Optional[List[Dict]],
    db: Session,
    user_id: str,
) -> AsyncGenerator[str, None]:
    """Wrapper that iterates _agent_loop_inner and records metrics + persists the run."""
    run_state: Dict[str, Any] = {
        "run_id": uuid.uuid4().hex[:12],
        "outcome": "failure",
        "total_rounds": 0,
        "total_tokens": 0,
        "skill_id": None,
    }
    run_tool_calls: List[Dict[str, Any]] = []
    t_start = time.monotonic()

    try:
        async for event in _agent_loop_inner(
            user_message=user_message,
            conversation_history=conversation_history,
            db=db,
            user_id=user_id,
            _run_tool_calls=run_tool_calls,
            _run_state=run_state,
        ):
            yield event
        # If we reach here without explicit return, outcome stays as set by inner
    finally:
        latency_ms = int((time.monotonic() - t_start) * 1000)
        # Determine outcome from the last event or error state
        total_calls = len(run_tool_calls)
        record_agent_run(
            outcome=str(run_state["outcome"]),
            latency_ms=latency_ms,
            total_rounds=int(run_state["total_rounds"]),
            total_tool_calls=total_calls,
            total_tokens=int(run_state["total_tokens"]),
        )
        for tc in run_tool_calls:
            record_tool_metric(
                tc.get("tool_name", ""), tc.get("outcome", "failure"), tc.get("latency_ms", 0)
            )

        # Persist to DB
        try:
            from app.models.agent_run import AgentRun

            run_row = AgentRun(
                run_id=str(run_state["run_id"]),
                user_id=user_id,
                message=user_message[:2000],
                outcome=str(run_state["outcome"]),
                total_rounds=int(run_state["total_rounds"]),
                total_tool_calls=total_calls,
                total_tokens=int(run_state["total_tokens"]),
                latency_ms=latency_ms,
                failure_reason=(
                    str(run_state["outcome"]) if run_state["outcome"] != "success" else None
                ),
                tool_calls_log=run_tool_calls or None,
                skill_id=run_state.get("skill_id"),
            )
            db.add(run_row)
            db.commit()
        except Exception as e:
            logger.warning("Failed to persist agent run: %s", e)


async def _agent_loop_inner(
    *,
    user_message: str,
    conversation_history: Optional[List[Dict]],
    db: Session,
    user_id: str,
    _run_tool_calls: List[Dict[str, Any]],
    _run_state: Dict[str, Any],
) -> AsyncGenerator[str, None]:
    max_rounds = settings.AGENT_MAX_ROUNDS
    timeout_sec = settings.AGENT_TIMEOUT_SECONDS
    token_budget = settings.AGENT_TOTAL_TOKEN_BUDGET
    max_tool_calls = settings.AGENT_MAX_TOOL_CALLS

    tools_openai = get_openai_tools()

    model = settings.AGENT_MODEL or settings.AI_RECOMMENDER_MODEL
    if not model:
        model = "gpt-4o-mini"

    run_id = str(_run_state["run_id"])
    step_id = 0
    total_tokens = 0
    total_tool_calls = 0
    round_num = 0
    t0 = time.monotonic()

    config_error = _agent_llm_config_error(
        settings.AI_RECOMMENDER_API_BASE_URL,
        settings.AI_RECOMMENDER_API_KEY,
    )
    if config_error:
        step_id += 1
        yield _agent_event(
            "error",
            run_id=run_id,
            step_id=step_id,
            elapsed_ms=_ms_since(t0),
            status="error",
            data={"message": config_error},
        )
        _run_state["outcome"] = "configuration_error"
        record_agent_failure("configuration_error")
        return

    llm = AgentLLMClient(
        api_base=settings.AI_RECOMMENDER_API_BASE_URL,
        api_key=settings.AI_RECOMMENDER_API_KEY,
        model=model,
        timeout_seconds=min(timeout_sec, 30.0),
    )

    safe_user_msg = guard_wrap(user_message, field_name="user_message")

    # ── Skill matching ──
    matched_skill, matched_keywords = match_skill_for_message(safe_user_msg, db, str(user_id))
    system_prompt = SYSTEM_PROMPT
    if matched_skill:
        system_prompt += "\n\n" + matched_skill.system_prompt_addon
        _run_state["skill_id"] = str(matched_skill.skill_id)
        step_id += 1
        yield _agent_event(
            "skill_execution",
            run_id=run_id,
            step_id=step_id,
            elapsed_ms=int((time.monotonic() - t0) * 1000),
            status="success",
            data={
                "skill_id": str(matched_skill.skill_id),
                "skill_name": matched_skill.name,
                "version": matched_skill.active_version,
                "matched_keywords": matched_keywords,
            },
        )

    # ── Memory preload ──
    memory_context = await preload_memories(
        safe_user_msg, db, str(user_id), settings.MEMORY_PRELOAD_TOP_K
    )
    if memory_context:
        system_prompt += "\n\n" + memory_context

    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    if conversation_history:
        for msg in conversation_history[-20:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": safe_user_msg})

    # ── stream_start (backwards compat + new fields) ──
    step_id += 1
    yield _agent_event(
        "step",
        run_id=run_id,
        step_id=step_id,
        elapsed_ms=0,
        status="running",
        data={"label": "正在分析你的需求", "max_rounds": max_rounds},
    )

    while round_num < max_rounds:
        elapsed_sec = time.monotonic() - t0
        if elapsed_sec > timeout_sec:
            yield _agent_event(
                "error",
                run_id=run_id,
                step_id=step_id,
                elapsed_ms=_ms_since(t0),
                status="error",
                data={"message": f"Agent 超时（{timeout_sec:.0f}s）"},
            )
            _run_state["outcome"] = "timeout"
            _run_state["total_rounds"] = round_num
            _run_state["total_tokens"] = total_tokens
            record_agent_failure("timeout")
            return

        if total_tokens >= token_budget:
            yield _agent_event(
                "error",
                run_id=run_id,
                step_id=step_id,
                elapsed_ms=_ms_since(t0),
                status="error",
                data={"message": f"Token 预算已用尽（{token_budget}）"},
            )
            _run_state["outcome"] = "failure"
            _run_state["total_rounds"] = round_num
            _run_state["total_tokens"] = total_tokens
            record_agent_failure("token_budget")
            return

        round_num += 1
        _run_state["total_rounds"] = round_num

        # ── thinking step ──
        step_id += 1
        yield _agent_event(
            "step",
            run_id=run_id,
            step_id=step_id,
            elapsed_ms=_ms_since(t0),
            status="running",
            data={"label": f"第 {round_num} 轮思考中", "round": round_num},
        )

        try:
            response = await llm.chat_completion(
                messages=messages,
                tools=tools_openai if tools_openai else None,
                temperature=0.3,
            )
        except Exception as e:
            logger.error("LLM call failed in round %d: %s", round_num, e)
            yield _agent_event(
                "error",
                run_id=run_id,
                step_id=step_id,
                elapsed_ms=_ms_since(t0),
                status="error",
                data={"message": f"LLM 调用失败: {e}", "round": round_num},
            )
            _run_state["outcome"] = "failure"
            _run_state["total_rounds"] = round_num
            _run_state["total_tokens"] = total_tokens
            record_agent_failure("llm_error")
            return

        usage = response.get("usage", {})
        total_tokens += usage.get("total_tokens", 0)
        _run_state["total_tokens"] = total_tokens

        choices = response.get("choices", [])
        if not choices:
            yield _agent_event(
                "error",
                run_id=run_id,
                step_id=step_id,
                elapsed_ms=_ms_since(t0),
                status="error",
                data={"message": "LLM 返回空 choices", "round": round_num},
            )
            _run_state["outcome"] = "failure"
            _run_state["total_rounds"] = round_num
            _run_state["total_tokens"] = total_tokens
            record_agent_failure("empty_choices")
            return

        assistant_msg = choices[0].get("message", {})
        messages.append(assistant_msg)

        # ── Case 1: tool_calls ──
        if assistant_msg.get("tool_calls"):
            for tc in assistant_msg["tool_calls"]:
                total_tool_calls += 1
                if total_tool_calls > max_tool_calls:
                    yield _agent_event(
                        "error",
                        run_id=run_id,
                        step_id=step_id,
                        elapsed_ms=_ms_since(t0),
                        status="error",
                        data={"message": f"工具调用次数超限（{max_tool_calls}）"},
                    )
                    _run_state["outcome"] = "failure"
                    _run_state["total_rounds"] = round_num
                    _run_state["total_tokens"] = total_tokens
                    record_agent_failure("tool_limit")
                    return

                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                raw_args = fn.get("arguments", "{}")
                try:
                    tool_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError:
                    tool_args = {}

                # step: calling tool
                step_id += 1
                yield _agent_event(
                    "step",
                    run_id=run_id,
                    step_id=step_id,
                    tool_name=tool_name,
                    elapsed_ms=_ms_since(t0),
                    status="running",
                    data={"label": f"调用 {tool_name}", "round": round_num},
                )

                # tool_call event
                yield _agent_event(
                    "tool_call",
                    run_id=run_id,
                    step_id=step_id,
                    tool_name=tool_name,
                    elapsed_ms=_ms_since(t0),
                    status="running",
                    data={"arguments": tool_args, "round": round_num},
                )

                # execute
                _tc_start = time.monotonic()
                _tc_outcome = "success"
                try:
                    result = await execute_tool(
                        tool_name,
                        tool_args,
                        db=db,
                        user_id=user_id,
                    )
                except Exception as e:
                    result = json.dumps({"error": str(e)}, ensure_ascii=False)
                    _tc_outcome = "failure"
                _tc_latency = int((time.monotonic() - _tc_start) * 1000)
                _run_tool_calls.append(
                    {
                        "tool_name": tool_name,
                        "arguments": tool_args,
                        "result_preview": result[:500],
                        "latency_ms": _tc_latency,
                        "outcome": _tc_outcome,
                    }
                )

                # tool_result event
                truncated = len(result) > 500
                yield _agent_event(
                    "tool_result",
                    run_id=run_id,
                    step_id=step_id,
                    tool_name=tool_name,
                    elapsed_ms=_ms_since(t0),
                    status="success",
                    data={
                        "result_preview": result[:500],
                        "truncated": truncated,
                        "round": round_num,
                    },
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": result,
                    }
                )
            # continue to next round

        # ── Case 2: final text answer ──
        elif assistant_msg.get("content"):
            content = assistant_msg["content"]

            step_id += 1
            yield _agent_event(
                "step",
                run_id=run_id,
                step_id=step_id,
                elapsed_ms=_ms_since(t0),
                status="success",
                data={"label": "生成回答", "round": round_num},
            )

            yield _agent_event(
                "answer",
                run_id=run_id,
                step_id=step_id,
                elapsed_ms=_ms_since(t0),
                status="success",
                data={"content": content, "round": round_num},
            )

            yield _agent_event(
                "done",
                run_id=run_id,
                step_id=step_id,
                elapsed_ms=_ms_since(t0),
                status="success",
                data={
                    "total_rounds": round_num,
                    "total_tokens": total_tokens,
                    "total_tool_calls": total_tool_calls,
                },
            )
            _run_state["outcome"] = "success"
            _run_state["total_rounds"] = round_num
            _run_state["total_tokens"] = total_tokens
            return

        # ── Case 3: empty ──
        else:
            yield _agent_event(
                "error",
                run_id=run_id,
                step_id=step_id,
                elapsed_ms=_ms_since(t0),
                status="error",
                data={"message": "LLM 返回空响应", "round": round_num},
            )
            _run_state["outcome"] = "failure"
            _run_state["total_rounds"] = round_num
            _run_state["total_tokens"] = total_tokens
            record_agent_failure("empty_response")
            return

    # ── Max rounds exhausted — force summarization ──
    step_id += 1
    yield _agent_event(
        "step",
        run_id=run_id,
        step_id=step_id,
        elapsed_ms=_ms_since(t0),
        status="running",
        data={"label": "整理最终回答", "round": round_num},
    )

    messages.append(
        {
            "role": "user",
            "content": "根据上面收集到的信息，请直接给出最终回答。",
        }
    )
    try:
        final = await llm.chat_completion(messages=messages, tools=None, temperature=0.3)
        content = final.get("choices", [{}])[0].get("message", {}).get("content", "")

        yield _agent_event(
            "answer",
            run_id=run_id,
            step_id=step_id,
            elapsed_ms=_ms_since(t0),
            status="success",
            data={"content": content, "round": round_num, "forced_summary": True},
        )

        yield _agent_event(
            "done",
            run_id=run_id,
            step_id=step_id,
            elapsed_ms=_ms_since(t0),
            status="success",
            data={
                "total_rounds": round_num,
                "total_tokens": total_tokens,
                "total_tool_calls": total_tool_calls,
                "forced_summary": True,
            },
        )
        _run_state["outcome"] = "success"
        _run_state["total_rounds"] = round_num
        _run_state["total_tokens"] = total_tokens
    except Exception as e:
        logger.error("Final summarization failed: %s", e)
        yield _agent_event(
            "error",
            run_id=run_id,
            step_id=step_id,
            elapsed_ms=_ms_since(t0),
            status="error",
            data={"message": f"最终总结失败: {e}"},
        )
        _run_state["outcome"] = "failure"
        _run_state["total_rounds"] = round_num
        _run_state["total_tokens"] = total_tokens
        record_agent_failure("summary_error")


# ── Endpoint ────────────────────────────────────────────────────────────────


@router.post("/chat-stream")
async def agent_chat_stream(
    body: AgentChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """SSE 流式 Agent 对话：多轮工具调用 + 可观测 Pipeline 事件。

    事件格式为 Server-Sent Events：`event: <type>` + JSON `data`。
    JSON data 包含 run_id、step_id、event、tool_name、elapsed_ms、status，
    以及按事件类型变化的 data 字段。
    """
    return StreamingResponse(
        _run_agent_loop(
            user_message=body.message,
            conversation_history=body.conversation_history,
            db=db,
            user_id=str(current_user.user_id),
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
