import sys
sys.path.insert(0, r'd:\Users\omen\OneDrive\桌面\clothing-assistant\backend')

with open(r'd:\Users\omen\OneDrive\桌面\clothing-assistant\backend\app\services\tryon_v2\warp_engine.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_func = '''def _detect_face_box_from_result(
    catvton_result: Image.Image,
    cw: int,
    ch: int,
    original_person: Image.Image | None = None,
) -> tuple[int, int, int, int] | None:
    """Detect face bounding box for CatVTON result using Haar cascade.

    Strategy (priority order):
      1. Detect face in ORIGINAL person image (much clearer, more reliable).
         Then SCALE the detected bbox to catvton_result coordinates proportionally.
         This solves the core problem: CatVTON output degrades face quality,
         making Haar cascade detection unreliable on AI-generated faces.
      2. Fallback: detect face directly in catvton_result with histogram equalization.
      3. Final fallback: return None (caller uses coarse neck-based protection).

    Returns (x, y, w, h) in catvton_result pixel coordinates, or None if undetected.
    """
    try:
        from app.services.cascade_manager import load_cascade

        cascade = load_cascade("haarcascade_frontalface_default.xml")
        if cascade is None or cascade.empty():
            logger.warning(
                "catvton_color_fidelity_spatial: Haar cascade unavailable, "
                "falling back to coarse face protection"
            )
            return None

        # ── Priority 1: Detect on ORIGINAL person image (clear, reliable) ───────
        if original_person is not None:
            try:
                orig_arr = np.asarray(original_person.convert("RGB"))
                orig_h, orig_w = orig_arr.shape[:2]

                if orig_h < 64 or orig_w < 64:
                    raise ValueError("Original person image too small")

                orig_gray = cv2.cvtColor(orig_arr, cv2.COLOR_RGB2GRAY)
                orig_gray_eq = cv2.equalizeHist(orig_gray)

                orig_faces = cascade.detectMultiScale(
                    orig_gray_eq,
                    scaleFactor=1.1,
                    minNeighbors=4,
                    minSize=(int(orig_w * 0.06), int(orig_h * 0.06)),
                    maxSize=(int(orig_w * 0.60), int(orig_h * 0.60)),
                )

                if orig_faces is not None and len(orig_faces) > 0:
                    orig_face_list = sorted(orig_faces, key=lambda f: f[2] * f[3], reverse=True)
                    ofx, ofy, ofw, ofh = [int(v) for v in orig_face_list[0]]

                    # Scale from original person coords → catvton_result coords
                    scale_x = cw / float(orig_w)
                    scale_y = ch / float(orig_h)
                    fx = int(ofx * scale_x)
                    fy = int(ofy * scale_y)
                    fw = int(ofw * scale_x)
                    fh = int(ofh * scale_y)

                    # Safety clamp
                    fx = _clamp_int(fx, 0, cw - 1)
                    fy = _clamp_int(fy, 0, ch - 1)
                    fw = _clamp_int(fw, 4, cw)
                    fh = _clamp_int(fh, 4, ch)

                    logger.info(
                        "catvton_color_fidelity_spatial: face detected on ORIGINAL person "
                        "([%d,%d,%d,%d] at %dx%d) -> scaled to catvton([%d,%d,%d,%d] at %dx%d) "
                        "(sx=%.4f, sy=%.4f)",
                        ofx, ofy, ofw, ofh, orig_w, orig_h,
                        fx, fy, fw, fh, cw, ch,
                        scale_x, scale_y,
                    )
                    return (fx, fy, fw, fh)
            except Exception as orig_err:
                logger.debug(
                    "catvton_color_fidelity_spatial: face detection on original failed (%s), "
                    "falling back to catvton result detection",
                    orig_err,
                )

        # ── Priority 2: Detect on CatVTON result directly (fallback) ──────────
        arr = np.asarray(catvton_result.convert("RGB"))
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        gray_eq = cv2.equalizeHist(gray)

        faces = cascade.detectMultiScale(
            gray_eq,
            scaleFactor=1.1,
            minNeighbors=4,
            minSize=(int(cw * 0.06), int(ch * 0.06)),
            maxSize=(int(cw * 0.60), int(ch * 0.60)),
        )
        if faces is None or len(faces) == 0:
            logger.debug(
                "catvton_color_fidelity_spatial: no face detected by Haar cascade "
                "(will use coarse neck-based protection)"
            )
            return None

        face_list = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        fx, fy, fw, fh = [int(v) for v in face_list[0]]
        logger.info(
            "catvton_color_fidelity_spatial: face detected on CatVTON result "
            "bbox=[%d,%d,%d,%d] (%.1f%%w x %.1f%%h)",
            fx, fy, fw, fh,
            fw / cw * 100, fh / ch * 100,
        )
        return (fx, fy, fw, fh)

    except Exception as e:
        logger.warning(
            "catvton_color_fidelity_spatial: face detection failed (%s), "
            "falling back to coarse neck-based protection",
            e,
        )
        return None

'''

# Find and replace the function
start = content.find('def _detect_face_box_from_result(')
rest = content[start+1:]
next_def = rest.find('\ndef ')
end_offset = start + 1 + next_def if next_def != -1 else len(content)

new_content = content[:start] + new_func + content[end_offset:]

with open(r'd:\Users\omen\OneDrive\桌面\clothing-assistant\backend\app\services\tryon_v2\warp_engine.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print('Replacement done. Old length:', len(content), 'New length:', len(new_content))
