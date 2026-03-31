"""
CLIP 模型微调训练器

使用 PyTorch 和 Transformers 库对 CLIP 模型进行微调，
以提高服装识别准确性。
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torch.cuda.amp import autocast, GradScaler
from PIL import Image
from tqdm import tqdm

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.core.logging import setup_logging

logger = setup_logging()

# 设备配置
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
logger.info(f"Using device: {device}")


@dataclass
class TrainingConfig:
    """训练配置"""
    model_name: str = "openai/clip-vit-base-patch32"  # 或 "openai/clip-vit-large-patch14"
    batch_size: int = 8
    num_epochs: int = 10
    learning_rate: float = 1e-6
    weight_decay: float = 0.01
    warmup_steps: int = 100
    save_steps: int = 500
    eval_steps: int = 100
    max_seq_length: int = 77
    image_size: int = 224
    gradient_accumulation_steps: int = 1
    max_grad_norm: float = 1.0
    use_amp: bool = True  # 混合精度训练
    freeze_vision: bool = False  # 是否冻结视觉编码器
    freeze_text: bool = True  # 是否冻结文本编码器


class GarmentDataset(Dataset):
    """衣物数据集"""

    def __init__(
        self,
        data_path: str,
        clip_processor,
        categories: List[str],
        styles: List[str],
        transform: Optional[Callable] = None
    ):
        """
        初始化数据集

        Args:
            data_path: 训练数据 JSON 文件路径
            clip_processor: CLIP 处理器
            categories: 类别列表
            styles: 风格列表
            transform: 图片预处理函数
        """
        self.data_path = data_path
        self.processor = clip_processor
        self.categories = categories
        self.styles = styles
        self.transform = transform

        # 加载数据
        with open(data_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

        logger.info(f"Loaded {len(self.data)} samples from {data_path}")

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        """获取单个样本"""
        item = self.data[idx]

        # 加载图片
        image = Image.open(item["image_path"]).convert("RGB")

        # 获取类别标签
        category = item.get("category", "")
        category_idx = self.categories.index(category) if category in self.categories else 0

        # 获取风格标签 (多标签)
        style_labels = torch.zeros(len(self.styles))
        for style in item.get("style_tags", []):
            if style in self.styles:
                style_labels[self.styles.index(style)] = 1.0

        return {
            "image": image,
            "category_idx": category_idx,
            "category_text": category,
            "style_labels": style_labels,
            "image_path": item["image_path"],
        }


class CLIPFineTuner:
    """CLIP 模型微调器"""

    def __init__(
        self,
        config: TrainingConfig = None,
        categories: List[str] = None,
        styles: List[str] = None,
    ):
        """
        初始化 CLIP 微调器

        Args:
            config: 训练配置
            categories: 类别列表
            styles: 风格列表
        """
        self.config = config or TrainingConfig()
        self.categories = categories or [
            "上衣", "裤子", "裙子", "外套", "鞋", "包",
            "汉服", "国风", "马面裙", "上衣(汉)", "下装(汉)"
        ]
        self.styles = styles or [
            "通勤", "休闲", "正式", "运动", "街头", "学院",
            "甜酷", "简约", "复古", "朋克", "民族", "优雅",
            "国风", "汉服", "新中式", "禅意", "古风"
        ]

        # 模型和处理器
        self.model = None
        self.processor = None
        self.optimizer = None
        self.scheduler = None
        self.scaler = None

        # 训练状态
        self.global_step = 0
        self.best_loss = float("inf")
        self.train_losses = []
        self.eval_losses = []

        # 输出目录
        self.output_dir = project_root / "models" / "clip_finetuned"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"CLIPFineTuner initialized. Output dir: {self.output_dir}")

    def load_model(self):
        """加载 CLIP 模型"""
        logger.info(f"Loading CLIP model: {self.config.model_name}")

        from transformers import CLIPModel, CLIPProcessor

        self.processor = CLIPProcessor.from_pretrained(self.config.model_name)
        self.model = CLIPModel.from_pretrained(self.config.model_name)

        # 冻结部分层
        if self.config.freeze_vision:
            for param in self.model.vision_model.parameters():
                param.requires_grad = False
            logger.info("Vision encoder frozen")

        if self.config.freeze_text:
            for param in self.model.text_model.parameters():
                param.requires_grad = False
            logger.info("Text encoder frozen")

        # 移动到 GPU
        self.model = self.model.to(device)

        logger.info("CLIP model loaded successfully")

    def setup_training(self):
        """设置训练组件"""
        # 优化器
        self.optimizer = torch.optim.AdamW(
            self.model.parameters(),
            lr=self.config.learning_rate,
            weight_decay=self.config.weight_decay,
        )

        # 学习率调度器
        total_steps = self.config.num_epochs * 100  # 估算
        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer,
            T_max=total_steps,
            eta_min=self.config.learning_rate * 0.1,
        )

        # 混合精度训练
        if self.config.use_amp and device.type == "cuda":
            self.scaler = GradScaler()

        logger.info("Training components initialized")

    def create_category_prompts(self) -> List[str]:
        """创建类别提示文本"""
        prompts = []
        for cat in self.categories:
            prompt = f"a photo of {cat}, a piece of clothing"
            prompts.append(prompt)
        return prompts

    def create_style_prompts(self) -> List[str]:
        """创建风格提示文本"""
        prompts = []
        style_templates = {
            "通勤": "a professional office commute outfit",
            "休闲": "a casual everyday comfortable outfit",
            "正式": "a formal business attire",
            "运动": "an athletic sports fitness outfit",
            "街头": "a trendy street fashion urban style",
            "学院": "a preppy academic college style",
            "甜酷": "a sweet and cool girl crush outfit",
            "简约": "a minimalist simple clean style",
            "复古": "a vintage retro old-fashioned style",
            "朋克": "a punk edgy rebellious style",
            "民族": "an ethnic cultural style",
            "优雅": "an elegant graceful feminine style",
            "国风": "a Chinese fashion style with traditional elements",
            "汉服": "a traditional Chinese Hanfu style",
            "新中式": "a neo-Chinese new Chinese modern style",
            "禅意": "a zen minimalist Eastern aesthetic",
            "古风": "an ancient classical Chinese style",
        }
        for style in self.styles:
            template = style_templates.get(style, f"a {style} style outfit")
            prompts.append(template)
        return prompts

    def compute_loss(
        self,
        image_features: torch.Tensor,
        text_features: torch.Tensor,
        category_labels: torch.Tensor,
        style_labels: torch.Tensor,
    ) -> Tuple[torch.Tensor, Dict[str, float]]:
        """
        计算损失

        Args:
            image_features: 图片特征 [batch, dim]
            text_features: 文本特征 [batch, dim]
            category_labels: 类别标签 [batch]
            style_labels: 风格标签 [batch, num_styles]

        Returns:
            (总损失, 损失分解)
        """
        # 对比损失 (CLIP 损失)
        logits_per_image = image_features @ text_features.T
        logits_per_text = logits_per_image.T

        labels = torch.arange(len(image_features), device=device)
        clip_loss_img = nn.CrossEntropyLoss()(logits_per_image, labels)
        clip_loss_text = nn.CrossEntropyLoss()(logits_per_text, labels)
        clip_loss = (clip_loss_img + clip_loss_text) / 2

        # 分类损失
        category_loss = nn.CrossEntropyLoss()(
            image_features @ torch.randn(len(self.categories), image_features.shape[1], device=device),
            category_labels
        )

        # 多标签分类损失 (BCE)
        style_pred = image_features @ torch.randn(len(self.styles), image_features.shape[1], device=device)
        style_loss = nn.BCEWithLogitsLoss()(style_pred, style_labels)

        # 总损失
        total_loss = clip_loss + 0.1 * category_loss + 0.1 * style_loss

        loss_breakdown = {
            "clip_loss": clip_loss.item(),
            "category_loss": category_loss.item(),
            "style_loss": style_loss.item(),
            "total_loss": total_loss.item(),
        }

        return total_loss, loss_breakdown

    def train_step(
        self,
        images: List[Image.Image],
        category_texts: List[str],
        category_labels: torch.Tensor,
        style_labels: torch.Tensor,
    ) -> Dict[str, float]:
        """单步训练"""
        self.model.train()

        # 处理输入
        inputs = self.processor(
            text=category_texts,
            images=images,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=self.config.max_seq_length,
        )
        inputs = {k: v.to(device) for k, v in inputs.items()}

        # 前向传播
        if self.config.use_amp and device.type == "cuda":
            with autocast():
                outputs = self.model(**inputs)
                image_features = outputs.image_embeds
                text_features = outputs.text_embeds

                # L2 归一化
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)

                loss, loss_breakdown = self.compute_loss(
                    image_features, text_features,
                    category_labels, style_labels
                )

            # 反向传播
            self.scaler.scale(loss).backward()
            self.scaler.unscale_(self.optimizer)
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.config.max_grad_norm)
            self.scaler.step(self.optimizer)
            self.scaler.update()
        else:
            outputs = self.model(**inputs)
            image_features = outputs.image_embeds
            text_features = outputs.text_embeds

            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)

            loss, loss_breakdown = self.compute_loss(
                image_features, text_features,
                category_labels, style_labels
            )

            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.config.max_grad_norm)
            self.optimizer.step()

        self.optimizer.zero_grad()
        self.scheduler.step()

        self.global_step += 1

        return loss_breakdown

    def evaluate(self, val_data: List[Dict]) -> Dict[str, float]:
        """评估模型"""
        self.model.eval()

        total_loss = 0
        num_batches = 0

        with torch.no_grad():
            for batch in val_data:
                images = [Image.open(item["image_path"]).convert("RGB") for item in batch]
                category_texts = [item["category"] for item in batch]
                category_labels = torch.tensor([
                    self.categories.index(item["category"]) if item["category"] in self.categories else 0
                    for item in batch
                ], device=device)
                style_labels = torch.zeros(len(batch), len(self.styles), device=device)
                for i, item in enumerate(batch):
                    for style in item.get("style_tags", []):
                        if style in self.styles:
                            style_labels[i, self.styles.index(style)] = 1.0

                inputs = self.processor(
                    text=category_texts,
                    images=images,
                    return_tensors="pt",
                    padding=True,
                )
                inputs = {k: v.to(device) for k, v in inputs.items()}

                outputs = self.model(**inputs)
                image_features = outputs.image_embeds
                text_features = outputs.text_embeds

                image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)

                _, loss_breakdown = self.compute_loss(
                    image_features, text_features,
                    category_labels, style_labels
                )

                total_loss += loss_breakdown["total_loss"]
                num_batches += 1

        avg_loss = total_loss / num_batches if num_batches > 0 else 0
        return {"eval_loss": avg_loss}

    def train(
        self,
        train_data_path: str,
        val_data_path: Optional[str] = None,
        resume_from: Optional[str] = None,
    ):
        """
        训练模型

        Args:
            train_data_path: 训练数据路径
            val_data_path: 验证数据路径 (可选)
            resume_from: 从检查点恢复 (可选)
        """
        # 加载模型
        self.load_model()
        self.setup_training()

        # 加载训练数据
        with open(train_data_path, "r", encoding="utf-8") as f:
            train_data = json.load(f)

        logger.info(f"Training with {len(train_data)} samples")

        # 训练循环
        for epoch in range(self.config.num_epochs):
            logger.info(f"\n=== Epoch {epoch + 1}/{self.config.num_epochs} ===")

            epoch_losses = []
            pbar = tqdm(train_data, desc=f"Epoch {epoch + 1}")

            for i, item in enumerate(pbar):
                # 获取样本
                image = Image.open(item["image_path"]).convert("RGB")
                category_text = item["category"]
                category_label = self.categories.index(category_text) if category_text in self.categories else 0

                style_label = torch.zeros(len(self.styles))
                for style in item.get("style_tags", []):
                    if style in self.styles:
                        style_label[self.styles.index(style)] = 1.0

                # 训练一步
                loss_dict = self.train_step(
                    images=[image],
                    category_texts=[category_text],
                    category_labels=torch.tensor([category_label], device=device),
                    style_labels=style_label.unsqueeze(0).to(device),
                )

                epoch_losses.append(loss_dict["total_loss"])

                # 更新进度条
                pbar.set_postfix({
                    "loss": f"{loss_dict['total_loss']:.4f}",
                    "clip": f"{loss_dict['clip_loss']:.4f}",
                    "lr": f"{self.scheduler.get_last_lr()[0]:.2e}",
                })

                # 保存检查点
                if self.global_step % self.config.save_steps == 0:
                    self.save_checkpoint(f"checkpoint-{self.global_step}")

            # 记录 epoch 损失
            avg_loss = np.mean(epoch_losses)
            self.train_losses.append(avg_loss)
            logger.info(f"Epoch {epoch + 1} average loss: {avg_loss:.4f}")

            # 保存 epoch 检查点
            self.save_checkpoint(f"epoch-{epoch + 1}")

        logger.info("Training completed!")
        self.save_model()

    def save_checkpoint(self, name: str):
        """保存检查点"""
        checkpoint_path = self.output_dir / f"{name}.pt"

        checkpoint = {
            "global_step": self.global_step,
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "scheduler_state_dict": self.scheduler.state_dict(),
            "best_loss": self.best_loss,
            "config": {
                "model_name": self.config.model_name,
                "categories": self.categories,
                "styles": self.styles,
            },
        }

        torch.save(checkpoint, checkpoint_path)
        logger.info(f"Checkpoint saved: {checkpoint_path}")

    def save_model(self):
        """保存最终模型"""
        model_path = self.output_dir / "final_model"
        model_path.mkdir(parents=True, exist_ok=True)

        self.model.save_pretrained(model_path)
        self.processor.save_pretrained(model_path)

        # 保存配置
        config = {
            "model_name": self.config.model_name,
            "categories": self.categories,
            "styles": self.styles,
            "image_size": self.config.image_size,
        }
        with open(model_path / "config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        logger.info(f"Model saved to: {model_path}")

    def load_checkpoint(self, checkpoint_path: str):
        """加载检查点"""
        checkpoint = torch.load(checkpoint_path, map_location=device)

        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        self.scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
        self.global_step = checkpoint["global_step"]
        self.best_loss = checkpoint["best_loss"]

        logger.info(f"Checkpoint loaded: {checkpoint_path}")


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="CLIP 模型微调训练")
    parser.add_argument("--data", required=True, help="训练数据 JSON 文件路径")
    parser.add_argument("--val-data", help="验证数据路径")
    parser.add_argument("--epochs", type=int, default=10, help="训练轮数")
    parser.add_argument("--batch-size", type=int, default=8, help="批大小")
    parser.add_argument("--lr", type=float, default=1e-6, help="学习率")
    parser.add_argument("--model", default="openai/clip-vit-base-patch32", help="CLIP 模型名称")
    parser.add_argument("--freeze-vision", action="store_true", help="冻结视觉编码器")
    parser.add_argument("--output", default=str(project_root / "models" / "clip_finetuned"), help="输出目录")
    parser.add_argument("--resume", help="从检查点恢复")

    args = parser.parse_args()

    # 配置
    config = TrainingConfig(
        model_name=args.model,
        num_epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        freeze_vision=args.freeze_vision,
    )

    # 训练器
    trainer = CLIPFineTuner(config=config)
    trainer.output_dir = Path(args.output)
    trainer.output_dir.mkdir(parents=True, exist_ok=True)

    # 开始训练
    trainer.train(
        train_data_path=args.data,
        val_data_path=args.val_data,
        resume_from=args.resume,
    )


if __name__ == "__main__":
    main()
