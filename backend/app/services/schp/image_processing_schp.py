from typing import Dict, List, Optional

import numpy as np
import torch
import torchvision.transforms.functional as TF
from PIL import Image
from transformers import BaseImageProcessor
from transformers.image_processing_utils import BatchFeature


class SCHPImageProcessor(BaseImageProcessor):
    model_input_names = ["pixel_values"]

    def __init__(
        self,
        size: Optional[Dict[str, int]] = None,
        image_mean: Optional[List[float]] = None,
        image_std: Optional[List[float]] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.size = size or {"height": 473, "width": 473}
        self.image_mean = image_mean or [0.406, 0.456, 0.485]
        self.image_std = image_std or [0.225, 0.224, 0.229]

    def preprocess(
        self,
        images,
        return_tensors: Optional[str] = "pt",
        **kwargs,
    ) -> BatchFeature:
        if not isinstance(images, (list, tuple)):
            images = [images]

        h = self.size["height"]
        w = self.size["width"]

        tensors = []
        for img in images:
            pil: Image.Image
            if isinstance(img, torch.Tensor):
                pil = TF.to_pil_image(img.cpu())
            elif isinstance(img, np.ndarray):
                pil = Image.fromarray(np.asarray(img, dtype=np.uint8))
            else:
                pil = img
            pil = pil.convert("RGB")

            pil = pil.resize((w, h), resample=Image.Resampling.BILINEAR)
            t = TF.to_tensor(pil)
            t = TF.normalize(t, mean=self.image_mean, std=self.image_std)
            tensors.append(t)

        pixel_values = torch.stack(tensors)
        return BatchFeature({"pixel_values": pixel_values}, tensor_type=return_tensors)
