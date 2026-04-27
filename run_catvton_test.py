"""Test realistic mode with debug_mode=preprocess_only and capture CatVTON logs."""
import io, time, requests, os, sys
from PIL import Image, ImageDraw
from datetime import datetime

BASE = "http://127.0.0.1:8010"


def make_test_img(w, h, base_color, label=""):
    """Create a textured test image with a label."""
    img = Image.new("RGB", (w, h), base_color)
    draw = ImageDraw.Draw(img)
    # Add some texture lines
    for i in range(0, w, 30):
        draw.line([(i, 0), (i + 20, h)],
                  fill=tuple(max(0, c - 40) for c in base_color), width=2)
    for i in range(0, h, 30):
        draw.line([(0, i), (w, i + 20)],
                  fill=tuple(min(255, c + 30) for c in base_color), width=2)
    # Add label text
    if label:
        try:
            draw.text((10, 10), label, fill=(255, 255, 255))
        except Exception:
            pass
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    buf.seek(0)
    return buf


def main():
    print("=" * 60)
    print("  CatVTON 完整功能测试")
    print("  mode=realistic + debug_mode=preprocess_only")
    print("=" * 60)

    # 1. Login
    print("\n[1/4] 登录...")
    r = requests.post(f"{BASE}/api/v1/auth/login", json={
        "username": "tryon_test_768156", "password": "TestPass123"
    }, timeout=10)
    if r.status_code != 200:
        print(f"  FAIL: {r.status_code} {r.text[:200]}")
        sys.exit(1)
    token = r.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"  OK: {token[:18]}...")

    # 2. Prepare test images
    print("\n[2/4] 准备测试图片...")
    person_buf = make_test_img(512, 768, (180, 160, 140), "PERSON_512x768")
    garment_buf = make_test_img(256, 384, (80, 100, 200), "GARMENT_256x384")
    print(f"  人物图: 512x768, 彩色纹理")
    print(f"  衣服图: 256x384, 彩色纹理")

    # 3. Make request with debug_mode=preprocess_only
    print("\n[3/4] 发起请求: realistic + preprocess_only...")
    print(f"  URL: POST {BASE}/api/v2/tryon/garment")
    print(f"  mode: realistic")
    print(f"  debug_mode: preprocess_only")
    print(f"  garment_category: top")
    print(f"  timeout: 120s")
    print(f"\n  -> 请观察终端窗口中的 CatVTON 日志！")
    print(f"  -> 测试图片已在准备中...")

    files = {
        "garment_file": ("garment.jpg", garment_buf, "image/jpeg"),
        "person_file": ("person.jpg", person_buf, "image/jpeg"),
    }
    data = {
        "mode": "realistic",
        "garment_category": "top",
        "model_gender": "neutral",
        "debug_mode": "preprocess_only",
    }

    t0 = time.time()
    try:
        r = requests.post(
            f"{BASE}/api/v2/tryon/garment",
            headers=headers,
            files=files,
            data=data,
            timeout=120,
        )
        elapsed = time.time() - t0

        print(f"\n[4/4] 响应收到！耗时 {elapsed:.1f}s")

        resp = r.json()
        data2 = resp.get("data") or {}

        print(f"  HTTP Status: {r.status_code}")
        print(f"  API Success: {resp.get('success')}")
        print(f"  TryOn Status: {data2.get('status')}")
        print(f"  Pipeline: {data2.get('pipeline')}")
        print(f"  Message: {data2.get('message', '')}")
        print(f"  Debug Dir: {data2.get('debug_session_dir', '')}")
        print(f"  QC Scores: {data2.get('qc_scores', {})}")

        if data2.get("result_image_url"):
            result_url = data2["result_image_url"]
            print(f"\n  结果图片: {BASE}{result_url}")
            # Verify image is accessible
            try:
                ir = requests.get(f"{BASE}{result_url}", timeout=5)
                print(f"  图片验证: HTTP {ir.status_code}, {len(ir.content):,} bytes")
            except Exception as e:
                print(f"  图片验证失败: {e}")

        # Check debug files
        debug_dir = data2.get("debug_session_dir")
        if debug_dir and os.path.exists(debug_dir):
            files_in_dir = sorted(os.listdir(debug_dir))
            print(f"\n  白盒调试文件 ({len(files_in_dir)} 个):")
            for f in files_in_dir:
                fp = os.path.join(debug_dir, f)
                size = os.path.getsize(fp)
                print(f"    {f} ({size:,} bytes)")
        elif debug_dir:
            print(f"\n  调试目录已创建但文件未找到: {debug_dir}")
        else:
            print(f"\n  CATVTON_DEBUG_DIR 未配置，不保存调试文件（这是正常的）")

        if not resp.get("success"):
            err = resp.get("error", {})
            print(f"\n  错误: {err.get('type')}: {err.get('message', '')}")

    except requests.exceptions.Timeout:
        print(f"\n  TIMEOUT after 120s - CatVTON 推理可能需要更长时间")
    except Exception as e:
        print(f"\n  异常: {type(e).__name__}: {e}")

    print("\n" + "=" * 60)
    print("  测试完成！")
    print("  如果看到 CatVTON 日志出现在终端窗口，说明子进程通信正常。")
    print("  如果响应成功，说明 preprocess_only 功能正常。")
    print("=" * 60)


if __name__ == "__main__":
    main()
