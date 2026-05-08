"""
SCHP (Self-Correction Human Parsing) — native PyTorch implementation.

Architecture from: https://github.com/PeikeLi/Self-Correction-Human-Parsing
(networks/AugmentCE2P.py) with the CUDA-only InPlaceABNSync replaced by a
pure-PyTorch BatchNorm2d drop-in, making the model fully runnable on CPU.

Labels (20 classes, LIP dataset):
    0  Background   5  Upper-clothes  10 Jumpsuits    15 Right-arm
    1  Hat          6  Dress          11 Scarf        16 Left-leg
    2  Hair         7  Coat           12 Skirt        17 Right-leg
    3  Glove        8  Socks          13 Face         18 Left-shoe
    4  Sunglasses   9  Pants          14 Left-arm     19 Right-shoe
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

from .configuration_schp import SCHPConfig


# ── CPU-compatible InPlaceABNSync replacement ──────────────────────────────
class InPlaceABNSync(nn.BatchNorm2d):
    """CPU drop-in for InPlaceABNSync — subclassed from BatchNorm2d so
    state-dict keys (weight, bias, running_mean, running_var) match the
    original SCHP checkpoints exactly.
    """

    def __init__(self, num_features, activation="leaky_relu", slope=0.01, **kwargs):
        bn_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k in ("eps", "momentum", "affine", "track_running_stats")
        }
        super().__init__(num_features, **bn_kwargs)
        self.activation = activation
        self.slope = slope

    def forward(self, input: torch.Tensor) -> torch.Tensor:
        input = super().forward(input)
        if self.activation == "leaky_relu":
            return F.leaky_relu(input, negative_slope=self.slope, inplace=True)
        elif self.activation == "elu":
            return F.elu(input, inplace=True)
        return input


BatchNorm2d = functools.partial(InPlaceABNSync, activation="none")
affine_par = True


# ── ResNet-101 building blocks ───────────────────────────────────────────────
def _conv3x3(in_planes, out_planes, stride=1):
    return nn.Conv2d(in_planes, out_planes, kernel_size=3, stride=stride, padding=1, bias=False)


class _Bottleneck(nn.Module):
    expansion = 4

    def __init__(self, inplanes, planes, stride=1, dilation=1, downsample=None, multi_grid=1):
        super().__init__()
        self.conv1 = nn.Conv2d(inplanes, planes, kernel_size=1, bias=False)
        self.bn1 = BatchNorm2d(planes)
        self.conv2 = nn.Conv2d(
            planes,
            planes,
            kernel_size=3,
            stride=stride,
            padding=dilation * multi_grid,
            dilation=dilation * multi_grid,
            bias=False,
        )
        self.bn2 = BatchNorm2d(planes)
        self.conv3 = nn.Conv2d(planes, planes * 4, kernel_size=1, bias=False)
        self.bn3 = BatchNorm2d(planes * 4)
        self.relu = nn.ReLU(inplace=False)
        self.relu_inplace = nn.ReLU(inplace=True)
        self.downsample = downsample
        self.dilation = dilation
        self.stride = stride

    def forward(self, x):
        residual = x
        out = self.relu(self.bn1(self.conv1(x)))
        out = self.relu(self.bn2(self.conv2(out)))
        out = self.bn3(self.conv3(out))
        if self.downsample is not None:
            residual = self.downsample(x)
        return self.relu_inplace(out + residual)


# ── PSP context encoding ─────────────────────────────────────────────────────
class _PSPModule(nn.Module):
    def __init__(self, features, out_features=512, sizes=(1, 2, 3, 6)):
        super().__init__()
        self.stages = nn.ModuleList(
            [
                nn.Sequential(
                    nn.AdaptiveAvgPool2d(size),
                    nn.Conv2d(features, out_features, kernel_size=1, bias=False),
                    InPlaceABNSync(out_features),
                )
                for size in sizes
            ]
        )
        self.bottleneck = nn.Sequential(
            nn.Conv2d(
                features + len(sizes) * out_features,
                out_features,
                kernel_size=3,
                padding=1,
                dilation=1,
                bias=False,
            ),
            InPlaceABNSync(out_features),
        )

    def forward(self, feats):
        h, w = feats.size(2), feats.size(3)
        priors = [
            F.interpolate(stage(feats), size=(h, w), mode="bilinear", align_corners=True)
            for stage in self.stages
        ] + [feats]
        return self.bottleneck(torch.cat(priors, dim=1))


# ── Edge branch ──────────────────────────────────────────────────────────────
class _Edge_Module(nn.Module):
    def __init__(self, in_fea=(256, 512, 1024), mid_fea=256, out_fea=2):
        super().__init__()
        self.conv1 = nn.Sequential(
            nn.Conv2d(in_fea[0], mid_fea, kernel_size=1, bias=False),
            InPlaceABNSync(mid_fea),
        )
        self.conv2 = nn.Sequential(
            nn.Conv2d(in_fea[1], mid_fea, kernel_size=1, bias=False),
            InPlaceABNSync(mid_fea),
        )
        self.conv3 = nn.Sequential(
            nn.Conv2d(in_fea[2], mid_fea, kernel_size=1, bias=False),
            InPlaceABNSync(mid_fea),
        )
        self.conv4 = nn.Conv2d(mid_fea, out_fea, kernel_size=3, padding=1, bias=True)
        self.conv5 = nn.Conv2d(out_fea * 3, out_fea, kernel_size=1, bias=True)

    def forward(self, x1, x2, x3):
        _, _, h, w = x1.size()
        ef1 = self.conv1(x1)
        ef2 = self.conv2(x2)
        ef3 = self.conv3(x3)
        e1 = self.conv4(ef1)
        e2 = F.interpolate(self.conv4(ef2), size=(h, w), mode="bilinear", align_corners=True)
        e3 = F.interpolate(self.conv4(ef3), size=(h, w), mode="bilinear", align_corners=True)
        ef2 = F.interpolate(ef2, size=(h, w), mode="bilinear", align_corners=True)
        ef3 = F.interpolate(ef3, size=(h, w), mode="bilinear", align_corners=True)
        edge = self.conv5(torch.cat([e1, e2, e3], dim=1))
        edge_fea = torch.cat([ef1, ef2, ef3], dim=1)
        return edge, edge_fea


# ── Decoder ──────────────────────────────────────────────────────────────────
class _Decoder_Module(nn.Module):
    def __init__(self, num_classes):
        super().__init__()
        self.conv1 = nn.Sequential(
            nn.Conv2d(512, 256, kernel_size=1, bias=False),
            InPlaceABNSync(256),
        )
        self.conv2 = nn.Sequential(
            nn.Conv2d(256, 48, kernel_size=1, bias=False),
            InPlaceABNSync(48),
        )
        self.conv3 = nn.Sequential(
            nn.Conv2d(304, 256, kernel_size=1, bias=False),
            InPlaceABNSync(256),
            nn.Conv2d(256, 256, kernel_size=1, bias=False),
            InPlaceABNSync(256),
        )
        self.conv4 = nn.Conv2d(256, num_classes, kernel_size=1, bias=True)

    def forward(self, xt, xl):
        _, _, h, w = xl.size()
        xt = F.interpolate(self.conv1(xt), size=(h, w), mode="bilinear", align_corners=True)
        xl = self.conv2(xl)
        x = self.conv3(torch.cat([xt, xl], dim=1))
        return self.conv4(x), x


# ── Full SCHP ResNet-101 ─────────────────────────────────────────────────────
class _SCHPResNet(nn.Module):
    def __init__(self, num_classes: int):
        self.inplanes = 128
        super().__init__()
        self.conv1 = _conv3x3(3, 64, stride=2)
        self.bn1 = BatchNorm2d(64)
        self.relu1 = nn.ReLU(inplace=False)
        self.conv2 = _conv3x3(64, 64)
        self.bn2 = BatchNorm2d(64)
        self.relu2 = nn.ReLU(inplace=False)
        self.conv3 = _conv3x3(64, 128)
        self.bn3 = BatchNorm2d(128)
        self.relu3 = nn.ReLU(inplace=False)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)

        self.layer1 = self._make_layer(_Bottleneck, 64, 3)
        self.layer2 = self._make_layer(_Bottleneck, 128, 4, stride=2)
        self.layer3 = self._make_layer(_Bottleneck, 256, 23, stride=2)
        self.layer4 = self._make_layer(
            _Bottleneck, 512, 3, stride=1, dilation=2, multi_grid=(1, 1, 1)
        )

        self.context_encoding = _PSPModule(2048, 512)
        self.edge = _Edge_Module()
        self.decoder = _Decoder_Module(num_classes)
        self.fushion = nn.Sequential(
            nn.Conv2d(1024, 256, kernel_size=1, bias=False),
            InPlaceABNSync(256),
            nn.Dropout2d(0.1),
            nn.Conv2d(256, num_classes, kernel_size=1, bias=True),
        )

    def _make_layer(self, block, planes, blocks, stride=1, dilation=1, multi_grid=1):
        downsample = None
        if stride != 1 or self.inplanes != planes * block.expansion:
            downsample = nn.Sequential(
                nn.Conv2d(
                    self.inplanes,
                    planes * block.expansion,
                    kernel_size=1,
                    stride=stride,
                    bias=False,
                ),
                BatchNorm2d(planes * block.expansion, affine=affine_par),
            )

        def _grid(i, g):
            return g[i % len(g)] if isinstance(g, tuple) else 1

        layers = [
            block(
                self.inplanes,
                planes,
                stride,
                dilation=dilation,
                downsample=downsample,
                multi_grid=_grid(0, multi_grid),
            )
        ]
        self.inplanes = planes * block.expansion
        for i in range(1, blocks):
            layers.append(
                block(
                    self.inplanes,
                    planes,
                    dilation=dilation,
                    multi_grid=_grid(i, multi_grid),
                )
            )
        return nn.Sequential(*layers)

    def forward(self, x):
        x = self.relu1(self.bn1(self.conv1(x)))
        x = self.relu2(self.bn2(self.conv2(x)))
        x = self.relu3(self.bn3(self.conv3(x)))
        x = self.maxpool(x)
        x2 = self.layer1(x)
        x3 = self.layer2(x2)
        x4 = self.layer3(x3)
        x5 = self.layer4(x4)
        context = self.context_encoding(x5)
        parsing_result, parsing_fea = self.decoder(context, x2)
        edge_result, edge_fea = self.edge(x2, x3, x4)
        fusion_result = self.fushion(torch.cat([parsing_fea, edge_fea], dim=1))
        return [[parsing_result, fusion_result], [edge_result]]


# ── Output dataclass ─────────────────────────────────────────────────────────
@dataclass
class SCHPSemanticSegmenterOutput:
    loss: Optional[torch.Tensor] = None
    logits: Optional[torch.Tensor] = None
    parsing_logits: Optional[torch.Tensor] = None
    edge_logits: Optional[torch.Tensor] = None


# ── Main model class ─────────────────────────────────────────────────────────
class SCHPForSemanticSegmentation(nn.Module):
    """
    SCHP ResNet-101 for human parsing / semantic segmentation.

    Usage::

        # Load from HuggingFace (pirocheto/schp-lip-20)
        model = SCHPForSemanticSegmentation.from_pretrained("pirocheto/schp-lip-20")

        # Load from an original SCHP .pth checkpoint
        model = SCHPForSemanticSegmentation.from_schp_checkpoint(
            "checkpoints/exp-schp-201908261155-lip.pth"
        )
    """

    def __init__(self, config: SCHPConfig):
        super().__init__()
        self.config = config
        self.model = _SCHPResNet(num_classes=config.num_labels)

    def forward(
        self,
        pixel_values: torch.Tensor,
        labels: Optional[torch.LongTensor] = None,
    ) -> SCHPSemanticSegmenterOutput:
        h, w = pixel_values.shape[-2:]
        raw = self.model(pixel_values)

        logits = F.interpolate(raw[0][1], size=(h, w), mode="bilinear", align_corners=True)
        parsing_logits = F.interpolate(raw[0][0], size=(h, w), mode="bilinear", align_corners=True)
        edge_logits = F.interpolate(raw[1][0], size=(h, w), mode="bilinear", align_corners=True)

        loss = None
        if labels is not None:
            loss = F.cross_entropy(logits, labels.long())

        return SCHPSemanticSegmenterOutput(
            loss=loss,
            logits=logits,
            parsing_logits=parsing_logits,
            edge_logits=edge_logits,
        )

    @classmethod
    def from_schp_checkpoint(
        cls,
        checkpoint_path: str,
        config: Optional[SCHPConfig] = None,
        map_location: str = "cpu",
    ) -> "SCHPForSemanticSegmentation":
        """Load from an original SCHP ``.pth`` checkpoint."""
        if config is None:
            config = SCHPConfig()

        model = cls(config)
        raw = torch.load(checkpoint_path, map_location=map_location, weights_only=False)
        state_dict = raw.get("state_dict", raw)

        if all(k.startswith("module.") for k in state_dict):
            state_dict = {k[len("module.") :]: v for k, v in state_dict.items()}

        state_dict = {"model." + k: v for k, v in state_dict.items()}

        missing, unexpected = model.load_state_dict(state_dict, strict=False)
        real_missing = [k for k in missing if "num_batches_tracked" not in k]
        if real_missing:
            raise RuntimeError(
                f"Missing keys when loading SCHP checkpoint ({len(real_missing)}): "
                f"{real_missing[:5]}"
            )
        if unexpected:
            raise RuntimeError(
                f"Unexpected keys when loading SCHP checkpoint ({len(unexpected)}): "
                f"{unexpected[:5]}"
            )
        return model

    @classmethod
    def from_pretrained(cls, model_name: str, **kwargs) -> "SCHPForSemanticSegmentation":
        """Load model and weights from a HuggingFace model ID or local path."""
        from transformers import AutoConfig, AutoModel

        from .configuration_schp import SCHPConfig
        from .image_processing_schp import SCHPImageProcessor

        config = AutoConfig.from_pretrained(model_name, trust_remote_code=True, **kwargs)
        model = cls(config)
        state_dict = cls._download_safetensors(model_name)
        model.load_state_dict(state_dict, strict=False)
        return model

    @staticmethod
    def _download_safetensors(model_name: str) -> dict:
        """Download safetensors files from HuggingFace and return state dict."""
        from pathlib import Path

        from safetensors.torch import load_file

        cache_base = Path.home() / ".cache" / "huggingface" / "hub"
        snapshot_base = None

        for entry in cache_base.iterdir():
            if entry.is_dir() and model_name.replace("/", "--") in entry.name:
                snap = entry / "snapshots"
                if snap.exists():
                    for snap_entry in snap.iterdir():
                        blobs = snap_entry / "blobs"
                        if blobs.exists():
                            snapshot_base = snap_entry
                            break
                if snapshot_base:
                    break

        if snapshot_base is None:
            snapshot_base = cache_base / (model_name.replace("/", "--") + ".lock")

        blobs_dir = snapshot_base / "blobs"

        state_dict = {}
        for blob in sorted(blobs_dir.iterdir()):
            if blob.suffix in (".safetensors", ".bin"):
                state_dict.update(load_file(str(blob)))
                break

        return state_dict
