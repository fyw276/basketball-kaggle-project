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
from typing import Optional

from PIL import Image

from app.core.logging import setup_logging

logger = setup_logging()

# ──────────────────────────────────────────────────────────────────────────────
# Model Configuration
# ──────────────────────────────────────────────────────────────────────────────

# HuggingFace SD-VTON model (or compatible Stable Diffusion ControlNet for try-on)
# Available models on HuggingFace:
# - "timbeck7/SD-VTON" — Stable Diffusion Virtual Try-On
# - "lllyasviel/sd-controlnet-openpose" — ControlNet for pose-guided try-on
# - "stabilityai/stable-diffusion-2-inpainting" — SD 2.0 inpainting
#   (often gated; requires HF auth + acceptance)
# - "runwayml/stable-diffusion-inpainting" — public inpainting baseline (recommended default)
SD_VTON_MODEL_ID = os.environ.get("SD_VTON_MODEL_ID", "runwayml/stable-diffusion-inpainting")

# ControlNet model for pose/segmentation guidance
CONTROLNET_MODEL_ID = os.environ.get("CONTROLNET_MODEL_ID", "lllyasviel/control_v11p_sd15_openpose")

# Inference settings
DEFAULT_STEPS = 25
DEFAULT_GUIDANCE_SCALE = 7.5
FALLBACK_PIPELINE_VERSION = os.environ.get("TRYON_FALLBACK_PIPELINE_VERSION", "fallback_paste_v1")


def sanitize_tryon_prompt(prompt: Optional[str]) -> str:
    """Sanitize user prompt to avoid control chars and excessive length."""
    s = (prompt or "").strip()
    if not s:
        return ""

    buf = []
    for ch in s:
        code = ord(ch)
        if code in (9, 10, 13):
            buf.append(" ")
        elif code < 32:
            continue
        else:
            buf.append(ch)

    s = "".join(buf)
    s = " ".join(s.split())
    return s[:500]


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

        # Check if we have the necessary dependencies
        try:
            import torch  # noqa: F401 - required for torch_dtype
            from diffusers import StableDiffusionInpaintPipeline

            logger.info(f"Loading Stable Diffusion inpainting model on {self.device}")
            self._model = StableDiffusionInpaintPipeline.from_pretrained(
                SD_VTON_MODEL_ID,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                safety_checker=None,
                feature_extractor=None,
                requires_safety_checker=False,
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
            logger.warning(f"Failed to load try-on model: {e}")
            self._is_available = False
            return False

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
        force_fallback: bool = False,
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

        # Check cache (include model_gender in cache key)
        cache_key = self._compute_cache_key(garment_image, person_image, prompt, model_gender)
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

        # Identity-preserving mode: skip diffusion and use fallback paste directly.
        if force_fallback:
            out = self._tryon_fallback(
                garment_image,
                person_image,
                prompt,
                cache_key,
                model_gender,
                garment_category,
            )
            meta = out.get("metadata") if isinstance(out, dict) else None
            if isinstance(meta, dict):
                meta["reason"] = "forced_identity_preservation"
            return out

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
                garment_category,
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
                    "model": SD_VTON_MODEL_ID,
                    "device": self.device,
                },
            }

        output = {
            "result_image": result,
            "status": "success",
            "message": f"虚拟试穿成功完成 (model_gender={model_gender})",
            "metadata": {
                "model": SD_VTON_MODEL_ID,
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
            result = self._paste_garment_on_person(person_image, garment_rgba)

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
                    "reason": "model_unavailable",
                    "garment_category": (garment_category or "").strip() or None,
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
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            cascade = cv2.CascadeClassifier(cascade_path)
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
        except Exception as e:
            logger.info("rembg unavailable (%s); using local mask for garment alpha", e)

        mask_l = self._generate_garment_mask(garment_image)
        rgba = rgb.convert("RGBA")
        rgba.putalpha(mask_l)
        logger.info("Garment cutout: local threshold mask")
        return rgba

    def _crop_to_alpha_bbox(self, im: Image.Image) -> Image.Image:
        """按不透明区域裁剪，减少整图空白边。"""
        if im.mode != "RGBA":
            im = im.convert("RGBA")
        bbox = im.split()[3].getbbox()
        if bbox:
            return im.crop(bbox)
        return im

    def _paste_garment_on_person(
        self,
        person_image: Image.Image,
        garment_rgba: Image.Image,
    ) -> Image.Image:
        """将抠图衣服按 alpha 粘贴到人像躯干区域（不使用全图半透明叠图）。"""
        g = self._crop_to_alpha_bbox(garment_rgba)
        pw, ph = person_image.size
        gw, gh = g.size
        if gw < 8 or gh < 8:
            raise ValueError("Garment cutout too small after background removal")

        tw = max(32, int(pw * 0.50))
        th = int(round(gh * (tw / float(gw))))
        max_h = int(ph * 0.58)
        if th > max_h:
            th = max_h
            tw = max(32, int(round(gw * (th / float(gh)))))
        g = g.resize((tw, th), Image.Resampling.LANCZOS)

        x = (pw - tw) // 2
        y = int(ph * 0.07)
        base = person_image.convert("RGBA")
        base.paste(g, (x, y), g)
        return base.convert("RGB")

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _generate_garment_mask(self, garment_image: Image.Image) -> Image.Image:
        """
        Generate a simple garment mask using color thresholding.
        For production, use a dedicated garment segmentation model (e.g., BiRefNet).
        """
        import numpy as np
        from PIL import Image as PILImage
        from PIL import ImageFilter

        img_array = np.array(garment_image.convert("RGB"))
        h, w = img_array.shape[:2]

        mask = np.ones((h, w), dtype=np.uint8) * 255

        # Detect background: very bright + low-saturation pixels = likely background
        gray = np.mean(img_array, axis=2)
        sat = np.std(img_array, axis=2)
        bg_mask = (gray > 230) & (sat < 15)
        mask[bg_mask] = 0

        # Inflate foreground slightly without scipy dependency.
        pil_mask = PILImage.fromarray(mask, mode="L")
        for _ in range(3):
            pil_mask = pil_mask.filter(ImageFilter.MaxFilter(3))

        return pil_mask.resize((w, h), PILImage.Resampling.BILINEAR)

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
    ) -> str:
        """Compute cache key from image hashes + prompt + model_gender."""
        import io

        buf_g = io.BytesIO()
        buf_p = io.BytesIO()
        garment_image.save(buf_g, format="PNG")
        person_image.save(buf_p, format="PNG")
        key_str = hashlib.md5(buf_g.getvalue() + buf_p.getvalue()).hexdigest()
        key_str += hashlib.md5(model_gender.encode()).hexdigest()[:8]
        if prompt:
            key_str += hashlib.md5(prompt.encode()).hexdigest()[:8]
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
    """Public helper used by API guardrail before trying any upstream engine."""
    try:
        return get_tryon_service()._garment_has_face(garment_image)
    except Exception as e:
        logger.warning("Garment face check helper failed: %s", e)
        return False
