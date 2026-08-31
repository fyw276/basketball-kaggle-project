"""
下载评测用服装图片 v3 - 稳定版
策略：每个类别下载到独立子目录，最后统一复制+编号
"""

import csv
import hashlib
import json
import shutil
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from collections import Counter
from pathlib import Path

from icrawler.builtin import BingImageCrawler

BASE_DIR = Path(r"d:/Users/omen/OneDrive/桌面/clothing-assistant")
WORK_DIR = BASE_DIR / "data/eval/recognition"
IMAGE_DIR = WORK_DIR / "images"
LABELS_CSV = WORK_DIR / "labels.csv"
TRAINING_DATA = BASE_DIR / "backend/app/services/training_data.json"

# 每个类别独立下载
TASKS = [
    # (子目录名, 搜索关键词, 目标类别, 需要数量, 颜色预设, 备注)
    ("tops_white_tee", "white t-shirt product photo clothing", "上衣", 3, "白", "白色T恤"),
    ("tops_blue_shirt", "blue shirt men product photo", "上衣", 3, "蓝", "蓝色衬衫"),
    ("tops_black_hoodie", "black hoodie sweater product photo", "上衣", 2, "黑", "黑色卫衣"),
    ("tops_grey_sweater", "grey sweater knitwear product photo", "上衣", 2, "灰", "灰色毛衣"),
    ("outer_denim", "denim jacket product photo", "外套", 3, "蓝", "牛仔夹克"),
    ("outer_black_coat", "black winter coat product photo", "外套", 3, "黑", "黑色大衣"),
    ("outer_blazer", "blazer suit jacket product photo", "外套", 2, "黑", "西装外套"),
    ("pants_jeans", "blue jeans product photo clothing", "裤子", 4, "蓝", "蓝色牛仔裤"),
    ("pants_trousers", "black trousers pants product photo", "裤子", 3, "黑", "黑色西裤"),
    ("pants_shorts", "khaki cargo shorts product photo", "裤子", 3, "棕", "卡其短裤"),
    ("skirt_black", "black skirt women fashion product", "裙子", 3, "黑", "黑色半裙"),
    ("skirt_red", "red skirt women product photo", "裙子", 2, "红", "红色短裙"),
    ("dress_black", "black dress women product photo", "连衣裙", 3, "黑", "黑色连衣裙"),
    ("dress_red", "red dress women fashion product", "连衣裙", 2, "红", "红色连衣裙"),
    ("shoes_sneakers", "white sneakers shoes product photo", "鞋", 4, "白", "白色运动鞋"),
    ("shoes_boots", "brown leather boots product photo", "鞋", 2, "棕", "棕色靴子"),
    ("shoes_heels", "black high heels product photo", "鞋", 2, "黑", "黑色高跟鞋"),
    ("bag_handbag", "brown leather handbag product photo", "包", 2, "棕", "棕色手提包"),
    ("bag_backpack", "black backpack product photo", "包", 2, "黑", "黑色双肩包"),
]


def download_one(subdir, keyword, count):
    """下载一个搜索关键词的图片到子目录"""
    tmp_dir = IMAGE_DIR / subdir
    tmp_dir.mkdir(parents=True, exist_ok=True)
    print(f'  [{subdir}] "{keyword}" x{count}')

    try:
        crawler = BingImageCrawler(
            downloader_threads=2,
            storage={"root_dir": str(tmp_dir)},
        )
        crawler.crawl(keyword=keyword, max_num=count + 8)
    except Exception as e:
        print(f"    FAIL: {e}")
        return []

    # 过滤文件
    files = sorted(
        [
            f
            for f in tmp_dir.iterdir()
            if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
            and 5000 < f.stat().st_size < 10_000_000
        ]
    )
    return files[:count]


def convert_to_jpg(src_path, dst_path):
    """转换为JPEG格式"""
    if src_path.suffix.lower() in (".png", ".webp"):
        try:
            from PIL import Image

            img = Image.open(src_path).convert("RGB")
            img.save(dst_path, "JPEG", quality=90)
            return
        except Exception:
            pass
    shutil.copy2(src_path, dst_path)


