# 🔧 图像识别错误修复

## 问题描述

在测试 `POST /api/v1/recognition/analyze` 端点时，返回 400 错误：

```
"Invalid image data: Color extraction failed: 'bytes' object has no attribute 'resize'"
```

## 根本原因

`ColorExtractor.extract_colors()` 方法期望接收 PIL Image 对象，但实际接收到的是 bytes 对象。虽然其他模块（CategoryClassifier、StyleClassifier）通过 ImagePreprocessor 正确处理了 bytes 到 PIL Image 的转换，但 ColorExtractor 缺少这个转换步骤。

## 修复内容

已修改 `backend/app/ml/color_extractor.py`：

### 修改前
```python
def extract_colors(self, image: Union[Image.Image, np.ndarray]) -> List[ColorSchema]:
    try:
        # Convert to PIL Image if numpy array
        if isinstance(image, np.ndarray):
            image = Image.fromarray(image.astype("uint8"))
```

### 修改后
```python
def extract_colors(self, image: Union[Image.Image, np.ndarray, bytes]) -> List[ColorSchema]:
    try:
        # Convert to PIL Image if bytes
        if isinstance(image, bytes):
            from io import BytesIO
            image = Image.open(BytesIO(image))
        # Convert to PIL Image if numpy array
        elif isinstance(image, np.ndarray):
            image = Image.fromarray(image.astype("uint8"))
```

## 如何应用修复

### 方法 1: 重启后端服务（推荐）

1. **停止当前运行的后端服务**：
   - 在运行 `python run.py` 的终端中按 `Ctrl+C`

2. **重新启动后端服务**：
   ```bash
   cd backend
   python run.py
   ```

3. **验证服务已启动**：
   - 访问 http://localhost:8000/health
   - 应该返回 `{"status": "healthy"}`

### 方法 2: 使用 PowerShell 重启（如果终端不可用）

```powershell
# 停止所有相关的 Python 进程
Get-Process | Where-Object {$_.ProcessName -like "*python*" -and $_.Path -like "*clothing-assistant*"} | Stop-Process -Force

# 重新启动后端
cd backend
python run.py
```

## 测试修复

### 1. 准备测试图片

准备一张服饰图片（JPG、PNG 格式）

### 2. 在 Swagger UI 中测试

1. 访问 http://localhost:8000/docs
2. 展开 `POST /api/v1/recognition/analyze`
3. 点击 "Try it out"
4. 点击 "Choose File" 上传图片
5. 点击 "Execute"

### 3. 预期结果

应该返回 **200 OK** 状态码，包含：

```json
{
  "category": "上衣",
  "category_confidence": 0.85,
  "main_color": {
    "name": "蓝",
    "rgb": [52, 120, 180],
    "hsv": [210.0, 71.1, 70.6],
    "hex_code": "#3478b4"
  },
  "secondary_colors": [
    {
      "name": "白",
      "rgb": [240, 240, 240],
      "hsv": [0.0, 0.0, 94.1],
      "hex_code": "#f0f0f0"
    }
  ],
  "style_tags": ["通勤", "简约"],
  "feature_vector": [0.1, 0.2, ...]  // 1280 个值
}
```

## 如果仍然出错

### 检查日志

查看后端日志文件：

```bash
tail -f backend/logs/app.log
```

或在 Windows 中：

```powershell
Get-Content backend/logs/app.log -Tail 50
```

### 常见问题

1. **图片格式不支持**
   - 确保图片是 JPG、PNG 或 WebP 格式
   - 文件大小 < 10MB

2. **图片损坏**
   - 尝试使用不同的图片
   - 确保图片可以在图片查看器中正常打开

3. **服务未重启**
   - 确保已经重启后端服务
   - 检查是否有多个 Python 进程在运行

4. **依赖包问题**
   - 确保已安装所有依赖：
     ```bash
     pip install -r requirements.txt
     ```

## 验证修复成功

运行自动化测试脚本：

```bash
cd backend
python test_all_features.py
```

或使用 curl 命令测试：

```bash
curl -X POST http://localhost:8000/api/v1/recognition/analyze \
  -H "Content-Type: multipart/form-data" \
  -F "file=@/path/to/your/image.jpg"
```

## 相关文件

- `backend/app/ml/color_extractor.py` - 颜色提取器（已修复）
- `backend/app/ml/image_recognizer.py` - 图像识别器
- `backend/app/api/recognition.py` - 图像识别 API 端点

---

**修复日期**: 2026-03-22
**状态**: ✅ 已修复，需要重启服务
