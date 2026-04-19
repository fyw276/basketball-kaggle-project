"""
Virtual Try-On Service — SD-VTON based diffusion model.

Based on research insight:
Virtual Try-on Diffusion (SD-VTON等) 在保真度上持续改进

This module provides virtual try-on capabilities using Stable Diffusion-based
virtual try-on models. Supports:
- VITON-HD / SD-VTON pipeline
- Person-agnostic garment transfer
- High-fidelity synthesis

Note: SD-VTON requires significant compute (GPU recommended, ~8GB VRAM).
For CPU-only or low-resource deployments, falls back to a placeholder service.
For production, consider deploying SD-VTON as a separate microservice or using
Replicate/Modal for cloud GPU inference.
"""

import hashlib
import os
from pathlib import Path
from typing import Any, Optional

from PIL import Image

from app.core.config import settings
from app.core.logging import setup_logging

logger = setup_logging()

# Bump this to force new cached results for fallback.
FALLBACK_PIPELINE_VERSION = "fallback_v7"

# 旧客户端曾传「front view」等，易把通用 inpainting 带偏成场景生成而非试衣
_VIEW_PROMPT_DISCARD = frozenset({"front view", "side view", "back view"})


def sanitize_tryon_prompt(prompt: Optional[str]) -> Optional[str]:
    """Drop misleading view-only prompts; keep None for default try-on prompts."""
    if not prompt or not str(prompt).strip():
        return None
    s = str(prompt).strip().lower()
    if s in _VIEW_PROMPT_DISCARD:
        return None
    return str(prompt).strip()


def _infer_fallback_placement(garment_category: Optional[str]) -> Optional[str]:
    """Map wardrobe category to paste region: bottom, top, or None (aspect heuristics only)."""
    if not garment_category or not str(garment_category).strip():
        return None
    c = str(garment_category).strip().lower()
    # Full-body pieces: do not force "bottom" (would match substring 裙 in 连衣裙).
    if any(k in c for k in ("连衣裙", "连体", "套装")):
        return None
    for k in (
        "裤",
        "下装",
        "牛仔",
        "半裙",
        "长裙",
        "短裙",
        "卫裤",
        "阔腿裤",
        "短裤",
    ):
        if k in c:
            return "bottom"
    for k in (
        "上衣",
        "外套",
        "衬",
        "t恤",
        "卫衣",
        "针织",
        "吊带",
        "背心",
        "夹克",
        "大衣",
        "羽绒服",
    ):
        if k in c:
            return "top"
    return None


def _haarcascade_frontalface_xml() -> Optional[Path]:
    """
    Path to haarcascade_frontalface_default.xml that OpenCV can open.

    On Windows, cv2 is often installed under a Unicode path (e.g. OneDrive/桌面).
    OpenCV's C++ FileStorage may mangle non-ASCII paths and fail to open the XML.
    We copy the bundled file under %LOCALAPPDATA% (usually ASCII) as a stable workaround.
    """
    import shutil

    try:
        import cv2
    except ImportError:
        return None

    src = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    if not src.is_file():
        logger.warning("Bundled Haar cascade missing: %s", src)
        return None

    if os.name != "nt":
        return src

    try:
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or ""
        if not base.strip():
            return src
        cache_dir = Path(base) / "clothing-assistant" / "opencv_haarcascades"
        cache_dir.mkdir(parents=True, exist_ok=True)
        dst = cache_dir / "haarcascade_frontalface_default.xml"
        try:
            if not dst.is_file() or dst.stat().st_size != src.stat().st_size:
                shutil.copy2(src, dst)
        except OSError:
            return src
        return dst
    except Exception as e:
        logger.warning("Could not stage Haar cascade to ASCII path, using bundled path: %s", e)
        return src


# ──────────────────────────────────────────────────────────────────────────────
# Model Configuration
# ──────────────────────────────────────────────────────────────────────────────

# HuggingFace SD-VTON model (or compatible Stable Diffusion ControlNet for try-on)
# Available models on HuggingFace:
# - "timbeck7/SD-VTON" — Stable Diffusion Virtual Try-On
# - "lllyasviel/sd-controlnet-openpose" — ControlNet for pose-guided try-on
# - "stabilityai/stable-diffusion-2-inpainting" — SD 2.0 inpainting
#   (often gated; requires HF auth + acceptance)
# - "stable-diffusion-v1-5/stable-diffusion-inpainting" — public inpainting
#   baseline compatible with diffusers (recommended default)
SD_VTON_MODEL_ID = os.environ.get(
    "SD_VTON_MODEL_ID", "stable-diffusion-v1-5/stable-diffusion-inpainting"
)

# ControlNet model for pose/segmentation guidance
CONTROLNET_MODEL_ID = os.environ.get("CONTROLNET_MODEL_ID", "lllyasviel/control_v11p_sd15_openpose")

# Inference settings
DEFAULT_STEPS = 25
DEFAULT_GUIDANCE_SCALE = 7.5


def _resolve_tryon_model_source() -> tuple[str, str]:
    """
    Resolve try-on model source.

    Returns:
        ("local", <abs_path>) when TRYON_MODEL_LOCAL_PATH is configured and exists;
        otherwise ("hf", <model_id>).
    """
    local_path = str(getattr(settings, "TRYON_MODEL_LOCAL_PATH", "") or "").strip()
    if local_path:
        p = Path(local_path).expanduser()
        if p.is_dir():
            return "local", str(p)
        logger.warning("TRYON_MODEL_LOCAL_PATH does not exist or is not a directory: %s", p)
    return "hf", SD_VTON_MODEL_ID


def _tryon_force_fallback_enabled() -> bool:
    """Whether try-on should skip diffusion model loading entirely."""
    return bool(getattr(settings, "TRYON_FORCE_FALLBACK", False))


# ──────────────────────────────────────────────────────────────────────────────
# Try-On Service
# ──────────────────────────────────────────────────────────────────────────────


