"""最终校验和整理脚本：验证所有图片与CSV一致、训练集去重、文件名检查"""

import csv
import hashlib
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from collections import Counter
from pathlib import Path

BASE_DIR = Path(r"d:/Users/omen/OneDrive/桌面/clothing-assistant")
IMAGE_DIR = BASE_DIR / "data/eval/recognition/images"
LABELS_CSV = BASE_DIR / "data/eval/recognition/labels.csv"
TRAINING_DATA = BASE_DIR / "backend/app/services/training_data.json"

# ── Step 1: 读取现有 CSV ──
records = []
with open(LABELS_CSV, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for row in reader:
        records.append(row)
print(f"CSV 记录: {len(records)} 条")

# ── Step 2: 检查每张图片是否有对应记录 ──
csv_files = {r["image_file"] for r in records}
disk_files = {f.name for f in IMAGE_DIR.glob("item_*.jpg")}

missing_in_csv = disk_files - csv_files
missing_on_disk = csv_files - disk_files

if missing_in_csv:
    print(f"\n[WARN] 以下图片在磁盘上存在但CSV中缺失:")
    for f in sorted(missing_in_csv):
        print(f"  {f}")
        # 为缺失的添加占位记录
        records.append(
            {
                "image_file": f,
                "true_category": "待确认",
                "true_color": "待确认",
                "notes": "需人工标注",
            }
        )

if missing_on_disk:
    print(f"\n[WARN] 以下图片在CSV中但磁盘缺失:")
    for f in sorted(missing_on_disk):
        print(f"  {f}")
    records = [r for r in records if r["image_file"] not in missing_on_disk]

if not missing_in_csv and not missing_on_disk:
    print("[OK] 图片和CSV完全一致")

# ── Step 3: 写回完整 CSV ──
records.sort(key=lambda r: r["image_file"])
with open(LABELS_CSV, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=["image_file", "true_category", "true_color", "notes"])
    writer.writeheader()
    for r in records:
        writer.writerow(r)
print(f"\n[OK] labels.csv 已整理 ({len(records)} 条)")

# ── Step 4: 文件名检查 ──
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
    "heel",
    "top",
    "tee",
]
leak = False
for f in IMAGE_DIR.glob("item_*.jpg"):
    for kw in cat_kws:
        if kw in f.stem.lower():
            print(f'[LEAK] {f.name} 含 "{kw}"')
            leak = True
if not leak:
    print("[OK] 文件名无类别泄露")

# ── Step 5: 训练集去重 ──
if TRAINING_DATA.exists():
    with open(TRAINING_DATA, "r", encoding="utf-8") as f:
        training = json.load(f)

    def sha1(path):
        h = hashlib.sha1()
        with open(path, "rb") as fp:
            while True:
                chunk = fp.read(8192)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    train_hashes = set()
    for item in training:
        p = item.get("image_path", "")
        if p and Path(p).exists():
            train_hashes.add(sha1(p))

    overlap = 0
    for r in records:
        img_path = IMAGE_DIR / r["image_file"]
        if img_path.exists() and sha1(str(img_path)) in train_hashes:
            print(f'[CONFLICT] {r["image_file"]} 和训练集重叠!')
            overlap += 1
    if overlap == 0:
        print(f"[OK] 无训练集重叠 (训练集 {len(train_hashes)} 张哈希已比对)")
    else:
        print(f"[WARN] {overlap} 张与训练集重叠!")
else:
    print("[WARN] training_data.json 不存在, 跳过")

# ── Step 6: 统计 ──
cat_count = Counter(r["true_category"] for r in records)
color_count = Counter(r["true_color"] for r in records)

print(f"\n===== 最终统计 =====")
print(f"总计: {len(records)} 张图片\n")

print("类别分布:")
for cat in ["上衣", "外套", "裤子", "裙子", "连衣裙", "鞋", "包"]:
    cnt = cat_count.get(cat, 0)
    target = {"上衣": 10, "外套": 8, "裤子": 10, "裙子": 5, "连衣裙": 5, "鞋": 8, "包": 4}
    status = "OK" if cnt >= target[cat] else f"缺{target[cat]-cnt}"
    print(f"  {cat}: {cnt} 张 (目标{target[cat]}) [{status}]")

print("\n颜色分布:")
for color, cnt in color_count.most_common():
    print(f"  {color}: {cnt}")

print(f"\n===== 重要提醒 =====")
print(f"1. labels.csv 中的 true_color 基于搜索关键词猜测, 必须逐张人工确认!")
print(f"2. Bing搜索可能下载到非服装图/不当内容, 请逐张检查图片质量")
print(f"3. 标注颜色枚举: 红/橙/黄/绿/蓝/紫/黑/白/灰/棕")
print(f"4. 标注类别枚举: 上衣/外套/裤子/裙子/连衣裙/鞋/包")
print(f"5. 确认后运行评测脚本: python backend/scripts/evaluate_recognition_accuracy.py")
