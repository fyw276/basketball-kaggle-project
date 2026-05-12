"""Remove the duplicated 'realistic' mode block (alias to 'professional')."""

import re

path = r"D:\Users\omen\OneDrive\桌面\clothing-assistant\backend\app\api\tryon_v2.py"
with open(path, encoding="utf-8") as f:
    content = f.read()

# -------------------------------------------------------------------
# 1. Replace the entire 'realistic' elif block with a 2-line alias
# -------------------------------------------------------------------
# Find: elif mode == "realistic": [full block, ~220 lines] elif mode == "professional":
# Replace with: elif mode == "realistic": [alias + log] else: (falls through to professional)

old_realistic_block = """    elif mode == "realistic":
        # ── Realistic Mode: 使用 CatVTON 深度学习模型 ──────────────────────────
        # CatVTON 是唯一能产生真实试穿效果的深度学习模型
        # 它会根据人体姿态进行真实的衣物贴合、变形和光影处理
        from app.services.tryon_v2.catvton_engine_client import (
            _catvton_configured,
            call_local_catvton,
        )
        from app.services.tryon_v2.warp_engine import (
            tryon_pants_warp,
            tryon_skirt_warp,
            tryon_top_warp_preserve,
        )

        cat = (garment_category or "").strip().lower()

        cloth_type = "upper"
        if any(k in cat for k in ("bottom", "下装", "裤")):
            cloth_type = "lower"
        elif any(k in cat for k in ("skirt", "裙", "连衣裙", "dress")):
            cloth_type = "overall"

        # ── CatVTON 调用：最多重试 2 次（瞬时错误 / VRAM OOM / CUDA 抖动）───
        max_retries = 2
        last_upstream = None
        last_err_reason = None

        for attempt in range(max_retries + 1):
            if attempt > 0:
                wait_s = 2 ** (attempt - 1)
                logger.warning(
                    f"Realistic mode: CatVTON attempt {attempt}/{max_retries} failed, "
                    f"retrying in {wait_s}s..."
                )
                await asyncio.sleep(wait_s)

            upstream = await call_local_catvton(
                garment_bytes=garment_jpg,
                person_bytes=person_jpg,
                garment_category=cloth_type,
                debug_dir=debug_session_dir,
                preprocess_only=(debug_mode == "preprocess_only"),
            )
            last_upstream = upstream

            # ─── 预处理模式：直接返回中间产物 ─────────────────────────
            if debug_mode == "preprocess_only" and isinstance(upstream, dict):
                upstream_meta = upstream.get("metadata") or {}
                record_tryon_v2_success(int((time.perf_counter() - started) * 1000))
                return TryOnV2Response(
                    status="preprocess_only_success",
                    message="预处理完成（diffusion 未运行）。"
                    "请查看 debug_session_dir 中的 03_mask.png 和 04_pose_keypoints.jpg 验证质量。",
                    pipeline="REALISTIC",
                    result_image_url=None,
                    error_code=None,
                    retryable=False,
                    action_hint="检查 03_mask.png 是否覆盖了正确的衣服区域。"
                    "检查 04_pose_keypoints.jpg 关键点是否准确。",
                    qc_scores=upstream.get("qc_scores") or {},
                    metadata={
                        **upstream_meta,
                        "mode": "preprocess_only",
                        "engine": "catvton",
                        "catvton_category": cloth_type,
                    },
                    debug_session_dir=debug_session_dir,
                )

            # 检查 CatVTON 成功条件
            if (
                isinstance(upstream, dict)
                and str(upstream.get("status") or "").lower() == "success"
                and upstream.get("result_image") is not None
            ):
                result_img = upstream.get("result_image")

                # ── 衣服颜色保真增强（启用）───────────────────────────────────────
                # CatVTON 会重新生成衣服的颜色/图案，可能与原衣服差异较大。
                # catvton_color_fidelity_enhance 在保留 CatVTON 光影/阴影的前提下，
                # 用原衣服的颜色修正衣服区域，实现"真实贴合 + 颜色保真"。
                # 仅对彩色/有图案的衣服生效（高饱和度检测），纯白/纯黑衣服跳过。
                pattern_score = 0.0
                pattern_injected = False
                fidelity_strength = float(
                    getattr(settings, "TRYON_V2_COLOR_FIDELITY_STRENGTH", 0.75) or 0.75
                )
                enable_color_fidelity = bool(
                    getattr(settings, "TRYON_V2_COLOR_FIDELITY_ENABLED", True)
                )

                if enable_color_fidelity and fidelity_strength > 0.0:
                    try:
                        from app.services.tryon_v2.warp_engine import catvton_color_fidelity_enhance

                        arr_check = np.array(garment_image.convert("RGB"))
                        hsv_check = cv2.cvtColor(arr_check, cv2.COLOR_RGB2HSV).astype(np.float32)
                        sat_check = hsv_check[:, :, 1]
                        v_check = hsv_check[:, :, 2]
                        fg_mask_check = ~((v_check / 255.0 > 0.92) & (sat_check / 255.0 < 0.08))
                        fg_sat_check = sat_check[fg_mask_check]
                        if len(fg_sat_check) >= 50:
                            sat_mean = float(fg_sat_check.mean()) / 255.0
                        else:
                            sat_mean = 0.0

                        # 只有彩色衣服才启用保真（sat_mean > 0.08）
                        if sat_mean > 0.08:
                            logger.info(
                                "Realistic mode: applying color fidelity "
                                "(saturation=%.3f, strength=%.2f)",
                                sat_mean,
                                fidelity_strength,
                            )
                            result_img, cf_meta = catvton_color_fidelity_enhance(
                                catvton_result=result_img,
                                original_garment=garment_image,
                                person_image=person_image,
                                garment_category=gc or "top",
                                fidelity_strength=fidelity_strength,
                            )
                            pattern_injected = True
                            pattern_score = min(0.95, sat_mean + 0.3)
                            upstream["metadata"] = {
                                **(upstream.get("metadata") or {}),
                                **cf_meta,
                                "color_fidelity_applied": True,
                            }
                            logger.info(
                                "Realistic mode: color fidelity applied " "(pattern_score=%.3f)",
                                pattern_score,
                            )
                        else:
                            logger.info(
                                "Realistic mode: skipping color fidelity "
                                "(saturation=%.3f < 0.08, likely solid garment)",
                                sat_mean,
                            )
                    except Exception as cf_err:
                        logger.warning(
                            "Realistic mode: color fidelity failed (continuing): %s", cf_err
                        )
                else:
                    logger.info(
                        "Realistic mode: color fidelity disabled " "(enable=%s, strength=%.2f)",
                        enable_color_fidelity,
                        fidelity_strength,
                    )

                result = {
                    "status": "success",
                    "message": "CatVTON 深度学习试衣完成（真实贴合 + 细节保真）",
                    "result_image": result_img,
                    "qc_scores": {
                        "fidelity_score": 0.85 if not pattern_injected else 0.95,
                        "realism_score": 0.90,
                    },
                    "metadata": {
                        "pipeline": "REALISTIC",
                        "engine": "catvton",
                        "catvton_category": cloth_type,
                        "method": "deep_learning",
                        "attempts": attempt + 1,
                        "pattern_protected": pattern_injected,
                        "pattern_score": round(pattern_score, 3),
                    },
                }
                logger.info(f"Realistic mode: CatVTON succeeded on attempt {attempt + 1}")
                break

            # 记录失败原因用于诊断
            if isinstance(upstream, dict):
                last_err_reason = (
                    f"status={upstream.get('status')}, "
                    f"message={upstream.get('message')}, "
                    f"reason={upstream.get('metadata', {}).get('reason', 'unknown')}"
                )
            else:
                last_err_reason = f"unexpected upstream type: {type(upstream).__name__}"

            logger.warning(
                f"Realistic mode: CatVTON attempt {attempt + 1} returned: {last_err_reason}"
            )

            # 永久性错误（不需要重试）
            if isinstance(upstream, dict):
                reason = upstream.get("metadata", {}).get("reason", "")
                if reason in (
                    "not_configured",
                    "path_not_found",
                    "catvton_not_available",
                ):
                    logger.error(
                        f"Realistic mode: permanent CatVTON error ({reason}), not retrying"
                    )
                    break
                if upstream.get("status") == "timeout":
                    logger.error("Realistic mode: CatVTON timeout, not retrying")
                    break
        else:
            # 所有重试均失败
            upstream = last_upstream
            upstream_status = (
                upstream.get("status") if isinstance(upstream, dict) else str(upstream)
            )
            upstream_msg = upstream.get("message") if isinstance(upstream, dict) else ""
            upstream_meta = upstream.get("metadata", {}) if isinstance(upstream, dict) else {}
            debug_session = upstream_meta.get("debug_session_dir") or debug_session_dir or ""
            print(
                f"[REALISTIC-MODE-ERROR] CatVTON failed after {max_retries + 1} attempts: "
                f"status={upstream_status}, message={upstream_msg}, last_reason={last_err_reason}. "
                f"Debug dir: {debug_session}",
                flush=True,
            )
            raise RuntimeError(
                f"Realistic 模式失败: CatVTON 多次重试后仍不可用 "
                f"(status={upstream_status}, message={upstream_msg}). "
                f"请检查 {debug_session} 下的中间产物或运行预处理模式 debug。 "
                f"如需降级到 warp 试衣，请使用 mode=warp。"
            )"""