def compute_sha1(filepath):
    h = hashlib.sha1()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def main():
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    # 清空已有 item_*.jpg
    for f in IMAGE_DIR.glob("item_*.jpg"):
        f.unlink()
    print("已清空旧 item_*.jpg\n")

    # ── Step 1: 分类别下载 ──
    print("=== Step 1: 分类别下载 ===")
    all_records = []

    for subdir, keyword, category, count, color, notes in TASKS:
        files = download_one(subdir, keyword, count)
        print(f"    -> 实际下载 {len(files)} 张")
        for f in files:
            all_records.append(
                {
                    "src": f,
                    "category": category,
                    "color": color,
                    "notes": notes,
                }
            )
        time.sleep(1)

    print(f"\n总下载: {len(all_records)} 张\n")

    # ── Step 2: 统一编号 ──
    print("=== Step 2: 统一编号 ===")
    idx = 1
    final_records = []
    for rec in all_records:
        dst_name = f"item_{idx:03d}.jpg"
        dst_path = IMAGE_DIR / dst_name
        convert_to_jpg(rec["src"], dst_path)

        # 验证文件
        if dst_path.exists() and dst_path.stat().st_size > 5000:
            final_records.append(
                {
                    "image_file": dst_name,
                    "true_category": rec["category"],
                    "true_color": rec["color"],
                    "notes": rec["notes"],
                }
            )
            idx += 1
        else:
            print(f"  [SKIP] {dst_name} 无效")
            dst_path.unlink(missing_ok=True)

    # ── Step 3: 清理子目录 ──
    print("\n=== Step 3: 清理子目录 ===")
    for d in IMAGE_DIR.iterdir():
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
            print(f"  已删除 {d.name}")

    # ── Step 4: 写 labels.csv ──
    print("\n=== Step 4: 写 labels.csv ===")
    with open(LABELS_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f, fieldnames=["image_file", "true_category", "true_color", "notes"]
        )
        writer.writeheader()
        for r in final_records:
            writer.writerow(r)
    print(f"  写入 {len(final_records)} 条记录")

    # ── Step 5: 校验 ──
    print("\n=== Step 5: 校验 ===")

    # 5a. 文件名无类别泄露
    cat_kws = [
        "shirt",
        "tshirt",
        "jacket",
        "coat",
        "pants",
        "jeans",
        "skirt",
        "dress",
        "shoes",
        "sneakers",
        "bag",
        "boot",
        "hoodie",
        "blazer",
        "sweater",
    ]
    leak = False
    for f in IMAGE_DIR.glob("item_*.jpg"):
        for kw in cat_kws:
            if kw in f.stem.lower():
                print(f'  [LEAK] {f.name} 含 "{kw}"')
                leak = True
    if not leak:
        print("  [OK] 文件名无类别泄露")

    # 5b. 训练集去重
    if TRAINING_DATA.exists():
        with open(TRAINING_DATA, "r", encoding="utf-8") as f:
            training = json.load(f)
        train_hashes = set()
        for item in training:
            p = item.get("image_path", "")
            if p and Path(p).exists():
                train_hashes.add(compute_sha1(p))

        overlap = 0
        for r in final_records:
            img_path = IMAGE_DIR / r["image_file"]
            if compute_sha1(str(img_path)) in train_hashes:
                print(f'  [CONFLICT] {r["image_file"]} 和训练集重叠!')
                overlap += 1
        if overlap == 0:
            print("  [OK] 无训练集重叠")
        else:
            print(f"  [WARN] {overlap} 张重叠!")
    else:
        print("  [WARN] training_data.json 不存在, 跳过")

    # ── 统计 ──
    cat_count = Counter(r["true_category"] for r in final_records)
    color_count = Counter(r["true_color"] for r in final_records)

    print(f"\n=== 最终统计 ===")
    print(f"总计: {len(final_records)} 张图片\n")
    print("类别分布:")
    for cat, cnt in cat_count.most_common():
        print(f"  {cat}: {cnt}")
    print("\n颜色分布:")
    for color, cnt in color_count.most_common():
        print(f"  {color}: {cnt}")

    print(f"\n[IMPORTANT]")
    print(f"  1. labels.csv 中的 true_color 基于搜索关键词猜测, 必须逐张人工确认!")
    print(f"  2. 请检查每张图片质量, 删除不合格的(动漫/非服装/模糊/不当内容)")
    print(f"  3. 检查后运行: python backend/scripts/evaluate_recognition_accuracy.py")


if __name__ == "__main__":
    main()
