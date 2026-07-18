"""SCHP Human Parsing for accurate garment region segmentation.

SCHP (Self-Corrected Human Parsing) provides semantic part segmentation
that knows exactly where shoulders, arms, torso, etc. are — unlike
MediaPipe body masks which are coarse.

Installation:
    pip install torch torchvision transformers pillow

Usage:
    from app.services.human_parsing import schp_parse, SCHPParser

    parser = SCHPParser()
    result = parser.parse_person(image)
    upper_mask = result["upper_clothes"]
    arm_mask = result["left_arm"] + result["right_arm"]
    final_mask = upper_mask + arm_mask
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
import types
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

__all__ = ["schp_parse", "SCHPParser"]

logger = logging.getLogger(__name__)

# SCHP LIP input conventions (from pirocheto/schp-lip-20 image processor)
_SCHP_INPUT_SIZE = 473
_SCHP_MEAN = [0.406, 0.456, 0.485]
_SCHP_STD = [0.225, 0.224, 0.229]


# LIP dataset labels (20 classes) from pirocheto/schp-lip-20
# Index → label name mapping
LIP_LABELS = [
    "background",  # 0
    "hat",  # 1
    "hair",  # 2
    "glove",  # 3
    "sunglasses",  # 4
    "upper_clothes",  # 5
    "dress",  # 6
    "coat",  # 7
    "socks",  # 8
    "pants",  # 9
    "jumpsuits",  # 10
    "scarf",  # 11
    "skirt",  # 12
    "face",  # 13
    "left_arm",  # 14
    "right_arm",  # 15
    "left_leg",  # 16
    "right_leg",  # 17
    "left_shoe",  # 18
    "right_shoe",  # 19
]

# Label indices relevant to try-on
_UPPER_CLOTHES_IDX = {5, 6, 7}  # upper_clothes, dress, coat
_LOWER_GARMENT_IDX = {9, 12}  # pants, skirt
_LEFT_ARM_IDX = {14}
_RIGHT_ARM_IDX = {15}
_LEFT_LEG_IDX = {16}  # left_leg only (exclude shoes for lower try-on)
_RIGHT_LEG_IDX = {17}  # right_leg only
_LEFT_SHOE_IDX = {18}
_RIGHT_SHOE_IDX = {19}
_FACE_IDX = {13}
_HAIR_IDX = {2}


class SCHPResult:
    """Result of SCHP human parsing."""

    def __init__(
        self,
        parsing_map: np.ndarray,
        labels: list[str],
        source: str = "unknown",
    ):
        self.parsing_map = parsing_map
        self.labels = labels
        self.source = source

    def get_mask(self, *class_indices: int) -> np.ndarray:
        """Return binary mask (HxW float 0-1) for given class indices."""
        mask = np.zeros_like(self.parsing_map, dtype=np.float32)
        for idx in class_indices:
            mask[self.parsing_map == idx] = 1.0
        return mask

    @property
    def upper_clothes(self) -> np.ndarray:
        return self.get_mask(*_UPPER_CLOTHES_IDX)

    @property
    def left_arm(self) -> np.ndarray:
        return self.get_mask(*_LEFT_ARM_IDX)

    @property
    def right_arm(self) -> np.ndarray:
        return self.get_mask(*_RIGHT_ARM_IDX)

    @property
    def lower_garment(self) -> np.ndarray:
        return self.get_mask(*_LOWER_GARMENT_IDX)

    @property
    def left_leg(self) -> np.ndarray:
        return self.get_mask(*_LEFT_LEG_IDX)

    @property
    def right_leg(self) -> np.ndarray:
        return self.get_mask(*_RIGHT_LEG_IDX)

    @property
    def left_shoe(self) -> np.ndarray:
        return self.get_mask(*_LEFT_SHOE_IDX)

    @property
    def right_shoe(self) -> np.ndarray:
        return self.get_mask(*_RIGHT_SHOE_IDX)

    @property
    def face(self) -> np.ndarray:
        return self.get_mask(*_FACE_IDX)

    @property
    def hair(self) -> np.ndarray:
        return self.get_mask(*_HAIR_IDX)

    def top_region(self) -> np.ndarray:
        """Combined mask for upper garment + arms (top try-on area)."""
        return self.upper_clothes + self.left_arm + self.right_arm

    def bottom_region(self) -> np.ndarray:
        """Combined mask for lower garment + legs (exclude shoes)."""
        return self.lower_garment + self.left_leg + self.right_leg

    def as_dict(self) -> dict[str, np.ndarray]:
        return {
            "upper_clothes": self.upper_clothes,
            "left_arm": self.left_arm,
            "right_arm": self.right_arm,
            "lower_garment": self.lower_garment,
            "left_leg": self.left_leg,
            "right_leg": self.right_leg,
            "top_region": self.top_region(),
            "bottom_region": self.bottom_region(),
        }


def _candidate_paths(*parts: str) -> list[Path]:
    roots: list[Path] = []
    for key in ("CATVTON_PATH", "HF_HOME", "TRANSFORMERS_CACHE"):
        val = (os.environ.get(key) or "").strip()
        if val:
            roots.append(Path(val))
    roots.extend(
        [
            Path(r"D:\models\CatVTON_full"),
            Path(r"D:\hf-cache"),
            Path.home() / ".cache" / "huggingface",
        ]
    )
    try:
        from app.core.config import settings

        cat_path = (getattr(settings, "CATVTON_PATH", "") or "").strip()
        if cat_path:
            roots.insert(0, Path(cat_path))
    except Exception:
        pass

    out: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        p = root.joinpath(*parts)
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _find_lip_checkpoint() -> Path | None:
    for p in _candidate_paths("SCHP", "exp-schp-201908261155-lip.pth"):
        if p.is_file():
            return p
    # Search CatVTON HF cache snapshots for the lip weight
    for root in _candidate_paths("hub", "models--zhengchong--CatVTON", "snapshots"):
        if not root.is_dir():
            continue
        for snap in root.iterdir():
            cand = snap / "SCHP" / "exp-schp-201908261155-lip.pth"
            if cand.is_file():
                return cand
    return None


def _find_schp_remote_file(filename: str) -> Path | None:
    """Locate modeling/config files from the HuggingFace cache (offline-friendly)."""
    patterns = [
        ("transformers", "models--pirocheto--schp-lip-20", "snapshots"),
        ("hub", "models--pirocheto--schp-lip-20", "snapshots"),
        ("modules", "transformers_modules", "pirocheto", "schp-lip-20"),
    ]
    for parts in patterns:
        for root in _candidate_paths(*parts):
            if not root.exists():
                continue
            if root.is_file() and root.name == filename:
                return root
            if root.is_dir():
                direct = root / filename
                if direct.is_file():
                    return direct
                for snap in root.iterdir():
                    cand = snap / filename
                    if cand.is_file():
                        return cand
    return None


def _install_schp_config_shim(config_path: Path) -> None:
    """Satisfy `from schp.configuration_schp import SCHPConfig` used by modeling_schp.py."""
    if "schp.configuration_schp" in sys.modules:
        return
    pkg = types.ModuleType("schp")
    pkg.__path__ = []  # type: ignore[attr-defined]
    sys.modules["schp"] = pkg
    spec = importlib.util.spec_from_file_location("schp.configuration_schp", config_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load SCHP config from {config_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["schp.configuration_schp"] = mod
    spec.loader.exec_module(mod)


def _load_schp_modeling(modeling_path: Path):
    _install_schp_config_shim(
        _find_schp_remote_file("configuration_schp.py")
        or modeling_path.with_name("configuration_schp.py")
    )
    mod_name = "clothing_assistant_schp_modeling"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, modeling_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load SCHP modeling from {modeling_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _preprocess_schp_image(image: Image.Image, device: str):
    """Match pirocheto SCHPImageProcessor (473x473 + BGR-indexed mean/std)."""
    import torchvision.transforms.functional as TF

    pil = image.convert("RGB").resize(
        (_SCHP_INPUT_SIZE, _SCHP_INPUT_SIZE), Image.Resampling.BILINEAR
    )
    t = TF.to_tensor(pil)
    t = TF.normalize(t, mean=_SCHP_MEAN, std=_SCHP_STD)
    return t.unsqueeze(0).to(device)


class SCHPParser:
    """Human parsing using SCHP (Self-Corrected Human Parsing).

    Preferred load order:
      1. Local CatVTON LIP `.pth` + cached modeling_schp.py (offline / no pip `schp`)
      2. HuggingFace `pirocheto/schp-lip-20` via transformers (when network + deps OK)
      3. Heuristic GrabCut fallback (rejected by lower-mask QA)
    """

    def __init__(self, model_name: str = "pirocheto/schp-lip-20"):
        self.model_name = model_name
        self._model = None
        self._processor = None
        self._device = "cpu"
        self._source = "unknown"

    def _load_model(self):
        """Lazy-load SCHP — prefer local CatVTON LIP weights."""
        if self._model is not None:
            return

        errors: list[str] = []
        try:
            self._load_from_local_lip_checkpoint()
            return
        except Exception as e:
            errors.append(f"local_lip: {e}")
            logger.warning("[SCHP] local LIP checkpoint load failed: %s", e)

        try:
            self._load_from_transformers_hub()
            return
        except Exception as e:
            errors.append(f"transformers_hub: {e}")
            logger.warning("[SCHP] transformers hub load failed: %s", e)

        self._model = None
        self._processor = None
        raise RuntimeError("; ".join(errors) or "Failed to load SCHP model")

    def _load_from_local_lip_checkpoint(self) -> None:
        import torch

        ckpt = _find_lip_checkpoint()
        if ckpt is None:
            raise FileNotFoundError("CatVTON LIP SCHP checkpoint not found")
        modeling_path = _find_schp_remote_file("modeling_schp.py")
        config_path = _find_schp_remote_file("configuration_schp.py")
        if modeling_path is None or config_path is None:
            raise FileNotFoundError(
                "Cached modeling_schp.py / configuration_schp.py not found under HF_HOME"
            )

        modeling = _load_schp_modeling(modeling_path)
        config_mod = sys.modules["schp.configuration_schp"]
        config = config_mod.SCHPConfig(num_labels=20)
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model = modeling.SCHPForSemanticSegmentation.from_schp_checkpoint(
            str(ckpt),
            config=config,
            map_location=self._device,
        )
        self._model.to(self._device)
        self._model.eval()
        self._processor = None  # use built-in preprocessor
        self._source = "schp_local_lip"
        logger.info("[SCHP] loaded local LIP checkpoint: %s (device=%s)", ckpt, self._device)

    def _load_from_transformers_hub(self) -> None:
        import torch
        from transformers import AutoImageProcessor, AutoModelForSemanticSegmentation

        self._processor = AutoImageProcessor.from_pretrained(
            self.model_name,
            trust_remote_code=True,
        )
        self._model = AutoModelForSemanticSegmentation.from_pretrained(
            self.model_name,
            trust_remote_code=True,
        )
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model.to(self._device)
        self._model.eval()
        self._source = "schp_transformers"

    def parse_person(self, image: Image.Image) -> SCHPResult:
        """
        Parse a person image into semantic body parts.

        Args:
            image: PIL RGB image of a person.

        Returns:
            SCHPResult with body-part masks.
        """
        try:
            self._load_model()
        except RuntimeError:
            return self._heuristic_parsing(image)

        if self._model is None:
            return self._heuristic_parsing(image)

        try:
            import torch

            orig_w, orig_h = image.size

            if self._processor is not None:
                inputs = self._processor(images=image, return_tensors="pt")
                inputs = {k: v.to(self._device) for k, v in inputs.items()}
                with torch.no_grad():
                    outputs = self._model(**inputs)
            else:
                pixel_values = _preprocess_schp_image(image, self._device)
                with torch.no_grad():
                    outputs = self._model(pixel_values=pixel_values)

            logits = outputs.logits if hasattr(outputs, "logits") else outputs[0]
            pred = logits.argmax(dim=1).squeeze(0).cpu().numpy()

            pred = Image.fromarray(pred.astype(np.uint8)).resize((orig_w, orig_h), Image.NEAREST)
            parsing_map = np.array(pred, dtype=np.int32)

            return SCHPResult(parsing_map, LIP_LABELS, source=self._source or "schp_transformers")

        except Exception as e:
            logger.warning("[SCHP] parse_person failed, heuristic fallback: %s", e)
            return self._heuristic_parsing(image)

    def _heuristic_parsing(self, image: Image.Image) -> SCHPResult:
        """
        Fallback: use GrabCut body segmentation to create pseudo-SCHP masks.
        This separates upper/lower/arms based on body proportions.
        """

        arr = np.array(image.convert("RGB"))
        h, w = arr.shape[:2]

        mask = self._get_body_mask(image)

        parsing_map = np.zeros((h, w), dtype=np.int32)

        torso_top = int(h * 0.18)
        torso_bot = int(h * 0.52)
        parsing_map[torso_top:torso_bot, :] = 5  # upper_clothes

        arm_top = int(h * 0.18)
        arm_bot = int(h * 0.55)
        arm_w = int(w * 0.18)
        parsing_map[arm_top:arm_bot, :arm_w] = 14  # left_arm
        parsing_map[arm_top:arm_bot, w - arm_w :] = 15  # right_arm

        lower_top = int(h * 0.48)
        lower_bot = int(h * 0.98)
        parsing_map[lower_top:lower_bot, :] = 9  # pants

        body_mask = (mask > 0.3).astype(np.float32)
        if body_mask.ndim == 2:
            body_mask = body_mask[:, :, None]
        parsing_map = (parsing_map * body_mask[:, :, 0].astype(np.int32)).astype(np.int32)

        return SCHPResult(parsing_map, LIP_LABELS, source="heuristic_grabcut")

    def _get_body_mask(self, image: Image.Image) -> np.ndarray:
        """Get a rough body foreground mask using GrabCut."""

        arr = np.array(image.convert("RGB"))
        h, w = arr.shape[:2]

        mask = np.zeros((h, w), np.uint8)
        bgd_model = np.zeros((1, 65), np.float64)
        fgd_model = np.zeros((1, 65), np.float64)
        rect = (int(w * 0.05), int(h * 0.05), int(w * 0.90), int(h * 0.92))

        try:
            cv2.grabCut(arr, mask, rect, bgd_model, fgd_model, 3, cv2.GC_INIT_WITH_RECT)
            fg = (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD)
            return fg.astype(np.float32)
        except Exception:
            return np.ones((h, w), dtype=np.float32) * 0.8


# ─────────────────────────────────────────────────────────────────────────────
# Convenience function
# ─────────────────────────────────────────────────────────────────────────────

_schp_parser: SCHPParser | None = None


def schp_parse(
    person_image: Image.Image,
    model_name: str = "pirocheto/schp-lip-20",
) -> SCHPResult:
    """
    Parse a person image using SCHP human parsing.

    This is the primary entry point for body-part segmentation.

    Args:
        person_image: PIL RGB image of a person.
        model_name: HuggingFace model name or local path. Defaults to
            "pirocheto/schp-lip-20" (20-class LIP dataset model).

    Returns:
        SCHPResult with masks for:
        - upper_clothes, left_arm, right_arm (for top try-on)
        - lower_garment, left_leg, right_leg (for bottom try-on)

    Example:
        result = schp_parse(person_image)
        upper_mask = result.upper_clothes       # HxW float 0-1
        arm_mask = result.left_arm + result.right_arm
        final_mask = upper_mask + arm_mask      # Combine for full upper-body mask
    """
    global _schp_parser
    if _schp_parser is None:
        _schp_parser = SCHPParser(model_name=model_name)
    return _schp_parser.parse_person(person_image)