class VirtualTryOnService:
    """
    Virtual Try-On service using Stable Diffusion-based models.

    Supports:
    1. Garment-only try-on: Upload a garment image, get it rendered on a person
    2. Full outfit try-on: Try on multiple garments simultaneously
    3. Style transfer: Apply garment style to existing outfit

    Falls back to a sketch/description mode when GPU is unavailable.

    For best results with SD-VTON:
    - garment_image: Clean product photo (white/neutral background preferred)
    - person_image: Full-body or half-body photo (front-facing, good lighting)
    - Both images should be 512x512 or 768x768 for optimal results
    """

    def __init__(
        self,
        device: str = "auto",
        enable_cache: bool = True,
    ):
        """
        Initialize the try-on service.

        Args:
            device: Compute device ("auto", "cuda", "cpu")
            enable_cache: Whether to cache results
        """
        self.device = self._resolve_device(device)
        self.enable_cache = enable_cache
        self._cache = {}
        self._model = None
        self._is_available = None
        self._model_source = None
        logger.info(f"VirtualTryOnService initialized (device={self.device})")

    def _resolve_device(self, device: str) -> str:
        """Resolve compute device."""
        if device == "auto":
            try:
                import torch

                return "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                return "cpu"
        return device

    # ─── Model Loading ───────────────────────────────────────────────────────

    def _ensure_model_loaded(self) -> bool:
        """
        Load SD-VTON / Stable Diffusion inpainting model.
        Returns True if successful, False if unavailable.
        """
        if self._is_available is not None:
            return self._is_available

        if _tryon_force_fallback_enabled():
            logger.info("TRYON_FORCE_FALLBACK enabled; skip diffusion model loading")
            self._is_available = False
            self._model_source = "forced_fallback"
            return False

        # Check if we have the necessary dependencies
        try:
            import torch  # noqa: F401 - required for torch_dtype
            from diffusers import StableDiffusionInpaintPipeline

            source_kind, source_value = _resolve_tryon_model_source()
            self._model_source = source_value
            logger.info(
                "Loading Stable Diffusion inpainting model on {} from {}: {}",
                self.device,
                source_kind,
                source_value,
            )
            dtype = torch.float16 if self.device == "cuda" else torch.float32
            # This repo ships UNet/TextEncoder as .bin (pickle), not .safetensors.
            # Newer diffusers defaults to preferring safetensors and fails on Windows/HF cache.
            load_kw = {
                "torch_dtype": dtype,
                "safety_checker": None,
                "feature_extractor": None,
                "requires_safety_checker": False,
                "use_safetensors": False,
            }
            try:
                self._model = StableDiffusionInpaintPipeline.from_pretrained(
                    source_value,
                    low_cpu_mem_usage=True,
                    **load_kw,
                )
            except TypeError:
                self._model = StableDiffusionInpaintPipeline.from_pretrained(
                    source_value,
                    **load_kw,
                )
            self._model.to(self.device)
            self._is_available = True
            logger.info("Virtual try-on model loaded successfully")
            return True
        except ImportError as e:
            logger.warning(f"Required packages not available: {e}")
            logger.warning("Install: pip install diffusers torch")
            self._is_available = False
            return False
        except Exception as e:
            logger.warning(
                "Failed to load try-on model: {} "
                "(set TRYON_MODEL_LOCAL_PATH to an offline snapshot, "
                "or set TRYON_FORCE_FALLBACK=true to use paste-only mode)",
                e,
            )
            self._is_available = False
            return False

    def _current_model_label(self) -> str:
        """Return the actual loaded model source when available."""
        return getattr(self, "_model_source", None) or SD_VTON_MODEL_ID

    # ─── Core Try-On Methods ───────────────────────────────────────────────

    def tryon_garment(
        self,
        garment_image: Image.Image,
        person_image: Image.Image,
        garment_mask: Optional[Image.Image] = None,
        prompt: Optional[str] = None,
        num_inference_steps: int = DEFAULT_STEPS,
        guidance_scale: float = DEFAULT_GUIDANCE_SCALE,
        seed: Optional[int] = None,
        # 无性别推荐系统新增参数
        model_gender: str = "neutral",
        garment_category: Optional[str] = None,
    ) -> dict:
        """
        Try on a garment on a person image.

        无性别推荐系统 (Step 4):
        - model_gender 参数允许用户切换查看效果
        - 支持 male/female/neutral 三种模式
        - 同一件衣服可以分别在男女模特上生成上身图

        Args:
            garment_image: Clean garment product photo (PIL Image)
            person_image: Person photo (PIL Image)
            garment_mask: Optional mask indicating where to apply garment
                         (auto-generated if not provided)
            prompt: Optional text prompt describing desired output
            num_inference_steps: Diffusion steps (25-50 recommended)
            guidance_scale: CFG scale (5-12 recommended)
            seed: Optional random seed for reproducibility
            model_gender: 模特性别 ("male" / "female" / "neutral")

        Returns:
            Dict with:
                - result_image: PIL Image of the try-on result
                - status: "success" / "fallback" / "error"
                - message: Human-readable status message
                - metadata: Processing info (steps, seed, model_gender, etc.)
        """
        logger.info(f"Starting virtual try-on (model_gender={model_gender})")

        prompt = sanitize_tryon_prompt(prompt)

        # Check cache (include model_gender in cache key)
        cache_key = self._compute_cache_key(
            garment_image, person_image, prompt, model_gender, garment_category
        )
        if self.enable_cache and cache_key in self._cache:
            logger.debug("Try-on cache hit")
            return self._cache[cache_key]

        # 含模特的商品图会与人物叠出「双人脸」，直接拒绝
        if self._garment_has_face(garment_image):
            return {
                "result_image": None,
                "status": "error",
                "message": "衣服图检测到人像，请上传无模特的白底商品图，否则会出现重影。",
                "metadata": {"reason": "garment_contains_face"},
            }

        # Try loading the model
        if self._ensure_model_loaded():
            return self._tryon_diffusion(
                garment_image,
                person_image,
                garment_mask,
                prompt,
                num_inference_steps,
                guidance_scale,
                seed,
                cache_key,
                model_gender,
            )
        else:
            return self._tryon_fallback(
                garment_image,
                person_image,
                prompt,
                cache_key,
                model_gender,
                garment_category=garment_category,
            )

    def _tryon_diffusion(
        self,
        garment_image: Image.Image,
        person_image: Image.Image,
        garment_mask: Optional[Image.Image],
        prompt: Optional[str],
        num_inference_steps: int,
        guidance_scale: float,
        seed: Optional[int],
        cache_key: str,
        model_gender: str = "neutral",
    ) -> dict:
        """Run SD-based virtual try-on with gender-aware prompts."""
        import torch

        logger.info(f"Running Stable Diffusion virtual try-on (gender={model_gender})")

        # Auto-generate garment mask if not provided
        if garment_mask is None:
            garment_mask = self._generate_garment_mask(garment_image)

        # Build gender-aware prompt
        if prompt is None:
            prompt = self._build_tryon_prompt(garment_image, model_gender)
        else:
            # Inject gender into existing prompt
            prompt = self._inject_gender_into_prompt(prompt, model_gender)

        negative_prompt = (
            "low quality, blurry, distorted, watermark, text, "
            "deformed body, extra limbs, bad anatomy, poorly drawn face"
        )

        # Set seed
        generator = None
        if seed is not None:
            generator = torch.Generator(device=self.device).manual_seed(seed)

        # Resize to model input size
        target_size = (768, 768)
        person_resized = person_image.resize(target_size, Image.Resampling.LANCZOS)
        mask_resized = garment_mask.resize(target_size, Image.Resampling.LANCZOS)

        try:
            # Run inference
            result = self._model(
                prompt=prompt,
                image=person_resized,
                mask_image=mask_resized,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                negative_prompt=negative_prompt,
                generator=generator,
            ).images[0]
        except Exception as e:
            err_text = str(e)
            low = err_text.lower()
            reason = "inference_failed"
            if "out of memory" in low or "cuda" in low:
                reason = "gpu_oom"
            elif "timeout" in low or "timed out" in low:
                reason = "timeout"
            logger.warning("Diffusion try-on failed (%s): %s", reason, err_text)
            return {
                "result_image": None,
                "status": "error",
                "message": f"虚拟试穿失败: {err_text}",
                "metadata": {
                    "reason": reason,
                    "model": self._current_model_label(),
                    "device": self.device,
                },
            }

        output = {
            "result_image": result,
            "status": "success",
            "message": f"虚拟试穿成功完成 (model_gender={model_gender})",
            "metadata": {
                "model": self._current_model_label(),
                "prompt": prompt,
                "steps": num_inference_steps,
                "guidance_scale": guidance_scale,
                "seed": seed,
                "device": self.device,
                "model_gender": model_gender,
            },
        }

        if self.enable_cache:
            self._cache[cache_key] = output

        return output

    def _tryon_fallback(
        self,
        garment_image: Image.Image,
        person_image: Image.Image,
        prompt: Optional[str],
        cache_key: str,
        model_gender: str = "neutral",
        garment_category: Optional[str] = None,
    ) -> dict:
        """
        Fallback when SD-VTON is not available.
        使用去背景后的 RGBA + alpha 粘贴到人像上，避免 Image.blend 造成的重影/双人脸。
        """
        logger.warning(f"Using fallback composition mode (no GPU/model, gender={model_gender})")
        try:
            garment_rgba = self._garment_to_rgba_cutout(garment_image)
            result = self._paste_garment_on_person(
                person_image, garment_rgba, garment_category=garment_category
            )

            output = {
                "result_image": result,
                "status": "fallback",
                "message": (
                    "已使用去背景+粘贴合成（未加载扩散模型）。"
                    "安装 diffusers/torch 并可选用 GPU 可获得更高质量试衣。"
                ),
                "metadata": {
                    "model": "fallback_paste",
                    "device": "cpu",
                    "note": "mask+paste, no alpha blend",
                    "reason": (
                        "forced_fallback"
                        if _tryon_force_fallback_enabled()
                        else "model_unavailable"
                    ),
                },
            }

            if self.enable_cache:
                self._cache[cache_key] = output

            return output

        except Exception as e:
            logger.error(f"Fallback try-on also failed: {e}")
            return {
                "result_image": None,
                "status": "error",
                "message": f"虚拟试穿失败: {str(e)}",
                "metadata": {
                    "reason": "fallback_failed",
                    "error": str(e),
                },
            }

    def _garment_has_face(self, garment_image: Image.Image) -> bool:
        """检测衣服图是否含正面人脸（含模特图）。"""
        try:
            import cv2
            import numpy as np

            arr = np.array(garment_image.convert("RGB"))
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
            xml_path = _haarcascade_frontalface_xml()
            if xml_path is None:
                return False
            cascade = cv2.CascadeClassifier(str(xml_path))
            if cascade.empty():
                logger.warning("Haar cascade not loaded; skip garment face check")
                return False
            faces = cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(64, 64)
            )
            return len(faces) > 0
        except Exception as e:
            logger.warning("Garment face detection skipped: %s", e)
            return False

    def _garment_to_rgba_cutout(self, garment_image: Image.Image) -> Image.Image:
        """
        衣服抠图：优先 rembg（若已安装），否则用亮度/饱和度阈值生成 mask 作 alpha。
        """
        rgb = garment_image.convert("RGB")
        if _tryon_force_fallback_enabled():
            mask_l = self._refine_garment_mask_with_grabcut(garment_image)
            rgba = rgb.convert("RGBA")
            rgba.putalpha(mask_l)
            logger.info("Garment cutout: local refined mask (forced fallback)")
            return rgba
        try:
            from io import BytesIO

            from rembg import remove

            out = remove(rgb)
            if isinstance(out, Image.Image):
                logger.info("Garment cutout: rembg")
                return out.convert("RGBA")
            if isinstance(out, (bytes, bytearray)):
                logger.info("Garment cutout: rembg (bytes)")
                return Image.open(BytesIO(out)).convert("RGBA")
        except SystemExit as e:
            logger.info(
                "rembg exited during import/use (%s); using local mask for garment alpha", e
            )
        except Exception as e:
            logger.info("rembg unavailable (%s); using local mask for garment alpha", e)

        mask_l = self._refine_garment_mask_with_grabcut(garment_image)
        rgba = rgb.convert("RGBA")
        rgba.putalpha(mask_l)
        logger.info("Garment cutout: local refined mask")
        return rgba

    def _largest_connected_component_mask(self, mask_array):
        """Keep the largest foreground component to suppress background speckles."""
        import numpy as np

        try:
            import cv2

            mask_u8 = mask_array.astype("uint8")
            num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask_u8, connectivity=8)
            if num_labels <= 1:
                return mask_u8
            areas = stats[1:, cv2.CC_STAT_AREA]
            largest_idx = int(np.argmax(areas)) + 1
            return (labels == largest_idx).astype("uint8")
        except Exception:
            return mask_array.astype("uint8")

    def _fill_binary_mask_holes(self, mask_u8: Any) -> Any:
        """Fill holes inside a binary mask (expects 0/255 uint8)."""
        try:
            import cv2
            import numpy as np

            m = (mask_u8 > 0).astype(np.uint8) * 255
            h, w = m.shape[:2]
            flood = m.copy()
            flood_mask = np.zeros((h + 2, w + 2), np.uint8)
            # Flood fill the outer background (0) with 255, then invert to get holes (still 0).
            if int(flood[0, 0]) == 0:
                cv2.floodFill(flood, flood_mask, (0, 0), 255)
            flood_inv = cv2.bitwise_not(flood)
            filled = cv2.bitwise_or(m, flood_inv)
            return filled
        except Exception:
            return mask_u8

    def _classify_garment_photo_type(self, garment_image: Image.Image) -> str:
        """
        Classify product photo into simple local buckets.

        - `white_bg`: bright clean product shots on white background
        - `flat_lay`: laid-out garments on mixed but mostly static background
        - `real_photo`: in-scene/product-in-use photos, use more conservative cutout
        """
        import numpy as np

        rgb = garment_image.convert("RGB")
        arr = np.array(rgb, dtype=np.float32)
        h, w = arr.shape[:2]
        if h == 0 or w == 0:
            return "real_photo"

        gray = arr.mean(axis=2)
        sat = arr.std(axis=2)
        border = max(4, min(h, w) // 18)

        border_mask = np.zeros((h, w), dtype=bool)
        border_mask[:border, :] = True
        border_mask[-border:, :] = True
        border_mask[:, :border] = True
        border_mask[:, -border:] = True

        border_gray = gray[border_mask]
        border_sat = sat[border_mask]
        bright_border_ratio = float(((border_gray > 236) & (border_sat < 14)).mean())
        dark_border_ratio = float((border_gray < 90).mean())
        border_std = float(border_gray.std()) if border_gray.size else 0.0
        center_sat_mean = float(
            sat[h // 4 : max(h // 4 + 1, 3 * h // 4), w // 4 : max(w // 4 + 1, 3 * w // 4)].mean()
        )

        if bright_border_ratio > 0.78 and border_std < 18:
            return "white_bg"
        if dark_border_ratio > 0.38 or border_std > 42 or center_sat_mean > 36:
            return "real_photo"
        return "flat_lay"

    def _generate_garment_mask_by_photo_type(
        self,
        garment_image: Image.Image,
        photo_type: str,
    ) -> Image.Image:
        """Generate a coarse mask tuned for the detected product photo type."""
        import numpy as np
        from PIL import Image as PILImage
        from PIL import ImageFilter

        img_array = np.array(garment_image.convert("RGB"))
        h, w = img_array.shape[:2]
        gray = np.mean(img_array, axis=2)
        sat = np.std(img_array, axis=2)

        if photo_type == "white_bg":
            bg_mask = (gray > 240) & (sat < 18)
            grow_steps = 2
            blur_radius = 0.8
            fg_seed = None
        elif photo_type == "flat_lay":
            bg_mask = (gray > 228) & (sat < 16)
            grow_steps = 3
            blur_radius = 1.1
            fg_seed = None
        else:
            # Real photo: background is often similar to border colors.
            border = max(8, min(h, w) // 14)
            border_pixels = np.concatenate(
                [
                    img_array[:border, :, :].reshape(-1, 3),
                    img_array[-border:, :, :].reshape(-1, 3),
                    img_array[:, :border, :].reshape(-1, 3),
                    img_array[:, -border:, :].reshape(-1, 3),
                ],
                axis=0,
            ).astype(np.float32)
            border_mean = border_pixels.mean(axis=0)
            dist = np.sqrt(np.sum((img_array.astype(np.float32) - border_mean) ** 2, axis=2))

            # Two-threshold scheme:
            # - confident background: very close to border mean
            # - confident foreground: far from border mean (or high saturation)
            bg_mask = (dist < 18) | ((gray > 220) & (sat < 24) & (dist < 32))
            fg_seed = (dist > 45) | (sat > 42)
            # IMPORTANT: keep seeds strict for real photos; don't blur/expand too early
            grow_steps = 0
            blur_radius = 0.0

        # Build initial mask
        if fg_seed is None:
            mask = np.ones((h, w), dtype=np.uint8) * 255
            mask[bg_mask] = 0
        else:
            # Real-photo: start from confident FG only, then expand a bit.
            mask = np.zeros((h, w), dtype=np.uint8)
            mask[fg_seed] = 255

            try:
                import cv2

                mask = cv2.morphologyEx(
                    mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=2
                )
                mask = cv2.morphologyEx(
                    mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1
                )
            except Exception:
                pass

        # Real-photo extra: remove likely skin/hand pixels (common in "hand holding garment")
        if photo_type == "real_photo":
            try:
                import cv2

                bgr = cv2.cvtColor(img_array.astype(np.uint8), cv2.COLOR_RGB2BGR)
                ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
                y = ycrcb[:, :, 0]
                cr = ycrcb[:, :, 1]
                cb = ycrcb[:, :, 2]
                skin = (cr >= 130) & (cr <= 185) & (cb >= 80) & (cb <= 140) & (y >= 55)
                skin_u8 = skin.astype(np.uint8) * 255
                skin_u8 = cv2.morphologyEx(
                    skin_u8, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1
                )
                skin_u8 = cv2.morphologyEx(
                    skin_u8, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=2
                )

                # Only trust large-ish components (hands/arms); skip small warm-toned prints.
                num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
                    skin_u8, connectivity=8
                )
                if num_labels > 1:
                    min_area = max(250, int(h * w * 0.008))
                    large = np.zeros((h, w), dtype=bool)
                    for i in range(1, num_labels):
                        if stats[i, cv2.CC_STAT_AREA] >= min_area:
                            large |= labels == i
                    skin_u8 = large.astype(np.uint8) * 255

                # Remove skin only near image borders (hands enter from sides/top).
                border_band = max(10, min(h, w) // 14)
                near_border = np.zeros((h, w), dtype=bool)
                near_border[:border_band, :] = True
                near_border[-border_band:, :] = True
                near_border[:, :border_band] = True
                near_border[:, -border_band:] = True
                skin_border = (skin_u8 > 0) & near_border
                mask[skin_border] = 0

                # Also force obvious background (border-similar) to background.
                if "bg_mask" in locals() and bg_mask is not None:
                    mask[bg_mask] = 0
            except Exception as e:
                logger.info("Skin removal skipped (%s)", e)

            # Keep only the largest component (avoid background slabs).
            try:
                cc = self._largest_connected_component_mask((mask > 0).astype(np.uint8))
                mask = (cc * 255).astype(np.uint8)
            except Exception:
                pass

            # Hard background kill: anything too close to border mean must be background.
            # This prevents the "whole rectangular photo" from surviving as foreground.
            try:
                border = max(8, min(h, w) // 14)
                border_pixels = np.concatenate(
                    [
                        img_array[:border, :, :].reshape(-1, 3),
                        img_array[-border:, :, :].reshape(-1, 3),
                        img_array[:, :border, :].reshape(-1, 3),
                        img_array[:, -border:, :].reshape(-1, 3),
                    ],
                    axis=0,
                ).astype(np.float32)
                border_mean = border_pixels.mean(axis=0)
                dist = np.sqrt(np.sum((img_array.astype(np.float32) - border_mean) ** 2, axis=2))
                mask[dist < 22] = 0
                cc = self._largest_connected_component_mask((mask > 0).astype(np.uint8))
                mask = (cc * 255).astype(np.uint8)
            except Exception:
                pass

            # Real-photo extra: slightly expand foreground and fill small holes,
            # but never expand into confident background (bg_mask).
            try:
                import cv2

                mask = self._fill_binary_mask_holes(mask)
                expanded = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
                if "bg_mask" in locals() and bg_mask is not None:
                    expanded[bg_mask] = 0
                mask = expanded
            except Exception:
                pass

        pil_mask = PILImage.fromarray(mask, mode="L")
        for _ in range(grow_steps):
            pil_mask = pil_mask.filter(ImageFilter.MaxFilter(3))
        if blur_radius > 0:
            pil_mask = pil_mask.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        return pil_mask.resize((w, h), PILImage.Resampling.BILINEAR)

    def _refine_garment_mask_with_grabcut(self, garment_image: Image.Image) -> Image.Image:
        """
        Refine garment foreground locally with GrabCut.

        No model download required. We seed probable foreground from the old
        threshold mask, mark image borders as background, then let GrabCut clean
        edges and small holes.
        """
        import numpy as np
        from PIL import ImageFilter

        rgb = garment_image.convert("RGB")
        photo_type = self._classify_garment_photo_type(garment_image)
        coarse = self._generate_garment_mask_by_photo_type(garment_image, photo_type)
        coarse_arr = np.array(coarse, dtype=np.uint8)
        # Real photos need stricter seeds; otherwise everything becomes foreground.
        seed_fg = coarse_arr > (220 if photo_type == "real_photo" else 24)

        try:
            import cv2

            img = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)
            h, w = img.shape[:2]
            mask = np.full((h, w), cv2.GC_PR_BGD, dtype=np.uint8)

            # Real-photo: definite background on border-like pixels (avoid whole-image FG).
            if photo_type == "real_photo":
                try:
                    border = max(8, min(h, w) // 14)
                    border_pixels = np.concatenate(
                        [
                            img[:border, :, :].reshape(-1, 3),
                            img[-border:, :, :].reshape(-1, 3),
                            img[:, :border, :].reshape(-1, 3),
                            img[:, -border:, :].reshape(-1, 3),
                        ],
                        axis=0,
                    ).astype(np.float32)
                    border_mean = border_pixels.mean(axis=0)
                    dist = np.sqrt(np.sum((img.astype(np.float32) - border_mean) ** 2, axis=2))
                    bg_guard = dist < 20
                    mask[bg_guard] = cv2.GC_BGD
                except Exception as e:
                    logger.info("Real-photo bg guard skipped (%s)", e)

            border_x = max(6, w // 25)
            border_y = max(6, h // 25)
            mask[:border_y, :] = cv2.GC_BGD
            mask[-border_y:, :] = cv2.GC_BGD
            mask[:, :border_x] = cv2.GC_BGD
            mask[:, -border_x:] = cv2.GC_BGD

            inner = np.zeros((h, w), dtype=bool)
            inner[
                border_y : max(border_y + 1, h - border_y),
                border_x : max(border_x + 1, w - border_x),
            ] = True
            seed_fg &= inner
            mask[seed_fg] = cv2.GC_PR_FGD

            confident = self._largest_connected_component_mask(seed_fg.astype(np.uint8)).astype(
                bool
            )
            if confident.any():
                mask[confident] = cv2.GC_FGD
            else:
                rect = (
                    border_x,
                    border_y,
                    max(1, w - border_x * 2),
                    max(1, h - border_y * 2),
                )
                bgd_model = np.zeros((1, 65), np.float64)
                fgd_model = np.zeros((1, 65), np.float64)
                cv2.grabCut(img, mask, rect, bgd_model, fgd_model, 2, cv2.GC_INIT_WITH_RECT)

            bgd_model = np.zeros((1, 65), np.float64)
            fgd_model = np.zeros((1, 65), np.float64)
            cv2.grabCut(img, mask, None, bgd_model, fgd_model, 3, cv2.GC_INIT_WITH_MASK)

            out = np.where(
                (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD),
                255,
                0,
            ).astype(np.uint8)
            out = self._largest_connected_component_mask((out > 0).astype(np.uint8)) * 255

            kernel = np.ones((3, 3), np.uint8)
            out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, kernel, iterations=1)
            out = cv2.morphologyEx(out, cv2.MORPH_OPEN, kernel, iterations=1)

            # Real-photo extra: after grabcut, aggressively drop large border skin regions again.
            if photo_type == "real_photo":
                try:
                    ycrcb = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
                    y = ycrcb[:, :, 0]
                    cr = ycrcb[:, :, 1]
                    cb = ycrcb[:, :, 2]
                    skin = (cr >= 130) & (cr <= 185) & (cb >= 80) & (cb <= 140) & (y >= 55)
                    skin_u8 = skin.astype(np.uint8) * 255
                    skin_u8 = cv2.morphologyEx(
                        skin_u8, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=2
                    )
                    border_band = max(10, min(h, w) // 14)
                    near_border = np.zeros((h, w), dtype=bool)
                    near_border[:border_band, :] = True
                    near_border[-border_band:, :] = True
                    near_border[:, :border_band] = True
                    near_border[:, -border_band:] = True
                    out[(skin_u8 > 0) & near_border] = 0
                except Exception as e:
                    logger.info("Post skin removal skipped (%s)", e)

                # Fill holes + expand slightly, but guard against border-like background.
                try:
                    # bg_guard is recomputed for safety
                    border = max(8, min(h, w) // 14)
                    border_pixels = np.concatenate(
                        [
                            img[:border, :, :].reshape(-1, 3),
                            img[-border:, :, :].reshape(-1, 3),
                            img[:, :border, :].reshape(-1, 3),
                            img[:, -border:, :].reshape(-1, 3),
                        ],
                        axis=0,
                    ).astype(np.float32)
                    border_mean = border_pixels.mean(axis=0)
                    dist = np.sqrt(np.sum((img.astype(np.float32) - border_mean) ** 2, axis=2))
                    bg_guard = dist < 20

                    out = self._fill_binary_mask_holes(out)
                    out = cv2.dilate(out, np.ones((3, 3), np.uint8), iterations=1)
                    out[bg_guard] = 0
                    out = self._largest_connected_component_mask((out > 0).astype(np.uint8)) * 255
                except Exception as e:
                    logger.info("Post fill/expand skipped (%s)", e)

            # Slight feathering after refinement; keep it small to avoid re-introducing background.
            pil_mask = Image.fromarray(out, mode="L").filter(ImageFilter.GaussianBlur(radius=0.9))
            logger.info(f"Garment cutout photo_type={photo_type}")
            return pil_mask
        except Exception as e:
            logger.info("GrabCut unavailable (%s); using local threshold mask", e)
            return coarse

    def _crop_to_alpha_bbox(self, im: Image.Image) -> Image.Image:
        """按不透明区域裁剪，减少整图空白边。"""
        if im.mode != "RGBA":
            im = im.convert("RGBA")
        # IMPORTANT: use a hard alpha threshold to avoid "whole image bbox"
        # when the mask has faint non-zero alpha everywhere (common on real photos).
        a = im.split()[3]
        a_bin = a.point(lambda p: 255 if p >= 200 else 0)
        bbox = a_bin.getbbox()
        if bbox:
            return im.crop(bbox)
        return im

    def _soften_alpha_edges(self, im: Image.Image, blur_radius: int = 3) -> Image.Image:
        """Slightly feather alpha edges so fallback paste looks less harsh."""
        from PIL import ImageFilter

        if im.mode != "RGBA":
            im = im.convert("RGBA")
        r, g, b, a = im.split()
        a = a.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        out = Image.merge("RGBA", (r, g, b, a))
        return out

    def _compute_fallback_overlay_box(
        self,
        person_size: tuple[int, int],
        garment_size: tuple[int, int],
        placement: Optional[str] = None,
    ) -> tuple[int, int, int, int]:
        """
        Compute a torso-biased overlay box for fallback composition.

        Heuristics favor upper-body for tops; very tall/narrow cutouts (typical flat-lay
        pants) are anchored lower with a smaller max height so they do not cover the face.
        When placement is "bottom" or "top", category overrides ambiguous aspect.
        """
        pw, ph = person_size
        gw, gh = garment_size
        aspect = gh / max(float(gw), 1.0)

        width_ratio: float
        top_ratio: float
        max_height_ratio: float

        if placement == "bottom":
            # Waist/hip downward; cap height so flat-lay trousers do not eat the torso.
            if aspect >= 2.05:
                width_ratio, top_ratio, max_height_ratio = 0.56, 0.44, 0.48
            elif aspect >= 1.35:
                width_ratio, top_ratio, max_height_ratio = 0.57, 0.42, 0.52
            else:
                width_ratio, top_ratio, max_height_ratio = 0.56, 0.40, 0.50
        elif placement == "top":
            width_ratio, top_ratio, max_height_ratio = 0.52, 0.10, 0.55
        else:
            # Tall narrow → likely trousers / long bottoms (flat lay); start near waist/hip.
            if aspect >= 2.05:
                width_ratio = 0.56
                top_ratio = 0.40
                max_height_ratio = 0.50
            elif aspect >= 1.75:
                width_ratio = 0.57
                top_ratio = 0.32
                max_height_ratio = 0.56
            elif aspect >= 1.45:
                width_ratio = 0.58
                top_ratio = 0.22
                max_height_ratio = 0.64
            elif aspect >= 1.1:
                width_ratio = 0.54
                top_ratio = 0.13
                max_height_ratio = 0.64
            else:
                width_ratio = 0.50
                top_ratio = 0.10
                max_height_ratio = 0.52

        tw = max(48, int(round(pw * width_ratio)))
        th = int(round(gh * (tw / max(float(gw), 1.0))))
        max_h = max(64, int(round(ph * max_height_ratio)))
        if th > max_h:
            th = max_h
            tw = max(48, int(round(gw * (th / max(float(gh), 1.0)))))

        x = (pw - tw) // 2
        y = int(round(ph * top_ratio))
        y = max(0, min(y, max(0, ph - th)))
        x = max(0, min(x, max(0, pw - tw)))
        return x, y, tw, th

    def _protected_head_box(self, person_size: tuple[int, int]) -> tuple[int, int, int, int]:
        """
        Head/face protection region for fallback paste.

        We avoid relying on Haar cascade data (often missing on Windows installs).
        Instead, reserve a conservative top-center box as "do not paint" so the
        garment overlay cannot cover the face.
        """
        pw, ph = person_size
        x0 = int(round(pw * 0.28))
        x1 = int(round(pw * 0.72))
        y0 = int(round(ph * 0.00))
        y1 = int(round(ph * 0.26))
        return x0, y0, x1, y1

    def _apply_head_protection_to_overlay(
        self,
        overlay_rgba: Image.Image,
        *,
        paste_xy: tuple[int, int],
        person_size: tuple[int, int],
    ) -> Image.Image:
        """Zero-out overlay alpha where it would cover the protected head box."""
        if overlay_rgba.mode != "RGBA":
            overlay_rgba = overlay_rgba.convert("RGBA")

        px, py = paste_xy
        pw, ph = person_size
        hx0, hy0, hx1, hy1 = self._protected_head_box((pw, ph))

        ox0 = max(0, hx0 - px)
        oy0 = max(0, hy0 - py)
        ox1 = min(overlay_rgba.size[0], hx1 - px)
        oy1 = min(overlay_rgba.size[1], hy1 - py)

        if ox1 <= ox0 or oy1 <= oy0:
            return overlay_rgba

        from PIL import ImageDraw

        r, g, b, a = overlay_rgba.split()
        draw = ImageDraw.Draw(a)
        draw.rectangle([ox0, oy0, ox1, oy1], fill=0)
        return Image.merge("RGBA", (r, g, b, a))

    def _shift_overlay_below_head_if_needed(
        self,
        *,
        paste_xywh: tuple[int, int, int, int],
        person_size: tuple[int, int],
    ) -> tuple[int, int, int, int]:
        """If overlay would cover head area too much, push it down."""
        x, y, tw, th = paste_xywh
        pw, ph = person_size
        hx0, hy0, hx1, hy1 = self._protected_head_box((pw, ph))

        ox0, oy0, ox1, oy1 = x, y, x + tw, y + th
        ix0, iy0 = max(ox0, hx0), max(oy0, hy0)
        ix1, iy1 = min(ox1, hx1), min(oy1, hy1)
        if ix1 <= ix0 or iy1 <= iy0:
            return x, y, tw, th

        overlap_h = iy1 - iy0
        # push down enough so overlap becomes small (but keep within canvas)
        target_overlap = int(round(ph * 0.02))
        need = max(0, overlap_h - target_overlap)
        if need <= 0:
            return x, y, tw, th

        new_y = min(max(0, ph - th), y + need)
        return x, new_y, tw, th

    def _apply_upper_body_cutoff_to_overlay(
        self,
        overlay_rgba: Image.Image,
        *,
        paste_y: int,
        person_height: int,
        cutoff_ratio: float = 0.42,
    ) -> Image.Image:
        """For bottoms: clear alpha above ``cutoff_ratio`` of person height (keep shirt visible)."""
        if overlay_rgba.mode != "RGBA":
            overlay_rgba = overlay_rgba.convert("RGBA")
        cutoff_y = int(round(person_height * cutoff_ratio))
        # Rows of overlay that fall entirely above cutoff_y in person coords.
        clear_below_row = max(0, cutoff_y - paste_y)
        if clear_below_row <= 0:
            return overlay_rgba
        w, h = overlay_rgba.size
        if clear_below_row >= h:
            return Image.new("RGBA", (w, h), (0, 0, 0, 0))

        r, g, b, a = overlay_rgba.split()
        top = Image.new("L", (w, clear_below_row), 0)
        bottom = a.crop((0, clear_below_row, w, h))
        a = Image.new("L", (w, h))
        a.paste(top, (0, 0))
        a.paste(bottom, (0, clear_below_row))
        return Image.merge("RGBA", (r, g, b, a))

    def _paste_garment_on_person(
        self,
        person_image: Image.Image,
        garment_rgba: Image.Image,
        garment_category: Optional[str] = None,
    ) -> Image.Image:
        """将抠图衣服按 alpha 粘贴到人像躯干区域（不使用全图半透明叠图）。"""
        g = self._crop_to_alpha_bbox(garment_rgba)
        pw, ph = person_image.size
        gw, gh = g.size
        if gw < 8 or gh < 8:
            raise ValueError("Garment cutout too small after background removal")

        placement = _infer_fallback_placement(garment_category)
        x, y, tw, th = self._compute_fallback_overlay_box((pw, ph), (gw, gh), placement)
        x, y, tw, th = self._shift_overlay_below_head_if_needed(
            paste_xywh=(x, y, tw, th), person_size=(pw, ph)
        )
        # Long flat-lay bottoms / category bottom: never anchor above upper torso.
        aspect_g = gh / max(float(gw), 1.0)
        _, _, _, hy1 = self._protected_head_box((pw, ph))
        if placement == "bottom" or aspect_g >= 1.65:
            min_y = max(int(round(hy1)), int(round(ph * 0.36)))
            y = max(y, min_y)
            y = min(max(0, ph - th), y)
        g = g.resize((tw, th), Image.Resampling.LANCZOS)
        g = self._soften_alpha_edges(g, blur_radius=2)
        if placement == "bottom":
            g = self._apply_upper_body_cutoff_to_overlay(
                g, paste_y=y, person_height=ph, cutoff_ratio=0.42
            )
        g = self._apply_head_protection_to_overlay(g, paste_xy=(x, y), person_size=(pw, ph))
        base = person_image.convert("RGBA")
        base.paste(g, (x, y), g)
        return base.convert("RGB")

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _generate_garment_mask(self, garment_image: Image.Image) -> Image.Image:
        """
        Backward-compatible coarse garment mask entrypoint.
        """
        photo_type = self._classify_garment_photo_type(garment_image)
        return self._generate_garment_mask_by_photo_type(garment_image, photo_type)

    def _build_tryon_prompt(self, garment_image: Image.Image, model_gender: str = "neutral") -> str:
        """
        Build a gender-aware text prompt for try-on based on garment analysis.
        无性别推荐系统: 根据 model_gender 生成适合的提示词

        Args:
            garment_image: Garment image (unused, for future CLIP analysis)
            model_gender: "male" / "female" / "neutral"
        """
        gender_prompts = {
            "male": (
                "a man wearing the garment, full body photo, masculine build, "
                "high quality, realistic, natural lighting, "
                "professional fashion photography"
            ),
            "female": (
                "a woman wearing the garment, full body photo, feminine build, "
                "high quality, realistic, natural lighting, "
                "professional fashion photography"
            ),
            "neutral": (
                "a person wearing the garment, full body photo, "
                "high quality, realistic, natural lighting, "
                "professional fashion photography"
            ),
        }
        return gender_prompts.get(model_gender, gender_prompts["neutral"])

    def _inject_gender_into_prompt(self, prompt: str, model_gender: str) -> str:
        """
        Inject gender information into an existing prompt.
        用于用户自定义 prompt 时注入性别信息
        """
        if model_gender == "neutral":
            return prompt

        gender_phrases = {
            "male": ["a man", "man wearing", "male model", "he is wearing"],
            "female": ["a woman", "woman wearing", "female model", "she is wearing"],
        }

        phrases = gender_phrases.get(model_gender, [])
        for phrase in phrases:
            if phrase.lower() not in prompt.lower():
                # Prepend gender context
                prefix = {
                    "male": "A man: ",
                    "female": "A woman: ",
                }.get(model_gender, "")
                return prefix + prompt

        return prompt

    def _compute_cache_key(
        self,
        garment_image: Image.Image,
        person_image: Image.Image,
        prompt: Optional[str],
        model_gender: str = "neutral",
        garment_category: Optional[str] = None,
    ) -> str:
        """Compute cache key from image hashes + prompt + model_gender + garment_category."""
        import io

        buf_g = io.BytesIO()
        buf_p = io.BytesIO()
        garment_image.save(buf_g, format="PNG")
        person_image.save(buf_p, format="PNG")
        key_str = hashlib.md5(buf_g.getvalue() + buf_p.getvalue()).hexdigest()
        key_str += hashlib.md5(model_gender.encode()).hexdigest()[:8]
        key_str += hashlib.md5(FALLBACK_PIPELINE_VERSION.encode()).hexdigest()[:8]
        if prompt:
            key_str += hashlib.md5(prompt.encode()).hexdigest()[:8]
        cat = (garment_category or "").strip()
        if cat:
            key_str += hashlib.md5(cat.encode("utf-8")).hexdigest()[:8]
        return key_str

    # ─── Multi-Garment Try-On ───────────────────────────────────────────────

    def tryon_outfit(
        self, garments: list, person_image: Image.Image, scene: str = "休闲", **kwargs
    ) -> dict:
        """
        Try on multiple garments (full outfit) on a person.

        Args:
            garments: List of garment images (PIL Image or dict with 'image' key)
            person_image: Person photo
            scene: Scene context for prompt ("通勤", "约会", etc.)
            **kwargs: Additional arguments passed to tryon_garment

        Returns:
            Dict with combined try-on result
        """
        logger.info(f"Trying on {len(garments)} garments for scene: {scene}")

        if not garments:
            return {
                "result_image": person_image,
                "status": "error",
                "message": "没有提供服饰图片",
                "metadata": {
                    "reason": "empty_garments",
                },
            }

        scene_prompts = {
            "通勤": "professional office wear, business casual",
            "约会": "elegant romantic outfit, stylish date wear",
            "休闲": "casual relaxed outfit, everyday style",
            "运动": "athletic sportswear, gym outfit",
            "正式": "formal elegant outfit, sophisticated look",
            "派对": "party fashion, glamorous outfit",
            "度假": "vacation resort wear, tropical outfit",
        }
        prompt_suffix = scene_prompts.get(scene, "high quality fashion photo")

        # Try on each garment sequentially (can be parallelized in production)
        current_result = person_image

        for _, garment in enumerate(garments):
            if isinstance(garment, dict):
                gar_img = garment.get("image")
            else:
                gar_img = garment

            if gar_img is None:
                continue

            results = self.tryon_garment(
                garment_image=gar_img,
                person_image=current_result,
                prompt=f"wearing {prompt_suffix}, high quality realistic fashion photo",
                **kwargs,
            )

            # Use result as input for next garment
            if results["status"] in ("success", "fallback") and results["result_image"]:
                current_result = results["result_image"]

        # Return the final composite
        return {
            "result_image": current_result,
            "status": "success",
            "message": f"完整套装试穿完成（{len(garments)}件服饰）",
            "metadata": {
                "garment_count": len(garments),
                "scene": scene,
            },
        }

    def clear_cache(self):
        """Clear the in-memory cache."""
        self._cache.clear()
        logger.info("VirtualTryOn cache cleared")


# ──────────────────────────────────────────────────────────────────────────────
# Global singleton
# ──────────────────────────────────────────────────────────────────────────────
_tryon_instance: Optional[VirtualTryOnService] = None


def get_tryon_service() -> VirtualTryOnService:
    """Get or create the global VirtualTryOnService singleton."""
    global _tryon_instance
    if _tryon_instance is None:
        _tryon_instance = VirtualTryOnService()
    return _tryon_instance


def check_tryon_garment_has_face(garment_image: Image.Image) -> bool:
    """True if the garment product photo likely contains a face (reject before upstream APIs)."""
    svc = get_tryon_service()
    fn = getattr(svc, "_garment_has_face", None)
    if fn is None:
        return False
    return bool(fn(garment_image))
