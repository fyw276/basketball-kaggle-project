#!/usr/bin/env python3
"""Smart Outfit CLI.

Features:
- auth register/login
- wardrobe add/list
- analysis similarity/outfits/suitability
- smart-outfit: weather-by-city, upload-reference, generate
- mood: list moods, recommend
- virtual try-on (garment + person)
- outfit collections list

Implementation: stdlib argparse + httpx; default output is JSON for automation.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import httpx

CONFIG_PATH = Path.home() / ".outfit-cli" / "config.json"
DEFAULT_BASE_URL = "http://127.0.0.1:8010/api/v1"


class CLIError(Exception):
    """CLI business error."""


def ensure_config_dir() -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {"base_url": DEFAULT_BASE_URL, "token": None}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CLIError(f"Invalid config file: {CONFIG_PATH}") from exc


def save_config(config: Dict[str, Any]) -> None:
    ensure_config_dir()
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def resolve_base_url(cli_value: Optional[str], config: Dict[str, Any]) -> str:
    return (cli_value or config.get("base_url") or DEFAULT_BASE_URL).rstrip("/")


def auth_headers(token: Optional[str]) -> Dict[str, str]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def unwrap_api_envelope(payload: Any) -> Any:
    """与后端 ApiEnvelopeMiddleware / success_response 对齐，成功时返回 data。"""
    if isinstance(payload, dict) and payload.get("success") is True and "data" in payload:
        return payload["data"]
    return payload


def handle_response(resp: httpx.Response) -> Any:
    try:
        payload = resp.json()
    except Exception:
        payload = {"status_code": resp.status_code, "text": resp.text}

    if resp.status_code >= 400:
        detail = None
        if isinstance(payload, dict):
            detail = payload.get("detail") or payload.get("message") or payload.get("error")
            err = payload.get("error")
            if isinstance(err, dict) and err.get("message"):
                detail = detail or err.get("message")
        raise CLIError(f"HTTP {resp.status_code}: {detail or payload}")
    return unwrap_api_envelope(payload)


def _file_part(path: str) -> tuple[str, Any, str]:
    p = Path(path)
    if not p.exists():
        raise CLIError(f"File not found: {path}")
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return (p.name, p.open("rb"), mime)


def post_json(
    base_url: str,
    endpoint: str,
    body: Dict[str, Any],
    token: Optional[str],
    *,
    timeout: float = 60.0,
) -> Any:
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            f"{base_url}{endpoint}",
            headers={**auth_headers(token), "Content-Type": "application/json"},
            json=body,
        )
    return handle_response(resp)


def post_file(
    base_url: str,
    endpoint: str,
    file_path: str,
    token: Optional[str],
    data: Optional[Dict[str, Any]] = None,
    multi_field: Optional[str] = None,
    *,
    timeout: float = 120.0,
) -> Any:
    files = None
    opened = []
    try:
        if multi_field:
            files = []
            for p in file_path.split(","):
                part = _file_part(p.strip())
                opened.append(part[1])
                files.append((multi_field, part))
        else:
            part = _file_part(file_path)
            opened.append(part[1])
            files = {"file": part}

        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                f"{base_url}{endpoint}",
                headers=auth_headers(token),
                data=data or {},
                files=files,
            )
        return handle_response(resp)
    finally:
        for fd in opened:
            fd.close()


def get_json(
    base_url: str,
    endpoint: str,
    token: Optional[str],
    params: Optional[Dict[str, Any]] = None,
    *,
    timeout: float = 60.0,
) -> Any:
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(
            f"{base_url}{endpoint}",
            headers=auth_headers(token),
            params=params or {},
        )
    return handle_response(resp)


def post_json_public(base_url: str, endpoint: str, body: Dict[str, Any], *, timeout: float = 30.0) -> Any:
    """POST JSON without Authorization (e.g. /agent/intent)."""
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            f"{base_url}{endpoint}",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json=body,
        )
    return handle_response(resp)


def post_tryon_files(
    base_url: str,
    garment_path: str,
    person_path: str,
    token: Optional[str],
    prompt: str = "",
    model_gender: str = "neutral",
    *,
    timeout: float = 300.0,
) -> Any:
    """POST /tryon/garment — 衣物图 + 人物图。"""
    g = _file_part(garment_path)
    p = _file_part(person_path)
    opened = [g[1], p[1]]
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                f"{base_url}/tryon/garment",
                headers=auth_headers(token),
                data={
                    "prompt": prompt,
                    "model_gender": model_gender,
                },
                files={
                    "garment_file": (g[0], g[1], g[2]),
                    "person_file": (p[0], p[1], p[2]),
                },
            )
        return handle_response(resp)
    finally:
        for fd in opened:
            fd.close()


def cmd_config(args: argparse.Namespace, config: Dict[str, Any]) -> None:
    if args.base_url:
        config["base_url"] = args.base_url.rstrip("/")
    if args.token is not None:
        config["token"] = args.token
    save_config(config)
    print_json({"ok": True, "config_path": str(CONFIG_PATH), "config": config})


def cmd_register(args: argparse.Namespace, base_url: str, _: Dict[str, Any]) -> None:
    body = {
        "username": args.username,
        "email": args.email,
        "password": args.password,
        "phone_number": args.phone_number,
    }
    print_json(post_json(base_url, "/auth/register", body, token=None))


def cmd_login(args: argparse.Namespace, base_url: str, config: Dict[str, Any]) -> None:
    payload = post_json(
        base_url,
        "/auth/login",
        {"username": args.identifier, "password": args.password},
        token=None,
    )
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not token:
        raise CLIError("Login succeeded but no access_token returned")
    config["token"] = token
    save_config(config)
    print_json({"ok": True, "token_type": payload.get("token_type", "bearer")})


def cmd_wardrobe_add(args: argparse.Namespace, base_url: str, config: Dict[str, Any]) -> None:
    token = args.token or config.get("token")
    if not token:
        raise CLIError("Missing token. Run auth login first or pass --token")
    data = {
        "category": args.category,
        "main_color_name": args.main_color_name,
        "main_color_rgb": args.main_color_rgb,
        "main_color_hsv": args.main_color_hsv,
        "main_color_hex": args.main_color_hex,
        "style_tags": args.style_tags,
        "fit_type": args.fit_type or "",
        "notes": args.notes or "",
    }
    print_json(post_file(base_url, "/wardrobe/garments", args.image, token=token, data=data))


def cmd_wardrobe_list(args: argparse.Namespace, base_url: str, config: Dict[str, Any]) -> None:
    token = args.token or config.get("token")
    if not token:
        raise CLIError("Missing token. Run auth login first or pass --token")
    params = {"page": args.page, "page_size": args.page_size}
    if args.category:
        params["category"] = args.category
    print_json(get_json(base_url, "/wardrobe/garments", token=token, params=params))


def cmd_similarity(args: argparse.Namespace, base_url: str, config: Dict[str, Any]) -> None:
    token = args.token or config.get("token")
    if not token:
        raise CLIError("Missing token. Run auth login first or pass --token")
    print_json(post_file(base_url, "/analysis/similarity", args.image, token=token))


def cmd_outfits(args: argparse.Namespace, base_url: str, config: Dict[str, Any]) -> None:
    token = args.token or config.get("token")
    if not token:
        raise CLIError("Missing token. Run auth login first or pass --token")

    endpoint = f"/analysis/outfits?num_outfits={args.num_outfits}"
    if args.scene:
        endpoint += f"&scene={args.scene}"

    # multi-image upload is sent with repeated "files" field
    print_json(
        post_file(
            base_url,
            endpoint,
            file_path=",".join(args.images),
            token=token,
            multi_field="files",
        )
    )


def cmd_suitability(args: argparse.Namespace, base_url: str, config: Dict[str, Any]) -> None:
    token = args.token or config.get("token")
    if not token:
        raise CLIError("Missing token. Run auth login first or pass --token")
    print_json(post_file(base_url, "/analysis/suitability", args.image, token=token))


def cmd_weather(args: argparse.Namespace, base_url: str, config: Dict[str, Any]) -> None:
    token = args.token or config.get("token")
    if not token:
        raise CLIError("Missing token. Run auth login first or pass --token")
    print_json(
        get_json(
            base_url,
            "/smart-outfit/weather-by-city",
            token=token,
            params={"name": args.city},
        )
    )


def cmd_smart_upload(args: argparse.Namespace, base_url: str, config: Dict[str, Any]) -> None:
    token = args.token or config.get("token")
    if not token:
        raise CLIError("Missing token. Run auth login first or pass --token")
    print_json(
        post_file(
            base_url,
            "/smart-outfit/upload-reference",
            args.image,
            token=token,
            timeout=120.0,
        )
    )


def cmd_smart_generate(args: argparse.Namespace, base_url: str, config: Dict[str, Any]) -> None:
    token = args.token or config.get("token")
    if not token:
        raise CLIError("Missing token. Run auth login first or pass --token")
    body: Dict[str, Any] = {
        "image_url": args.image_url,
        "location": args.location or "",
        "city": args.city or "",
        "address": {},
        "weather": args.weather or "晴",
        "temperature": float(args.temperature),
        "mood": args.mood or "",
        "count": int(args.count),
        "regeneration_index": int(args.regeneration_index),
    }
    if args.address_json:
        try:
            parsed = json.loads(args.address_json)
            if isinstance(parsed, dict):
                body["address"] = parsed
        except json.JSONDecodeError as exc:
            raise CLIError(f"Invalid --address-json: {exc}") from exc
    if args.gender_expression is not None:
        body["gender_expression"] = float(args.gender_expression)
    print_json(
        post_json(
            base_url,
            "/smart-outfit/generate",
            body,
            token=token,
            timeout=180.0,
        )
    )


def cmd_mood_list(args: argparse.Namespace, base_url: str, _: Dict[str, Any]) -> None:
    """GET /mood/moods — 无需登录。"""
    print_json(get_json(base_url, "/mood/moods", token=None, params=None))


def cmd_mood_recommend(args: argparse.Namespace, base_url: str, config: Dict[str, Any]) -> None:
    token = args.token or config.get("token")
    if not token:
        raise CLIError("Missing token. Run auth login first or pass --token")
    body = {
        "mood": args.mood or "",
        "include_wardrobe": bool(args.include_wardrobe),
    }
    print_json(post_json(base_url, "/mood/recommend", body, token=token, timeout=120.0))


def cmd_tryon(args: argparse.Namespace, base_url: str, config: Dict[str, Any]) -> None:
    token = args.token or config.get("token")
    if not token:
        raise CLIError("Missing token. Run auth login first or pass --token")
    print_json(
        post_tryon_files(
            base_url,
            args.garment,
            args.person,
            token=token,
            prompt=args.prompt or "",
            model_gender=args.model_gender or "neutral",
        )
    )


def cmd_collections_list(args: argparse.Namespace, base_url: str, config: Dict[str, Any]) -> None:
    token = args.token or config.get("token")
    if not token:
        raise CLIError("Missing token. Run auth login first or pass --token")
    params: Dict[str, Any] = {"page": args.page, "page_size": args.page_size}
    if args.scene:
        params["scene"] = args.scene
    print_json(get_json(base_url, "/outfits/collections", token=token, params=params))


def cmd_feedback_create(args: argparse.Namespace, base_url: str, config: Dict[str, Any]) -> None:
    token = args.token or config.get("token")
    if not token:
        raise CLIError("Missing token. Run auth login first or pass --token")
    body: Dict[str, Any] = {
        "event_type": args.event_type,
        "source": args.source or "analysis_outfit",
        "garment_id": args.garment_id,
        "collection_id": args.collection_id,
        "scene": args.scene,
    }
    print_json(post_json(base_url, "/feedback/events", body, token=token))


def cmd_analytics_summary(args: argparse.Namespace, base_url: str, config: Dict[str, Any]) -> None:
    token = args.token or config.get("token")
    if not token:
        raise CLIError("Missing token. Run auth login first or pass --token")
    print_json(
        get_json(
            base_url,
            "/analytics/summary",
            token=token,
            params={"scope": args.scope},
        )
    )


def cmd_agent_intent(args: argparse.Namespace, base_url: str, _: Dict[str, Any]) -> None:
    print_json(post_json_public(base_url, "/agent/intent", {"query": args.query}))


def cmd_memory_add(args: argparse.Namespace, base_url: str, config: Dict[str, Any]) -> None:
    token = args.token or config.get("token")
    if not token:
        raise CLIError("Missing token. Run auth login first or pass --token")
    print_json(
        post_json(
            base_url,
            "/memory/snippets",
            {"title": args.title or "", "content": args.content},
            token=token,
        )
    )


def cmd_memory_search(args: argparse.Namespace, base_url: str, config: Dict[str, Any]) -> None:
    token = args.token or config.get("token")
    if not token:
        raise CLIError("Missing token. Run auth login first or pass --token")
    print_json(
        get_json(
            base_url,
            "/memory/snippets/search",
            token=token,
            params={"q": args.query, "top_k": args.top_k},
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="outfit-cli", description="Smart Outfit CLI")
    parser.add_argument("--base-url", default=None, help="API base URL, e.g. http://127.0.0.1:8010/api/v1")

    sub = parser.add_subparsers(dest="command", required=True)

    p_config = sub.add_parser("config", help="Set CLI config")
    p_config.add_argument("--base-url", default=None)
    p_config.add_argument("--token", default=None)

    p_register = sub.add_parser("register", help="Register user")
    p_register.add_argument("--username", required=True)
    p_register.add_argument("--email", required=True)
    p_register.add_argument("--password", required=True)
    p_register.add_argument("--phone-number", default=None)

    p_login = sub.add_parser("login", help="Login with username/email/phone")
    p_login.add_argument("--identifier", required=True)
    p_login.add_argument("--password", required=True)

    p_wa = sub.add_parser("wardrobe-add", help="Add garment to wardrobe")
    p_wa.add_argument("--image", required=True)
    p_wa.add_argument("--category", required=True)
    p_wa.add_argument("--main-color-name", required=True)
    p_wa.add_argument("--main-color-rgb", required=True, help="e.g. 255,255,255")
    p_wa.add_argument("--main-color-hsv", required=True, help="e.g. 0,0,100")
    p_wa.add_argument("--main-color-hex", required=True, help="e.g. #FFFFFF")
    p_wa.add_argument("--style-tags", default="")
    p_wa.add_argument("--fit-type", default=None)
    p_wa.add_argument("--notes", default=None)
    p_wa.add_argument("--token", default=None)

    p_wl = sub.add_parser("wardrobe-list", help="List wardrobe garments")
    p_wl.add_argument("--page", type=int, default=1)
    p_wl.add_argument("--page-size", type=int, default=20)
    p_wl.add_argument("--category", default=None)
    p_wl.add_argument("--token", default=None)

    p_sim = sub.add_parser("similarity", help="Analyze similarity")
    p_sim.add_argument("--image", required=True)
    p_sim.add_argument("--token", default=None)

    p_out = sub.add_parser("outfits", help="Recommend outfits")
    p_out.add_argument("--images", nargs="+", required=True, help="One or more image paths")
    p_out.add_argument("--num-outfits", type=int, default=3)
    p_out.add_argument("--scene", default=None)
    p_out.add_argument("--token", default=None)

    p_suit = sub.add_parser("suitability", help="Analyze suitability")
    p_suit.add_argument("--image", required=True)
    p_suit.add_argument("--token", default=None)

    p_wx = sub.add_parser("weather", help="Weather by city name (requires login)")
    p_wx.add_argument("--city", required=True, help="City name, e.g. 上海")
    p_wx.add_argument("--token", default=None)

    p_su = sub.add_parser(
        "smart-upload",
        help="Upload reference garment image for smart outfit; returns image_url",
    )
    p_su.add_argument("--image", required=True)
    p_su.add_argument("--token", default=None)

    p_sg = sub.add_parser("smart-generate", help="Generate smart outfits (requires image_url)")
    p_sg.add_argument("--image-url", required=True, help="From smart-upload or uploads URL")
    p_sg.add_argument("--city", default="", help="City or short place name")
    p_sg.add_argument("--location", default="", help="Full address string (optional)")
    p_sg.add_argument("--weather", default="晴")
    p_sg.add_argument("--temperature", type=float, default=20.0)
    p_sg.add_argument("--mood", default="")
    p_sg.add_argument("--count", type=int, default=3)
    p_sg.add_argument("--regeneration-index", type=int, default=0)
    p_sg.add_argument("--gender-expression", type=float, default=None)
    p_sg.add_argument(
        "--address-json",
        default=None,
        help='Optional JSON object for address, e.g. {"city":"上海","district":"浦东"}',
    )
    p_sg.add_argument("--token", default=None)

    sub.add_parser("mood-list", help="List available mood types (no login)")

    p_mr = sub.add_parser("mood-recommend", help="Mood-based recommendation")
    p_mr.add_argument("--mood", default="", help="Mood key or phrase")
    p_mr.add_argument(
        "--include-wardrobe",
        action="store_true",
        help="Include matching garments from wardrobe",
    )
    p_mr.add_argument("--token", default=None)

    p_to = sub.add_parser("tryon", help="Virtual try-on: garment image + person image")
    p_to.add_argument("--garment", required=True, help="Garment product photo path")
    p_to.add_argument("--person", required=True, help="Person photo path")
    p_to.add_argument("--prompt", default="")
    p_to.add_argument(
        "--model-gender",
        default="neutral",
        choices=["male", "female", "neutral"],
    )
    p_to.add_argument("--token", default=None)

    p_col = sub.add_parser("collections-list", help="List saved outfit collections")
    p_col.add_argument("--page", type=int, default=1)
    p_col.add_argument("--page-size", type=int, default=20)
    p_col.add_argument("--scene", default=None)
    p_col.add_argument("--token", default=None)

    p_fb = sub.add_parser("feedback-create", help="Submit feedback event (like/adopt/view/dislike)")
    p_fb.add_argument("--event-type", required=True, choices=["like", "dislike", "adopt", "view"])
    p_fb.add_argument("--source", default="analysis_outfit")
    p_fb.add_argument("--garment-id", default=None)
    p_fb.add_argument("--collection-id", default=None)
    p_fb.add_argument("--scene", default=None)
    p_fb.add_argument("--token", default=None)

    p_an = sub.add_parser("analytics-summary", help="Analytics / flywheel metrics")
    p_an.add_argument(
        "--scope",
        default="user",
        choices=["user", "global"],
        help="user=本人；global=全库汇总",
    )
    p_an.add_argument("--token", default=None)

    p_ai = sub.add_parser("agent-intent", help="Rule-based intent -> suggested MCP tools (no login)")
    p_ai.add_argument("--query", required=True)

    p_ma = sub.add_parser("memory-add", help="Add memory snippet for RAG")
    p_ma.add_argument("--content", required=True)
    p_ma.add_argument("--title", default="")
    p_ma.add_argument("--token", default=None)

    p_ms = sub.add_parser("memory-search", help="Search memory snippets (keyword overlap)")
    p_ms.add_argument("--query", required=True)
    p_ms.add_argument("--top-k", type=int, default=5)
    p_ms.add_argument("--token", default=None)

    return parser


def dispatch(args: argparse.Namespace, config: Dict[str, Any]) -> None:
    base_url = resolve_base_url(args.base_url, config)

    if args.command == "config":
        cmd_config(args, config)
    elif args.command == "register":
        cmd_register(args, base_url, config)
    elif args.command == "login":
        cmd_login(args, base_url, config)
    elif args.command == "wardrobe-add":
        cmd_wardrobe_add(args, base_url, config)
    elif args.command == "wardrobe-list":
        cmd_wardrobe_list(args, base_url, config)
    elif args.command == "similarity":
        cmd_similarity(args, base_url, config)
    elif args.command == "outfits":
        cmd_outfits(args, base_url, config)
    elif args.command == "suitability":
        cmd_suitability(args, base_url, config)
    elif args.command == "weather":
        cmd_weather(args, base_url, config)
    elif args.command == "smart-upload":
        cmd_smart_upload(args, base_url, config)
    elif args.command == "smart-generate":
        cmd_smart_generate(args, base_url, config)
    elif args.command == "mood-list":
        cmd_mood_list(args, base_url, config)
    elif args.command == "mood-recommend":
        cmd_mood_recommend(args, base_url, config)
    elif args.command == "tryon":
        cmd_tryon(args, base_url, config)
    elif args.command == "collections-list":
        cmd_collections_list(args, base_url, config)
    elif args.command == "feedback-create":
        cmd_feedback_create(args, base_url, config)
    elif args.command == "analytics-summary":
        cmd_analytics_summary(args, base_url, config)
    elif args.command == "agent-intent":
        cmd_agent_intent(args, base_url, config)
    elif args.command == "memory-add":
        cmd_memory_add(args, base_url, config)
    elif args.command == "memory-search":
        cmd_memory_search(args, base_url, config)
    else:
        raise CLIError(f"Unknown command: {args.command}")


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config()

    try:
        dispatch(args, config)
        return 0
    except CLIError as exc:
        print_json({"ok": False, "error": str(exc)})
        return 2
    except httpx.HTTPError as exc:
        print_json({"ok": False, "error": f"Network error: {exc}"})
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
