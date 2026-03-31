"""
DeepFashion 数据集下载和转换工具

DeepFashion 包含以下子数据集：
1. Category and Attribute Prediction (推荐用于训练)
2. In-Shop Retrieval
3. Consumer-to-Shop Retrieval

使用方法:
    python scripts/training/deepfashion_downloader.py --download           # 下载数据集
    python scripts/training/deepfashion_downloader.py --prepare           # 准备数据
    python scripts/training/deepfashion_downloader.py --convert         # 转换为训练格式
    python scripts/training/deepfashion_downloader.py --all               # 执行全部步骤
"""

import argparse
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


# DeepFashion 数据集链接
DEEPFASHION_URLS = {
    "category_attribute": "https://drive.google.com/uc?id=0B7EVK8r0v71pWEZsVE9zaF9yTHc",
    "inshop": "https://drive.google.com/uc?id=0B7EVK8r0v71pY0RyRzlBYnA0LVE",
    "consumer2shop": "https://drive.google.com/uc?id=0B7EVK8r0v71pWnc5ek5MRnFxcEU",
}


class DeepFashionDownloader:
    """DeepFashion 数据集下载器"""

    def __init__(self, data_dir: str = "./data/deepfashion"):
        """
        初始化下载器

        Args:
            data_dir: 数据保存目录
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.raw_dir = self.data_dir / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)

        self.processed_dir = self.data_dir / "processed"
        self.processed_dir.mkdir(parents=True, exist_ok=True)

        print(f"[Init] DeepFashion Downloader initialized")
        print(f"  Data dir: {self.data_dir}")

    def download_with_gdown(self, url: str, output_path: Path) -> bool:
        """
        使用 gdown 下载 Google Drive 文件

        Args:
            url: Google Drive URL
            output_path: 输出路径

        Returns:
            bool: 是否成功
        """
        try:
            import gdown
            print(f"[Download] Downloading from {url}...")
            gdown.download(url, str(output_path), quiet=False)
            return True
        except ImportError:
            print("[Error] gdown not installed. Install: pip install gdown")
            return False
        except Exception as e:
            print(f"[Error] Download failed: {e}")
            return False

    def download_alternative(self, url: str, output_path: Path) -> bool:
        """
        使用 requests 下载（备选方案）

        Args:
            url: Google Drive URL
            output_path: 输出路径

        Returns:
            bool: 是否成功
        """
        try:
            import requests

            # 提取文件 ID
            file_id = url.split("id=")[-1] if "id=" in url else url.split("/")[-1]

            print(f"[Download] Downloading file ID: {file_id}...")

            # 访问确认页面
            session = requests.Session()
            res = session.get(url, stream=True)

            # 直接下载
            with open(output_path, "wb") as f:
                for chunk in res.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            return True
        except Exception as e:
            print(f"[Error] Download failed: {e}")
            return False

    def download(self, dataset: str = "category_attribute") -> bool:
        """
        下载指定数据集

        Args:
            dataset: 数据集名称

        Returns:
            bool: 是否成功
        """
        if dataset not in DEEPFASHION_URLS:
            print(f"[Error] Unknown dataset: {dataset}")
            print(f"Available: {list(DEEPFASHION_URLS.keys())}")
            return False

        url = DEEPFASHION_URLS[dataset]
        output_path = self.raw_dir / f"{dataset}.zip"

        if output_path.exists():
            print(f"[Info] Dataset already downloaded: {output_path}")
            return True

        # 尝试使用 gdown
        if not self.download_with_gdown(url, output_path):
            # 备选方案：手动下载
            print("\n[Info] Please download manually from:")
            print(f"  {url}")
            print(f"\nSave to: {output_path}")
            return False

        return True

    def extract(self, dataset: str = "category_attribute") -> Path:
        """
        解压数据集

        Args:
            dataset: 数据集名称

        Returns:
            Path: 解压目录
        """
        zip_path = self.raw_dir / f"{dataset}.zip"
        extract_dir = self.raw_dir / dataset

        if not zip_path.exists():
            print(f"[Error] Zip file not found: {zip_path}")
            return None

        if extract_dir.exists():
            print(f"[Info] Already extracted: {extract_dir}")
            return extract_dir

        print(f"[Extract] Extracting {zip_path}...")
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(self.raw_dir)

        return extract_dir

    def prepare_category_attribute(self) -> Dict:
        """
        准备 Category and Attribute Prediction 数据集

        Returns:
            Dict: 数据统计
        """
        extract_dir = self.extract("category_attribute")
        if not extract_dir:
            return {}

        # 查找图片目录
        img_dir = None
        for name in ["img", "images", "Img"]:
            potential = extract_dir / name
            if potential.exists():
                img_dir = potential
                break

        if not img_dir:
            print("[Error] Could not find images directory")
            return {}

        # 统计
        stats = {
            "total_images": 0,
            "categories": {},
            "attributes": {},
        }

        for cat_dir in img_dir.iterdir():
            if cat_dir.is_dir():
                cat_name = cat_dir.name
                count = len(list(cat_dir.glob("*")))
                stats["categories"][cat_name] = count
                stats["total_images"] += count

        print(f"[Stats] Total images: {stats['total_images']}")
        print(f"[Stats] Categories: {len(stats['categories'])}")

        return stats

    def convert_to_training_format(
        self,
        min_samples_per_category: int = 50,
        max_samples_per_category: int = 1000
    ) -> str:
        """
        转换为训练格式

        Args:
            min_samples_per_category: 每类最少样本数
            max_samples_per_category: 每类最多样本数

        Returns:
            str: 输出文件路径
        """
        print("[Convert] Converting to training format...")

        extract_dir = self.extract("category_attribute")
        if not extract_dir:
            return None

        # 查找图片目录
        img_dir = None
        for name in ["img", "images", "Img"]:
            potential = extract_dir / name
            if potential.exists():
                img_dir = potential
                break

        if not img_dir:
            print("[Error] Could not find images directory")
            return None

        # 收集数据
        training_data = []
        categories = []

        for cat_dir in img_dir.iterdir():
            if not cat_dir.is_dir():
                continue

            cat_name = cat_dir.name
            images = list(cat_dir.glob("*"))
            images = [img for img in images if img.suffix.lower() in [".jpg", ".jpeg", ".png"]]

            if len(images) < min_samples_per_category:
                continue

            # 限制样本数
            if len(images) > max_samples_per_category:
                import random
                images = random.sample(images, max_samples_per_category)

            categories.append(cat_name)

            for img_path in images:
                entry = {
                    "image_path": str(img_path),
                    "category": cat_name,
                    "style_tags": [],
                    "gender": "neutral",
                    "fit_type": "normal",
                }
                training_data.append(entry)

        # 保存
        output_path = self.processed_dir / "deepfashion_training.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(training_data, f, ensure_ascii=False, indent=2)

        # 保存类别映射
        categories_file = self.processed_dir / "categories.json"
        with open(categories_file, "w", encoding="utf-8") as f:
            json.dump({"categories": categories}, f, ensure_ascii=False, indent=2)

        print(f"[OK] Converted {len(training_data)} images from {len(categories)} categories")
        print(f"[OK] Saved to: {output_path}")

        return str(output_path)


class FashionNetDownloader:
    """备选：使用 Fashion-MNIST 或其他数据集"""

    DATASETS = {
        "fashion_mnist": {
            "url": "http://fashion-mnist.s3-website.eu-central-1.amazonaws.com/",
            "description": "Fashion-MNIST - 28x28 grayscale clothing images",
        },
        "zalando": {
            "url": "https://github.com/zalandoresearch/fashion-mnist",
            "description": "Same as Fashion-MNIST",
        },
    }

    def __init__(self, data_dir: str = "./data/fashion_mnist"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def download_fashion_mnist(self) -> str:
        """下载 Fashion-MNIST 数据集"""
        try:
            import torchvision.datasets as datasets
            import torchvision.transforms as transforms

            print("[Download] Downloading Fashion-MNIST...")

            transform = transforms.Compose([transforms.Resize((224, 224)), transforms.ToTensor()])

            train_dataset = datasets.FashionMNIST(
                root=str(self.data_dir),
                train=True,
                download=True,
                transform=transform
            )

            test_dataset = datasets.FashionMNIST(
                root=str(self.data_dir),
                train=False,
                download=True,
                transform=transform
            )

            print(f"[OK] Fashion-MNIST downloaded")
            print(f"  Train: {len(train_dataset)} images")
            print(f"  Test: {len(test_dataset)} images")

            return str(self.data_dir)

        except Exception as e:
            print(f"[Error] Failed to download Fashion-MNIST: {e}")
            return None

    def convert_fashion_mnist(self) -> str:
        """将 Fashion-MNIST 转换为训练格式"""
        try:
            import torchvision.datasets as datasets
            from PIL import Image

            print("[Convert] Converting Fashion-MNIST...")

            train_dataset = datasets.FashionMNIST(
                root=str(self.data_dir),
                train=True,
                download=False
            )

            # 类别映射
            class_names = [
                "T-shirt/top", "Trouser", "Pullover", "Dress", "Coat",
                "Sandal", "Shirt", "Sneaker", "Bag", "Ankle boot"
            ]

            # 映射到我们的类别
            category_map = {
                0: "上衣", 1: "裤子", 2: "上衣", 3: "裙子", 4: "外套",
                5: "鞋", 6: "上衣", 7: "鞋", 8: "包", 9: "鞋"
            }

            training_data = []

            for idx in range(len(train_dataset)):
                img, label = train_dataset[idx]

                # 转换为 PIL Image 并保存
                img_pil = Image.fromarray(img.numpy(), mode="L").convert("RGB")
                img_path = self.data_dir / "images" / f"fmnist_{idx}.jpg"
                img_path.parent.mkdir(parents=True, exist_ok=True)
                img_pil.save(img_path)

                entry = {
                    "image_path": str(img_path),
                    "category": category_map[label],
                    "style_tags": [],
                    "gender": "neutral",
                    "fit_type": "normal",
                    "subcategory": class_names[label],
                }
                training_data.append(entry)

                if idx % 5000 == 0:
                    print(f"  Processed {idx}/{len(train_dataset)}...")

            output_path = self.data_dir / "training_data.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(training_data, f, ensure_ascii=False, indent=2)

            print(f"[OK] Converted {len(training_data)} images")
            print(f"[OK] Saved to: {output_path}")

            return str(output_path)

        except Exception as e:
            print(f"[Error] Failed to convert: {e}")
            return None


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description="DeepFashion Dataset Downloader")
    parser.add_argument("--download", action="store_true", help="Download dataset")
    parser.add_argument("--prepare", action="store_true", help="Prepare downloaded data")
    parser.add_argument("--convert", action="store_true", help="Convert to training format")
    parser.add_argument("--all", action="store_true", help="Run all steps")
    parser.add_argument("--dataset", default="category_attribute",
                        choices=["category_attribute", "inshop", "consumer2shop"],
                        help="Dataset to download")
    parser.add_argument("--use-fashion-mnist", action="store_true",
                        help="Use Fashion-MNIST instead (faster)")
    parser.add_argument("--output", default="./training_data.json", help="Output file")

    args = parser.parse_args()

    if args.all or args.download:
        if args.use_fashion_mnist:
            downloader = FashionNetDownloader()
            data_dir = downloader.download_fashion_mnist()
            if data_dir and (args.all or args.convert):
                output = downloader.convert_fashion_mnist()
        else:
            downloader = DeepFashionDownloader()
            downloader.download(args.dataset)
            if args.all or args.prepare:
                downloader.prepare_category_attribute()
            if args.all or args.convert:
                output = downloader.convert_to_training_format()

    elif args.prepare:
        downloader = DeepFashionDownloader()
        downloader.prepare_category_attribute()

    elif args.convert:
        downloader = DeepFashionDownloader()
        output = downloader.convert_to_training_format()

    else:
        parser.print_help()
        print("\n=== Quick Start ===")
        print("1. Quick test (Fashion-MNIST):")
        print("   python scripts/training/deepfashion_downloader.py --all --use-fashion-mnist")
        print("\n2. Full DeepFashion (requires manual download):")
        print("   python scripts/training/deepfashion_downloader.py --download")
        print("   python scripts/training/deepfashion_downloader.py --convert")


if __name__ == "__main__":
    main()
