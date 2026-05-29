# API 使用示例

本文档提供智能穿搭助手 API 的实际使用示例，包括 curl 命令、Python 代码和 JavaScript 代码。

> **基址与端口**：开发环境默认后端为 **`http://127.0.0.1:8010`**（见 `backend/.env` 的 `PORT` 与 `mobile` 的 `kApiPort`）。如你的环境不同，请将示例里的主机与端口替换为实际值，或设 `BASE_URL=http://127.0.0.1:8010` 后自行拼接路径。

## 目录

1. [AI 穿搭风格分（/predict）](#ai-穿搭风格分predict)
2. [认证流程](#认证流程)
3. [用户画像管理](#用户画像管理)
4. [图像识别](#图像识别)
5. [衣橱管理](#衣橱管理)
6. [智能穿搭（天气与情绪）](#智能穿搭天气与情绪)
7. [智能分析](#智能分析)

---

## AI 穿搭风格分（/predict）

### 1. 获取风格分与推荐

**curl**:
```bash
curl -X POST "http://127.0.0.1:8010/predict" \
  -H "Content-Type: application/json" \
  -d '{
    "top": "衬衫",
    "bottom": "牛仔裤",
    "color_top": "白色",
    "color_bottom": "蓝色",
    "season": "春季",
    "occasion": "通勤"
  }'
```

**Python**:
```python
import requests

url = "http://127.0.0.1:8010/predict"
data = {
    "top": "衬衫",
    "bottom": "牛仔裤",
    "color_top": "白色",
    "color_bottom": "蓝色",
    "season": "春季",
    "occasion": "通勤",
}

response = requests.post(url, json=data)
print(response.json())
```

**响应示例**:
```json
{
  "score": 8.4,
  "recommendations": [
    { "outfit": "衬衫 + 牛仔裤", "score": 8.4 },
    { "outfit": "Shirt + Chinos", "score": 8.1 },
    { "outfit": "Hoodie + Joggers", "score": 7.8 }
  ],
  "explanation": "颜色搭配协调，适合当前季节和场景",
  "source": "local",
  "fallback_reason": null,
  "model_version_local": "local-sklearn-pipeline",
  "model_version_external": null,
  "latency_ms": 42
}
```

---

## 认证流程

### 1. 注册新用户

**curl**:
```bash
curl -X POST "http://127.0.0.1:8010/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "fashionista",
    "email": "fashionista@example.com",
    "password": "SecurePass123"
  }'
```

**Python**:
```python
import requests

url = "http://127.0.0.1:8010/api/v1/auth/register"
data = {
    "username": "fashionista",
    "email": "fashionista@example.com",
    "password": "SecurePass123"
}

response = requests.post(url, json=data)
print(response.json())
```

**JavaScript (fetch)**:
```javascript
const url = 'http://127.0.0.1:8010/api/v1/auth/register';
const data = {
  username: 'fashionista',
  email: 'fashionista@example.com',
  password: 'SecurePass123'
};

fetch(url, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify(data)
})
  .then(response => response.json())
  .then(data => console.log(data));
```

**响应示例**:
```json
{
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "username": "fashionista",
  "email": "fashionista@example.com",
  "is_active": true,
  "created_at": "2024-01-01T10:00:00Z"
}
```

---

### 2. 用户登录

**curl**:
```bash
curl -X POST "http://127.0.0.1:8010/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "fashionista",
    "password": "SecurePass123"
  }'
```

**Python**:
```python
import requests

url = "http://127.0.0.1:8010/api/v1/auth/login"
data = {
    "username": "fashionista",
    "password": "SecurePass123"
}

response = requests.post(url, json=data)
token_data = response.json()
access_token = token_data["access_token"]

print(f"Access Token: {access_token}")
```

**响应示例**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjNlNDU2Ny1lODliLTEyZDMtYTQ1Ni00MjY2MTQxNzQwMDAiLCJ1c2VybmFtZSI6ImZhc2hpb25pc3RhIiwiZXhwIjoxNzA0MTg3MjAwfQ.abc123...",
  "token_type": "bearer"
}
```

---

## 用户画像管理

### 3. 创建用户画像

**curl**:
```bash
curl -X POST "http://127.0.0.1:8010/api/v1/profile" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "height": 168,
    "body_type": "沙漏型",
    "skin_tone": "冷白",
    "style_preference": ["通勤", "简约", "优雅"],
    "budget_range": "中档",
    "avoid_body_parts": ["肩部"]
  }'
```

**Python**:
```python
import requests

url = "http://127.0.0.1:8010/api/v1/profile"
headers = {
    "Authorization": f"Bearer {access_token}"
}
data = {
    "height": 168,
    "body_type": "沙漏型",
    "skin_tone": "冷白",
    "style_preference": ["通勤", "简约", "优雅"],
    "budget_range": "中档",
    "avoid_body_parts": ["肩部"]
}

response = requests.post(url, json=data, headers=headers)
print(response.json())
```

---

### 4. 获取用户画像

**curl**:
```bash
curl -X GET "http://127.0.0.1:8010/api/v1/profile" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Python**:
```python
import requests

url = "http://127.0.0.1:8010/api/v1/profile"
headers = {
    "Authorization": f"Bearer {access_token}"
}

response = requests.get(url, headers=headers)
profile = response.json()
print(f"Body Type: {profile['body_type']}")
print(f"Style Preference: {profile['style_preference']}")
```

---

### 5. 更新用户画像

**curl**:
```bash
curl -X PUT "http://127.0.0.1:8010/api/v1/profile" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "style_preference": ["通勤", "简约", "优雅", "休闲"],
    "budget_range": "高档"
  }'
```

---

## 图像识别

### 6. 品类识别

**curl**:
```bash
curl -X POST "http://127.0.0.1:8010/api/v1/recognition/category" \
  -F "file=@/path/to/shirt.jpg"
```

**Python**:
```python
import requests

url = "http://127.0.0.1:8010/api/v1/recognition/category"
files = {
    "file": open("/path/to/shirt.jpg", "rb")
}

response = requests.post(url, files=files)
result = response.json()
print(f"Category: {result['category']}")
print(f"Confidence: {result['confidence']:.2%}")
```

**JavaScript (FormData)**:
```javascript
const url = 'http://127.0.0.1:8010/api/v1/recognition/category';
const formData = new FormData();
formData.append('file', fileInput.files[0]);

fetch(url, {
  method: 'POST',
  body: formData
})
  .then(response => response.json())
  .then(data => {
    console.log(`Category: ${data.category}`);
    console.log(`Confidence: ${data.confidence}`);
  });
```

---

### 7. 颜色识别

**curl**:
```bash
curl -X POST "http://127.0.0.1:8010/api/v1/recognition/colors" \
  -F "file=@/path/to/shirt.jpg"
```

**Python**:
```python
import requests

url = "http://127.0.0.1:8010/api/v1/recognition/colors"
files = {
    "file": open("/path/to/shirt.jpg", "rb")
}

response = requests.post(url, files=files)
result = response.json()

main_color = result["main_color"]
print(f"Main Color: {main_color['name']}")
print(f"RGB: {main_color['rgb']}")
print(f"Hex: {main_color['hex_code']}")

for i, color in enumerate(result["secondary_colors"], 1):
    print(f"Secondary Color {i}: {color['name']} ({color['hex_code']})")
```

---

### 8. 完整图像分析

**curl**:
```bash
curl -X POST "http://127.0.0.1:8010/api/v1/recognition/analyze" \
  -F "file=@/path/to/shirt.jpg"
```

**Python**:
```python
import requests

url = "http://127.0.0.1:8010/api/v1/recognition/analyze"
files = {
    "file": open("/path/to/shirt.jpg", "rb")
}

response = requests.post(url, files=files)
result = response.json()

print(f"Category: {result['category']} (confidence: {result['category_confidence']:.2%})")
print(f"Main Color: {result['main_color']['name']}")
print(f"Style Tags: {', '.join(result['style_tags'])}")
print(f"Feature Vector Length: {len(result['feature_vector'])}")
```

---

## 衣橱管理

### 9. 添加服饰到衣橱

**curl**:
```bash
curl -X POST "http://127.0.0.1:8010/api/v1/wardrobe/garments" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "file=@/path/to/shirt.jpg" \
  -F "category=上衣" \
  -F "main_color_name=蓝" \
  -F "main_color_rgb=52,120,180" \
  -F "main_color_hsv=210.0,71.1,70.6" \
  -F "main_color_hex=#3478b4" \
  -F "style_tags=通勤,简约" \
  -F "fit_type=合身" \
  -F "notes=蓝色衬衫，适合工作日穿着"
```

**Python**:
```python
import requests

url = "http://127.0.0.1:8010/api/v1/wardrobe/garments"
headers = {
    "Authorization": f"Bearer {access_token}"
}
files = {
    "file": open("/path/to/shirt.jpg", "rb")
}
data = {
    "category": "上衣",
    "main_color_name": "蓝",
    "main_color_rgb": "52,120,180",
    "main_color_hsv": "210.0,71.1,70.6",
    "main_color_hex": "#3478b4",
    "style_tags": "通勤,简约",
    "fit_type": "合身",
    "notes": "蓝色衬衫，适合工作日穿着"
}

response = requests.post(url, files=files, data=data, headers=headers)
garment = response.json()
print(f"Garment ID: {garment['garment_id']}")
```

---

### 10. 查询衣橱列表

**curl**:
```bash
# 获取所有服饰（第1页）
curl -X GET "http://127.0.0.1:8010/api/v1/wardrobe/garments?page=1&page_size=20" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# 按品类筛选
curl -X GET "http://127.0.0.1:8010/api/v1/wardrobe/garments?category=上衣" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Python**:
```python
import requests

url = "http://127.0.0.1:8010/api/v1/wardrobe/garments"
headers = {
    "Authorization": f"Bearer {access_token}"
}
params = {
    "page": 1,
    "page_size": 20,
    "category": "上衣"  # 可选筛选
}

response = requests.get(url, headers=headers, params=params)
result = response.json()

print(f"Total garments: {result['total']}")
print(f"Page {result['page']} of {result['total'] // result['page_size'] + 1}")

for garment in result["items"]:
    print(f"- {garment['category']}: {garment['main_color']['name']}")
```

---

### 11. 获取单个服饰详情

**curl**:
```bash
curl -X GET "http://127.0.0.1:8010/api/v1/wardrobe/garments/123e4567-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Python**:
```python
import requests

garment_id = "123e4567-e89b-12d3-a456-426614174000"
url = f"http://127.0.0.1:8010/api/v1/wardrobe/garments/{garment_id}"
headers = {
    "Authorization": f"Bearer {access_token}"
}

response = requests.get(url, headers=headers)
garment = response.json()
print(f"Category: {garment['category']}")
print(f"Color: {garment['main_color']['name']}")
print(f"Styles: {', '.join(garment['style_tags'])}")
```

---

### 12. 更新服饰信息

**curl**:
```bash
curl -X PUT "http://127.0.0.1:8010/api/v1/wardrobe/garments/123e4567-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "style_tags": ["通勤", "简约", "优雅"],
    "fit_type": "宽松",
    "notes": "更新后的备注"
  }'
```

**Python**:
```python
import requests

garment_id = "123e4567-e89b-12d3-a456-426614174000"
url = f"http://127.0.0.1:8010/api/v1/wardrobe/garments/{garment_id}"
headers = {
    "Authorization": f"Bearer {access_token}"
}
data = {
    "style_tags": ["通勤", "简约", "优雅"],
    "fit_type": "宽松",
    "notes": "更新后的备注"
}

response = requests.put(url, json=data, headers=headers)
updated_garment = response.json()
print("Garment updated successfully")
```

---

### 13. 删除服饰

**curl**:
```bash
curl -X DELETE "http://127.0.0.1:8010/api/v1/wardrobe/garments/123e4567-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Python**:
```python
import requests

garment_id = "123e4567-e89b-12d3-a456-426614174000"
url = f"http://127.0.0.1:8010/api/v1/wardrobe/garments/{garment_id}"
headers = {
    "Authorization": f"Bearer {access_token}"
}

response = requests.delete(url, headers=headers)
if response.status_code == 204:
    print("Garment deleted successfully")
```

---

### 14. 整套穿搭拆分（split-outfit）

**端点**: `POST /api/v1/wardrobe/split-outfit`（需登录）

**说明**: 上传一张穿搭图，返回多块裁切预览及品类（如连衣裙、包、上衣/裤子/鞋等）；`save=true` 时按 `selected_indexes` 写入衣橱。拆分策略见 `backend/app/services/outfit_split.py`。

**curl（仅预览）**:
```bash
curl -X POST "http://127.0.0.1:8010/api/v1/wardrobe/split-outfit" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "file=@/path/to/outfit.jpg" \
  -F "save=false"
```

**curl（保存第 0、2 块）**:
```bash
curl -X POST "http://127.0.0.1:8010/api/v1/wardrobe/split-outfit" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "file=@/path/to/outfit.jpg" \
  -F "save=true" \
  -F "selected_indexes=0,2"
```

**响应字段**: `items[]` 含 `category`、`image_url`、`confidence`；入库成功时含 `garment_id`。

---

## 智能穿搭（天气与情绪）

以下端点均在 **`/api/v1/smart-outfit`** 下，**需登录**（`Authorization: Bearer <token>`）。实现见 `backend/app/api/smart_outfit.py`。

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/smart-outfit/weather` | GET | 查询参数：`latitude`、`longitude` |
| `/api/v1/smart-outfit/weather-by-city?name=上海` | GET | 查询参数：`name`（城市名，推荐）；`city` 仅为旧客户端兼容参数 |
| `/api/v1/smart-outfit/upload-reference` | POST | `multipart/form-data`，字段 `file`：参考衣物图 |
| `/api/v1/smart-outfit/generate` | POST | JSON 体，见下方 |

### 生成搭配 `POST /api/v1/smart-outfit/generate`

**请求体（JSON）**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `image_url` | string | 必填，参考图 URL（通常来自 `upload-reference` 返回） |
| `location` | string | 可选，完整地址（省市区街道） |
| `city` | string | 可选，城市名 |
| `address` | object | 可选，结构化地址：`province/city/district/street/full_address/display_address` |
| `weather` | string | 可选，天气描述（如 晴/阴/雨） |
| `temperature` | number | 可选，气温 ℃ |
| `mood` | string | 可选，情绪描述；空字符串则仅按图+天气 |
| `count` | int | 可选，默认 `3`，一次生成套数（1–5） |
| `regeneration_index` | int | 可选，重新生成时递增，便于后端换一批结果 |
| `gender_expression` | float | 可选，0–1 |

**curl**：

```bash
curl -X POST "http://127.0.0.1:8010/api/v1/smart-outfit/generate" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "/uploads/user-id/ref.jpg",
    "location": "上海市浦东新区世纪大道",
    "city": "上海",
    "address": {
      "province": "上海市",
      "city": "上海市",
      "district": "浦东新区",
      "street": "世纪大道",
      "full_address": "上海市浦东新区世纪大道",
      "display_address": "上海市浦东新区"
    },
    "weather": "晴",
    "temperature": 22,
    "mood": "今天想轻松一点",
    "count": 3,
    "regeneration_index": 0
  }'
```
**响应要点**：

- 每套搭配都包含 `ai_recommendation`，结构固定为：
  - `outfit`（搭配名称）
  - `style`（风格）
  - `score`（0-100）
  - `reasons`（固定 3 条）
- 当 AI 返回非 JSON、超时或未配置时，后端会自动 fallback，但仍返回同结构。
- 推荐严格依赖用户衣橱数据；衣橱为空时会返回错误，提示先添加衣物。

**响应示例（AI 正常返回）**：

```json
{
  "success": true,
  "data": {
    "outfits": [
      {
        "outfit_id": "outfit_1",
        "scene": "休闲日常",
        "description": "浅色上衣搭配直筒下装，整体干净轻松。",
        "overall_score": 0.87,
        "items": [
          {"name": "上衣 · 白", "category": "上衣"},
          {"name": "裤子 · 蓝", "category": "裤子"}
        ],
        "ai_recommendation": {
          "outfit": "通勤轻松感组合",
          "style": "简约 · 休闲",
          "score": 88.5,
          "reasons": [
            "优先使用你衣橱中的白色上衣和蓝色下装，复用率高。",
            "风格与当前搭配标签一致，视觉更统一。",
            "22℃晴天适合轻薄分层，通勤与日常都舒适。"
          ]
        }
      }
    ],
    "city": "上海市浦东新区",
    "address": {
      "province": "上海市",
      "city": "上海市",
      "district": "浦东新区",
      "street": "世纪大道",
      "full_address": "上海市浦东新区世纪大道",
      "display_address": "上海市浦东新区"
    },
    "weather": "晴",
    "temperature": 22.0,
    "mood": "今天想轻松一点",
    "weather_fallback": false,
    "message": "ok"
  },
  "error": null,
  "message": "ok"
}
```

**响应示例（AI 解析失败自动 fallback）**：

```json
{
  "success": true,
  "data": {
    "outfits": [
      {
        "outfit_id": "outfit_2",
        "scene": "休闲日常",
        "description": "浅卡其外套配直筒牛仔裤，颜色协调。",
        "overall_score": 0.82,
        "items": [
          {"name": "外套 · 卡其", "category": "外套"},
          {"name": "裤子 · 牛仔", "category": "裤子"}
        ],
        "ai_recommendation": {
          "outfit": "周末轻通勤",
          "style": "简约",
          "score": 82.0,
          "reasons": [
            "优先复用衣橱现有外套与裤装，减少重复购买。",
            "整体风格保持简约，单品标签一致。",
            "已结合当前天气做搭配适配，出行舒适度更高。"
          ]
        }
      }
    ],
    "city": "上海",
    "address": {},
    "weather": "晴",
    "temperature": 22.0,
    "mood": "",
    "weather_fallback": false,
    "message": "ok"
  },
  "error": null,
  "message": "ok"
}
```

### 天气（经纬度）`GET /api/v1/smart-outfit/weather`

```bash
curl -G "http://127.0.0.1:8010/api/v1/smart-outfit/weather" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  --data-urlencode "latitude=31.23" \
  --data-urlencode "longitude=121.47"
```

### 天气（城市名）`GET /api/v1/smart-outfit/weather-by-city`

```bash
curl -G "http://127.0.0.1:8010/api/v1/smart-outfit/weather-by-city" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  --data-urlencode "name=上海"
```

推荐使用 `name` 参数；后端仍兼容旧客户端的 `city=上海`。

### 上传参考图 `POST /api/v1/smart-outfit/upload-reference`

```bash
curl -X POST "http://127.0.0.1:8010/api/v1/smart-outfit/upload-reference" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "file=@/path/to/garment.jpg"
```

---

## 智能分析

### 15. 相似度分析

**curl**:
```bash
curl -X POST "http://127.0.0.1:8010/api/v1/analysis/similarity" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "file=@/path/to/new_shirt.jpg"
```

**Python**:
```python
import requests

url = "http://127.0.0.1:8010/api/v1/analysis/similarity"
headers = {
    "Authorization": f"Bearer {access_token}"
}
files = {
    "file": open("/path/to/new_shirt.jpg", "rb")
}

response = requests.post(url, files=files, headers=headers)
result = response.json()

print(f"Target: {result['target_garment']['category']}")
print(f"Similar garments found: {len(result['similar_garments'])}")
print(f"Duplicate warning: {result['has_duplicate_warning']}")
print(f"Recommendation: {result['recommendation']}")

for garment in result["similar_garments"]:
    print(f"- Similarity: {garment['similarity_score']:.2%} ({garment['similarity_level']})")
```

---

### 16. 搭配推荐

**单图**（`file`，兼容旧客户端）：

**curl**:
```bash
curl -X POST "http://127.0.0.1:8010/api/v1/analysis/outfits?num_outfits=3" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "file=@/path/to/shirt.jpg"
```

**多图**（`files` 重复字段，最多 5 张；合并识别后一次推荐，第一张为主图预览）：

**curl**:
```bash
curl -X POST "http://127.0.0.1:8010/api/v1/analysis/outfits?num_outfits=3" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "files=@/path/to/top.jpg" \
  -F "files=@/path/to/pants.jpg"
```

**Python（单图）**:
```python
import requests

url = "http://127.0.0.1:8010/api/v1/analysis/outfits"
headers = {"Authorization": f"Bearer {access_token}"}
params = {"num_outfits": 3}

with open("/path/to/shirt.jpg", "rb") as f:
    response = requests.post(url, files={"file": f}, headers=headers, params=params)
result = response.json()
```

**Python（多图，`files` 重复）**:
```python
import requests

url = "http://127.0.0.1:8010/api/v1/analysis/outfits"
headers = {"Authorization": f"Bearer {access_token}"}
params = {"num_outfits": 3}

t = open("/path/to/top.jpg", "rb")
p = open("/path/to/pants.jpg", "rb")
try:
    multi = [
        ("files", ("top.jpg", t, "image/jpeg")),
        ("files", ("pants.jpg", p, "image/jpeg")),
    ]
    response = requests.post(url, files=multi, headers=headers, params=params)
finally:
    t.close()
    p.close()

result = response.json()

print(f"Target: {result['target_garment']['category']}")
print(f"Generated {len(result['outfit_cards'])} outfit recommendations:")

for i, outfit in enumerate(result["outfit_cards"], 1):
    print(f"\nOutfit {i}:")
    print(f"  Occasion: {outfit['occasion']}")
    print(f"  Description: {outfit['description']}")
    print(f"  Overall Score: {outfit['overall_score']:.2%}")
    print(f"  Items: {len(outfit['items'])}")
```

---

### 17. 适合度评分

**curl**:
```bash
curl -X POST "http://127.0.0.1:8010/api/v1/analysis/suitability" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "file=@/path/to/dress.jpg"
```

**Python**:
```python
import requests

url = "http://127.0.0.1:8010/api/v1/analysis/suitability"
headers = {
    "Authorization": f"Bearer {access_token}"
}
files = {
    "file": open("/path/to/dress.jpg", "rb")
}

response = requests.post(url, files=files, headers=headers)
result = response.json()

print(f"Overall Suitability: {result['suitability_score']}/100")
print(f"Color Score: {result['color_score']}/100")
print(f"Fit Score: {result['fit_score']}/100")
print(f"Style Score: {result['style_score']}/100")

print("\nReasons:")
print("  scene:", result.get("scene_match_reason") or result["explanation"].get("scene", ""))
print("  body :", result.get("body_fit_reason") or result["explanation"].get("body", ""))
print("  style:", result.get("style_coordination_reason") or result["explanation"].get("style", ""))

print(f"\nRecommended Occasions: {', '.join(result['recommended_occasions'])}")

print("\nSuggestions:")
for suggestion in result["suggestions"]:
    print(f"  - {suggestion}")
```

---

## 完整工作流示例

### Python 完整示例：从注册到分析

```python
import requests
import time

BASE_URL = "http://127.0.0.1:8010/api/v1"

# 1. 注册用户
print("1. Registering user...")
register_data = {
    "username": "demo_user",
    "email": "demo@example.com",
    "password": "DemoPass123"
}
response = requests.post(f"{BASE_URL}/auth/register", json=register_data)
user = response.json()
print(f"   User created: {user['username']}")

# 2. 登录获取 Token
print("\n2. Logging in...")
login_data = {
    "username": "demo_user",
    "password": "DemoPass123"
}
response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
print("   Login successful")

# 3. 创建用户画像
print("\n3. Creating user profile...")
profile_data = {
    "height": 170,
    "body_type": "沙漏",
    "skin_tone": "冷白",
    "style_preference": ["通勤", "简约"],
    "budget_range": "中等",
    "avoid_body_parts": ["腰", "臀"],
}
response = requests.post(f"{BASE_URL}/profile", json=profile_data, headers=headers)
print("   Profile created")

# 4. 图像识别
print("\n4. Analyzing image...")
with open("/path/to/shirt.jpg", "rb") as f:
    files = {"file": f}
    response = requests.post(f"{BASE_URL}/recognition/analyze", files=files)
result = response.json()
print(f"   Category: {result['category']}")
print(f"   Color: {result['main_color']['name']}")
print(f"   Styles: {', '.join(result['style_tags'])}")

# 5. 添加到衣橱
print("\n5. Adding to wardrobe...")
with open("/path/to/shirt.jpg", "rb") as f:
    files = {"file": f}
    data = {
        "category": result["category"],
        "main_color_name": result["main_color"]["name"],
        "main_color_rgb": ",".join(map(str, result["main_color"]["rgb"])),
        "main_color_hsv": ",".join(map(str, result["main_color"]["hsv"])),
        "main_color_hex": result["main_color"]["hex_code"],
        "style_tags": ",".join(result["style_tags"])
    }
    response = requests.post(f"{BASE_URL}/wardrobe/garments", files=files, data=data, headers=headers)
garment = response.json()
print(f"   Garment added: {garment['garment_id']}")

# 6. 相似度分析
print("\n6. Analyzing similarity...")
with open("/path/to/another_shirt.jpg", "rb") as f:
    files = {"file": f}
    response = requests.post(f"{BASE_URL}/analysis/similarity", files=files, headers=headers)
similarity = response.json()
print(f"   Similar items: {len(similarity['similar_garments'])}")
print(f"   Recommendation: {similarity['recommendation']}")

# 7. 搭配推荐（单图 file，或多图重复 files）
print("\n7. Getting outfit recommendations...")
with open("/path/to/shirt.jpg", "rb") as f:
    files = {"file": f}
    response = requests.post(f"{BASE_URL}/analysis/outfits?num_outfits=3", files=files, headers=headers)
outfits = response.json()
print(f"   Generated {len(outfits['outfit_cards'])} outfits")
# 多图示例：files = [("files", f1), ("files", f2)] 见本节「搭配推荐」curl/Python

# 8. 适合度评分
print("\n8. Calculating suitability score...")
with open("/path/to/dress.jpg", "rb") as f:
    files = {"file": f}
    response = requests.post(f"{BASE_URL}/analysis/suitability", files=files, headers=headers)
suitability = response.json()
print(f"   Overall score: {suitability['suitability_score']}/100")

print("\n✓ Complete workflow finished successfully!")
```

---

## 错误处理示例

### Python 错误处理

```python
import requests

def make_api_request(url, method="GET", **kwargs):
    """
    Make API request with error handling
    """
    try:
        if method == "GET":
            response = requests.get(url, **kwargs)
        elif method == "POST":
            response = requests.post(url, **kwargs)
        elif method == "PUT":
            response = requests.put(url, **kwargs)
        elif method == "DELETE":
            response = requests.delete(url, **kwargs)

        # Raise exception for bad status codes
        response.raise_for_status()

        # Return JSON if available
        if response.status_code != 204:  # No Content
            return response.json()
        return None

    except requests.exceptions.HTTPError as e:
        # Handle HTTP errors
        if e.response.status_code == 400:
            print(f"Bad Request: {e.response.json()}")
        elif e.response.status_code == 401:
            print("Unauthorized: Please login again")
        elif e.response.status_code == 403:
            print("Forbidden: You don't have permission")
        elif e.response.status_code == 404:
            print("Not Found: Resource doesn't exist")
        elif e.response.status_code == 422:
            print(f"Validation Error: {e.response.json()}")
        elif e.response.status_code == 500:
            print("Server Error: Please try again later")
        raise

    except requests.exceptions.ConnectionError:
        print("Connection Error: Cannot reach the server")
        raise

    except requests.exceptions.Timeout:
        print("Timeout: Request took too long")
        raise

    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        raise

# Usage
try:
    result = make_api_request(
        "http://127.0.0.1:8010/api/v1/profile",
        method="GET",
        headers={"Authorization": f"Bearer {token}"}
    )
    print(result)
except Exception as e:
    print(f"Failed to get profile: {e}")
```

---

## 性能测试示例

### Python 性能测试

```python
import requests
import time

def test_api_performance(url, files=None, headers=None):
    """
    Test API endpoint performance
    """
    start_time = time.time()

    if files:
        response = requests.post(url, files=files, headers=headers)
    else:
        response = requests.get(url, headers=headers)

    elapsed_time = time.time() - start_time

    print(f"Endpoint: {url}")
    print(f"Status: {response.status_code}")
    print(f"Response Time: {elapsed_time:.3f}s")

    return elapsed_time

# Test image recognition performance
with open("/path/to/test_image.jpg", "rb") as f:
    files = {"file": f}
    elapsed = test_api_performance(
        "http://127.0.0.1:8010/api/v1/recognition/analyze",
        files=files
    )

    if elapsed < 2.0:
        print("✓ Performance requirement met (< 2s)")
    else:
        print("✗ Performance requirement not met")
```

---

## 反馈、分析、Agent 意图、记忆（数据飞轮 / MCP 叙事）

### 提交反馈 `POST /api/v1/feedback/events`（需登录）

`event_type`: `like` | `dislike` | `adopt` | `view`；可选 `garment_id`、`collection_id`、`scene`、`payload`。

```bash
curl -X POST "http://127.0.0.1:8010/api/v1/feedback/events" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"event_type\":\"like\",\"source\":\"analysis_outfit\",\"garment_id\":\"<uuid>\"}"
```

### 分析摘要 `GET /api/v1/analytics/summary`（需登录）

查询参数：`scope=user`（本人）或 `scope=global`（全库汇总，演示用）。

```bash
curl -G "http://127.0.0.1:8010/api/v1/analytics/summary" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  --data-urlencode "scope=user"
```

### 意图路由 `POST /api/v1/agent/intent`（无需登录）

```bash
curl -X POST "http://127.0.0.1:8010/api/v1/agent/intent" \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"今天上海天气怎么样\"}"
```

### 记忆片段 `POST/GET /api/v1/memory/...`（需登录）

- `POST /api/v1/memory/snippets` — JSON：`title`, `content`
- `GET /api/v1/memory/snippets/search?q=关键词&top_k=5`

### 导出反馈 JSONL（离线）

```bash
python scripts/export_feedback_jsonl.py > feedback_events.jsonl
```

（需在 `backend` 可导入 `app`，并已配置 `DATABASE_URL` / `.env`。）

---

## 注意事项

1. **Token 管理**: Access Token 有效期为 24 小时，过期后需要重新登录
2. **文件上传**: 支持 JPEG, PNG, WebP 格式，建议文件大小 < 10MB
3. **并发限制**: 建议单用户并发请求不超过 10 个
4. **错误重试**: 遇到 500 错误时，建议使用指数退避策略重试
5. **图片质量**: 为获得最佳识别效果，建议上传清晰、光线充足的图片

---

## 更多资源

- **Swagger UI**: http://127.0.0.1:8010/docs
- **ReDoc**: http://127.0.0.1:8010/redoc
- **OpenAPI JSON**: http://127.0.0.1:8010/openapi.json