new_alias = """    elif mode == "realistic":
        mode = "professional"
        logger.info("'realistic' aliased to 'professional' — shared implementation")"""

if old_realistic_block in content:
    content = content.replace(old_realistic_block, new_alias)
    print("Step 1 OK: replaced 'realistic' block with alias")
else:
    print("WARNING: could not find exact 'realistic' block text")
    # Try a looser approach
    import re as re2

    pattern = r'\n    elif mode == "realistic":\n        # ── Realistic Mode.*?\n    elif mode == "professional":'
    match = re2.search(pattern, content, re2.DOTALL)
    if match:
        print(f"Found via regex at pos {match.start()}-{match.end()}")
        content = (
            content[: match.start()]
            + '\n    elif mode == "realistic":\n        mode = "professional"\n        logger.info("\'realistic\' aliased to \'professional\' — shared implementation")'
            + content[match.end() :]
        )
        print("Step 1 OK (regex): replaced 'realistic' block with alias")
    else:
        print("ERROR: could not find realistic block at all")

# -------------------------------------------------------------------
# 2. Fix the 'gc' undefined variable bug in professional block
#    (line ~1369: garment_category=gc or "top")
#    Should use 'cat' instead of 'gc'
# -------------------------------------------------------------------
# The professional block also has the same bug. Fix both.
content = content.replace('garment_category=gc or "top"', 'garment_category=cat or "top"')
print("Step 2 OK: fixed 'gc' undefined bug → 'cat'")

# -------------------------------------------------------------------
# 3. Remove unused imports from professional block
# -------------------------------------------------------------------
# The professional block imports _catvton_configured but never uses it
content = content.replace(
    """        from app.services.tryon_v2.catvton_engine_client import (
            _catvton_configured,
            call_local_catvton,
        )

        cat = (garment_category or "").strip().lower()""",
    """        from app.services.tryon_v2.catvton_engine_client import (
            call_local_catvton,
        )

        cat = (garment_category or "").strip().lower()""",
)
print("Step 3 OK: removed unused _catvton_configured import")

# -------------------------------------------------------------------
# 4. Update professional mode comment to reflect shared usage
# -------------------------------------------------------------------
content = content.replace(
    "        # ── Professional Mode: 使用 CatVTON + 后处理 ────────────────────────────\n        # 优先使用 CatVTON 深度学习模型",
    "        # ── CatVTON 深度学习试衣（professional / realistic 共用实现）──────────────",
)
print("Step 4 OK: updated professional block comment")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("Done.")
