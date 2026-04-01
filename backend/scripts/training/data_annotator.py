"""
图像标注工具

用于对衣物图片进行标注，生成训练数据。

使用方法:
    python scripts/training/data_annotator.py                    # 启动标注界面
    python scripts/training/data_annotator.py --review          # 审核已有数据
    python scripts/training/data_annotator.py --export          # 导出标注数据
    python scripts/training/data_annotator.py --import <folder>  # 导入图片文件夹
"""

import argparse
import base64
import json
import os
import sys
import webbrowser
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from PIL import Image

# 标注类别
CATEGORIES = [
    "上衣",
    "裤子",
    "裙子",
    "外套",
    "鞋",
    "包",
    "汉服",
    "国风",
    "马面裙",
    "上衣(汉)",
    "下装(汉)",
    "连衣裙",
]

STYLES = [
    "通勤",
    "休闲",
    "正式",
    "运动",
    "街头",
    "学院",
    "甜酷",
    "简约",
    "复古",
    "朋克",
    "民族",
    "优雅",
    "国风",
    "汉服",
    "新中式",
    "禅意",
    "古风",
]

GENDERS = ["男", "女", "中性"]


class AnnotationTool:
    """图像标注工具"""

    def __init__(self, output_dir: str = "./annotations"):
        """
        初始化标注工具

        Args:
            output_dir: 标注结果保存目录
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.annotations_file = self.output_dir / "annotations.json"
        self.annotations = self._load_annotations()

        self.pending_dir = self.output_dir / "pending"
        self.pending_dir.mkdir(parents=True, exist_ok=True)

        self.completed_dir = self.output_dir / "completed"
        self.completed_dir.mkdir(parents=True, exist_ok=True)

        print(f"[Init] Annotation tool initialized")
        print(f"  Output dir: {self.output_dir}")
        print(f"  Pending images: {len(self._get_pending_images())}")
        print(f"  Annotated: {len(self.annotations)}")

    def _load_annotations(self) -> Dict:
        """加载已有标注"""
        if self.annotations_file.exists():
            with open(self.annotations_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_annotations(self):
        """保存标注"""
        with open(self.annotations_file, "w", encoding="utf-8") as f:
            json.dump(self.annotations, f, ensure_ascii=False, indent=2)

    def _get_pending_images(self) -> List[Path]:
        """获取待标注图片"""
        images = []
        for ext in ["*.jpg", "*.jpeg", "*.png", "*.webp"]:
            images.extend(self.pending_dir.glob(ext))
        return sorted(images)

    def _image_to_base64(self, image_path: Path) -> str:
        """将图片转换为 base64"""
        with Image.open(image_path) as img:
            # 转换为 RGB
            if img.mode != "RGB":
                img = img.convert("RGB")
            # 缩放以减小大小
            img.thumbnail((800, 800), Image.Resampling.LANCZOS)
            # 转换为 base64
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            return base64.b64encode(buffer.getvalue()).decode()

    def _generate_html(self) -> str:
        """生成标注 HTML 页面"""
        pending_images = self._get_pending_images()

        if not pending_images:
            html = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>服装标注工具</title>
                <style>
                    body { font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }
                    h1 { color: #333; }
                    .completed { color: green; font-size: 1.2em; }
                    .info { background: #f0f0f0; padding: 15px; border-radius: 8px; margin: 20px 0; }
                    button { padding: 10px 20px; font-size: 16px; cursor: pointer; margin: 5px; }
                    .btn-primary { background: #007bff; color: white; border: none; border-radius: 4px; }
                    .btn-success { background: #28a745; color: white; border: none; border-radius: 4px; }
                    .btn-danger { background: #dc3545; color: white; border: none; border-radius: 4px; }
                </style>
            </head>
            <body>
                <h1>[OK] All images annotated!</h1>
                <div class="completed">
                    <p>Total annotated: <strong>{total}</strong></p>
                    <p>Pending: <strong>0</strong></p>
                </div>
                <div class="info">
                    <h3>Actions:</h3>
                    <button class="btn-primary" onclick="location.href='?action=review'">Review Annotations</button>
                    <button class="btn-success" onclick="location.href='?action=export'">Export Data</button>
                    <button class="btn-primary" onclick="location.href='?action=add'">Add More Images</button>
                </div>
            </body>
            </html>
            """.format(
                total=len(self.annotations)
            )
            return html

        current_image = pending_images[0]
        image_data = self._image_to_base64(current_image)
        remaining = len(pending_images)

        html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>服装标注工具</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { color: #333; text-align: center; }
        .progress { background: #e0e0e0; padding: 10px; border-radius: 4px; margin-bottom: 20px; }
        .progress-bar { background: #28a745; color: white; padding: 5px 10px; border-radius: 4px; display: inline-block; }
        .main-content { display: flex; gap: 20px; }
        .image-section { flex: 1; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .form-section { width: 350px; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); max-height: 80vh; overflow-y: auto; }
        .image-container { text-align: center; }
        .image-container img { max-width: 100%; max-height: 500px; border: 2px solid #ddd; border-radius: 4px; }
        .form-group { margin-bottom: 20px; }
        .form-group h3 { margin-top: 0; color: #555; border-bottom: 1px solid #eee; padding-bottom: 5px; }
        .checkbox-group { display: flex; flex-wrap: wrap; gap: 8px; }
        .checkbox-item { display: flex; align-items: center; }
        .checkbox-item input { margin-right: 5px; }
        .checkbox-item label { cursor: pointer; padding: 5px 10px; background: #f0f0f0; border-radius: 4px; }
        .checkbox-item input:checked + label { background: #007bff; color: white; }
        .radio-group { display: flex; gap: 15px; }
        .radio-item { display: flex; align-items: center; }
        .radio-item input { margin-right: 5px; }
        .buttons { display: flex; gap: 10px; margin-top: 20px; }
        button { padding: 12px 24px; font-size: 16px; cursor: pointer; border: none; border-radius: 4px; }
        .btn-skip { background: #6c757d; color: white; }
        .btn-save { background: #28a745; color: white; }
        .btn-delete { background: #dc3545; color: white; }
        .file-input { display: none; }
        .image-name { font-size: 14px; color: #666; margin-top: 10px; word-break: break-all; }
        .nav-buttons { display: flex; justify-content: space-between; margin-top: 20px; }
        .stats { background: #e7f3ff; padding: 15px; border-radius: 8px; margin-bottom: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>[Clothing] Annotation Tool</h1>

        <div class="progress">
            <span>Progress: <span class="progress-bar">{current}/{total}</span></span>
            <span style="float: right;">Remaining: {remaining}</span>
        </div>

        <div class="stats">
            <strong>Statistics:</strong> Total Annotated: {total_annotated} | Pending: {remaining} | Categories: {num_categories}
        </div>

        <div class="main-content">
            <div class="image-section">
                <div class="image-container">
                    <img src="data:image/jpeg;base64,{image_data}" alt="Annotation Image" id="mainImage">
                </div>
                <p class="image-name">{image_path}</p>
                <div class="nav-buttons">
                    <span style="color: #666;">
                        <a href="?action=prev">&laquo; Previous</a> |
                        <a href="?action=next">Next &raquo;</a>
                    </span>
                </div>
            </div>

            <div class="form-section">
                <form id="annotationForm" method="post">
                    <input type="hidden" name="action" value="save">
                    <input type="hidden" name="image_path" value="{image_path}">

                    <div class="form-group">
                        <h3>Category (Required)</h3>
                        <div class="radio-group">
                            {category_options}
                        </div>
                    </div>

                    <div class="form-group">
                        <h3>Style (Multi-select)</h3>
                        <div class="checkbox-group">
                            {style_options}
                        </div>
                    </div>

                    <div class="form-group">
                        <h3>Gender</h3>
                        <div class="radio-group">
                            {gender_options}
                        </div>
                    </div>

                    <div class="form-group">
                        <h3>Fit Type</h3>
                        <div class="radio-group">
                            <div class="radio-item">
                                <input type="radio" name="fit_type" id="fit_slim" value="slim">
                                <label for="fit_slim">Slim</label>
                            </div>
                            <div class="radio-item">
                                <input type="radio" name="fit_type" id="fit_normal" value="normal" checked>
                                <label for="fit_normal">Normal</label>
                            </div>
                            <div class="radio-item">
                                <input type="radio" name="fit_type" id="fit_loose" value="loose">
                                <label for="fit_loose">Loose</label>
                            </div>
                        </div>
                    </div>

                    <div class="buttons">
                        <button type="submit" class="btn-save">[Save & Next]</button>
                        <button type="button" class="btn-skip" onclick="skipImage()">Skip</button>
                        <button type="button" class="btn-delete" onclick="deleteImage()">Delete</button>
                    </div>
                </form>

                <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #eee;">
                    <h4>Quick Actions:</h4>
                    <button class="btn-skip" onclick="location.href='?action=export'">Export Data</button>
                    <button class="btn-skip" onclick="location.href='?action=review'">Review</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        function skipImage() {
            location.href = '?action=skip&path={image_path_escaped}';
        }

        function deleteImage() {
            if (confirm('Delete this image?')) {
                location.href = '?action=delete&path={image_path_escaped}';
            }
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', function(e) {
            if (e.key === 's' && !e.ctrlKey) {
                document.getElementById('annotationForm').submit();
            }
        });
    </script>
</body>
</html>
        """

        # 生成选项
        category_options = "\n".join(
            [
                f'<div class="radio-item"><input type="radio" name="category" id="cat_{i}" value="{cat}" required><label for="cat_{i}">{cat}</label></div>'
                for i, cat in enumerate(CATEGORIES)
            ]
        )

        style_options = "\n".join(
            [
                f'<div class="checkbox-item"><input type="checkbox" name="style" id="style_{i}" value="{style}"><label for="style_{i}">{style}</label></div>'
                for i, style in enumerate(STYLES)
            ]
        )

        gender_options = "\n".join(
            [
                f'<div class="radio-item"><input type="radio" name="gender" id="gender_{i}" value="{g}"><label for="gender_{i}">{g}</label></div>'
                for i, g in enumerate(GENDERS)
            ]
        )

        return html.format(
            image_data=image_data,
            image_path=str(current_image),
            image_path_escaped=str(current_image).replace("'", "\\'"),
            current=1,
            total=len(pending_images),
            remaining=remaining,
            total_annotated=len(self.annotations),
            num_categories=len(
                set(a.get("category") for a in self.annotations.values() if a.get("category"))
            ),
            category_options=category_options,
            style_options=style_options,
            gender_options=gender_options,
        )

    def run_server(self, host: str = "localhost", port: int = 5000):
        """启动标注服务"""
        try:
            import cv2
            from flask import Flask, Response, redirect, request, send_file
        except ImportError:
            print("[Error] Flask is required. Install: pip install flask")
            return

        app = Flask(__name__)

        @app.route("/")
        def index():
            action = request.args.get("action")
            if request.method == "POST" or action == "save":
                if request.method == "POST":
                    # 保存标注
                    image_path = request.form.get("image_path")
                    annotation = {
                        "category": request.form.get("category"),
                        "styles": request.form.getlist("style"),
                        "gender": request.form.get("gender"),
                        "fit_type": request.form.get("fit_type"),
                    }
                    if annotation["category"]:
                        self.annotations[image_path] = annotation
                        self._save_annotations()
                        # 移动到已完成
                        src = Path(image_path)
                        if src.exists():
                            dst = self.completed_dir / src.name
                            src.rename(dst)
                        print(f"[Saved] {image_path} -> {annotation}")

            # 显示标注界面
            return self._generate_html()

        @app.route("/")
        def handle_action():
            action = request.args.get("action", "")
            if action == "skip":
                return redirect("/")
            elif action == "delete":
                path = request.args.get("path")
                if path:
                    p = Path(path)
                    if p.exists():
                        p.unlink()
                    if path in self.annotations:
                        del self.annotations[path]
                        self._save_annotations()
                return redirect("/")
            elif action == "export":
                return redirect("/export")
            elif action == "review":
                return redirect("/review")
            return self._generate_html()

        @app.route("/export")
        def export():
            """导出标注数据"""
            data = []
            for path, ann in self.annotations.items():
                if Path(path).exists():
                    data.append(
                        {
                            "image_path": path,
                            "category": ann.get("category"),
                            "style_tags": ann.get("styles", []),
                            "gender": ann.get("gender"),
                            "fit_type": ann.get("fit_type"),
                        }
                    )

            export_file = self.output_dir / "exported_annotations.json"
            with open(export_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            return f"<h2>[OK] Exported {len(data)} annotations</h2><pre>{json.dumps(data[:3], ensure_ascii=False, indent=2)}...</pre><a href='/'>Back</a>"

        @app.route("/review")
        def review():
            """审核界面"""
            html = """
            <html><head><meta charset="UTF-8"><title>Review Annotations</title>
            <style>
                body { font-family: Arial; padding: 20px; }
                table { border-collapse: collapse; width: 100%; }
                th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                th { background: #f0f0f0; }
                img { max-width: 100px; max-height: 100px; }
                .delete { color: red; cursor: pointer; }
            </style></head>
            <body>
            <h1>Review Annotations ({count})</h1>
            <table>
                <tr><th>Image</th><th>Category</th><th>Styles</th><th>Gender</th><th>Action</th></tr>
                {rows}
            </table>
            <br><a href="/">Back to Annotation</a>
            </body></html>
            """
            rows = ""
            for path, ann in list(self.annotations.items())[:50]:
                if Path(path).exists():
                    rows += f"""<tr>
                        <td><img src="/thumb/{Path(path).name}"><br>{Path(path).name}</td>
                        <td>{ann.get('category', '')}</td>
                        <td>{', '.join(ann.get('styles', []))}</td>
                        <td>{ann.get('gender', '')}</td>
                        <td><a href="/?action=delete&path={path}" class="delete">Delete</a></td>
                    </tr>"""
            return html.format(count=len(self.annotations), rows=rows)

        @app.route("/thumb/<filename>")
        def thumbnail(filename):
            """生成缩略图"""
            for ext in ["jpg", "jpeg", "png"]:
                path = self.pending_dir / filename
                if not path.exists():
                    path = self.completed_dir / filename
                if path.exists():
                    img = Image.open(path)
                    img.thumbnail((100, 100))
                    buffer = BytesIO()
                    img.save(buffer, format="JPEG")
                    return Response(buffer.getvalue(), mimetype="image/jpeg")
            return "Not found", 404

        @app.route("/upload", methods=["POST"])
        def upload():
            """上传图片"""
            files = request.files.getlist("images")
            count = 0
            for f in files:
                if f.filename:
                    ext = Path(f.filename).suffix.lower()
                    if ext in [".jpg", ".jpeg", ".png", ".webp"]:
                        save_path = self.pending_dir / f.filename
                        f.save(save_path)
                        count += 1
            return f"<h2>Uploaded {count} images</h2><a href='/'>Start Annotating</a>"

        print(
            f"""
        =========================================
        [Annotation Tool] Starting Server
        =========================================
        URL: http://{host}:{port}

        Open this URL in your browser to start annotating!

        Keyboard shortcut: Press 's' to save
        =========================================
        """
        )

        webbrowser.open(f"http://{host}:{port}")
        app.run(host=host, port=port, debug=False)


def import_folder(folder_path: str, output_dir: str = "./annotations"):
    """导入文件夹中的图片"""
    folder = Path(folder_path)
    if not folder.exists():
        print(f"[Error] Folder not found: {folder_path}")
        return

    pending_dir = Path(output_dir) / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for ext in ["*.jpg", "*.jpeg", "*.png", "*.webp"]:
        for img_path in folder.glob(ext):
            dst = pending_dir / img_path.name
            if not dst.exists():
                img_path.rename(dst)  # 移动文件
                count += 1

    print(f"[OK] Imported {count} images to {pending_dir}")


def export_annotations(output_dir: str = "./annotations"):
    """导出标注数据"""
    annotations_file = Path(output_dir) / "annotations.json"
    export_file = Path(output_dir) / "exported_annotations.json"

    if not annotations_file.exists():
        print("[Error] No annotations found")
        return

    with open(annotations_file, "r", encoding="utf-8") as f:
        annotations = json.load(f)

    data = []
    for path, ann in annotations.items():
        if Path(path).exists():
            data.append(
                {
                    "image_path": path,
                    "category": ann.get("category"),
                    "style_tags": ann.get("styles", []),
                    "gender": ann.get("gender"),
                    "fit_type": ann.get("fit_type"),
                }
            )

    with open(export_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[OK] Exported {len(data)} annotations to {export_file}")


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description="Clothing Image Annotation Tool")
    parser.add_argument("--output", default="./annotations", help="Output directory")
    parser.add_argument("--host", default="localhost", help="Server host")
    parser.add_argument("--port", type=int, default=5000, help="Server port")
    parser.add_argument("--import", dest="import_folder", help="Import folder with images")
    parser.add_argument("--export", action="store_true", help="Export annotations to JSON")

    args = parser.parse_args()

    if args.import_folder:
        import_folder(args.import_folder, args.output)
    elif args.export:
        export_annotations(args.output)
    else:
        tool = AnnotationTool(args.output)
        tool.run_server(args.host, args.port)


if __name__ == "__main__":
    main()
