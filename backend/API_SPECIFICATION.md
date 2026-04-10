# 智能穿搭助手 API 规范文档 v1.0

## 概述

本文档定义了智能穿搭助手系统的 RESTful API 规范。所有 API 端点遵循统一的设计原则和响应格式。

### 基础信息

- **Base URL**: `http://127.0.0.1:8010/api/v1`
- **协议**: HTTP/HTTPS
- **数据格式**: JSON
- **字符编码**: UTF-8
- **API 版本**: v1.0

### 认证方式

使用 JWT (JSON Web Token) Bearer Token 认证：

```http
Authorization: Bearer <access_token>
```

Token 有效期：24 小时（可配置）

---

## 通用规范

### HTTP 状态码

| 状态码 | 说明 | 使用场景 |
|--------|------|----------|
| 200 | OK | 请求成功 |
| 201 | Created | 资源创建成功 |
| 204 | No Content | 删除成功（无返回内容）|
| 400 | Bad Request | 请求参数错误 |
| 401 | Unauthorized | 未认证或 Token 无效 |
| 403 | Forbidden | 无权限访问 |
| 404 | Not Found | 资源不存在 |
| 409 | Conflict | 资源冲突（如重复注册）|
| 422 | Unprocessable Entity | 数据验证失败 |
| 500 | Internal Server Error | 服务器内部错误 |

### 统一响应格式

#### 成功响应

```json
{
  "data": { ... },
  "message": "操作成功"
}
```

#### 错误响应

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "错误描述",
    "details": { ... }
  }
}
```

### 分页参数

所有列表接口支持分页：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| page | integer | 否 | 1 | 页码（从 1 开始）|
| page_size | integer | 否 | 20 | 每页数量（1-100）|

分页响应格式：

```json
{
  "total": 100,
  "page": 1,
  "page_size": 20,
  "items": [ ... ]
}
```

---

## API 端点详细说明

## 0. AI 穿搭风格分（Predict）

### 0.1 获取穿搭风格分

**端点**: `POST /predict`

**描述**: 基于上装/下装/颜色/季节/场景进行风格评分，并可在低置信度场景触发外部增强。

**请求头**: 无需认证

**请求体**:
```json
{
  "top": "衬衫",
  "bottom": "牛仔裤",
  "color_top": "白色",
  "color_bottom": "蓝色",
  "season": "春季",
  "occasion": "通勤"
}
```

**成功响应** (200 OK):
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

**字段补充说明**:

1. `source`: `local`（仅本地推理）或 `hybrid`（本地+外部增强）
2. `fallback_reason`: `low_confidence` / `small_margin` / `external_failed` / `null`
3. `model_version_external`: 未触发增强时为 `null`

## 1. 认证模块 (Authentication)

### 1.1 用户注册

**端点**: `POST /auth/register`

**描述**: 创建新用户账号

**请求头**: 无需认证

**请求体**:
```json
{
  "username": "string (3-50字符，字母数字下划线)",
  "email": "string (有效邮箱格式)",
  "password": "string (8-128字符，至少包含字母和数字)"
}
```

**成功响应** (201 Created):
```json
{
  "user_id": "uuid",
  "username": "string",
  "email": "string",
  "is_active": true,
  "created_at": "2024-01-01T00:00:00Z"
}
```

**错误响应**:
- 400: 用户名或邮箱已存在
- 422: 数据验证失败

**示例**:
```bash
curl -X POST "http://127.0.0.1:8010/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "SecurePass123"
  }'
```

---

### 1.2 用户登录

**端点**: `POST /auth/login`

**描述**: 用户登录获取访问令牌

**请求头**: 无需认证

**请求体**:
```json
{
  "username": "string",
  "password": "string"
}
```

**成功响应** (200 OK):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**错误响应**:
- 401: 用户名或密码错误
- 403: 账号未激活

**示例**:
```bash
curl -X POST "http://127.0.0.1:8010/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "SecurePass123"
  }'
```

---

## 2. 用户画像模块 (User Profile)

### 2.1 创建用户画像

**端点**: `POST /profile`

**描述**: 创建用户个人画像信息

**请求头**: 需要认证

**请求体**:
```json
{
  "height": 170,
  "body_type": "沙漏型",
  "skin_tone": "冷白",
  "style_preference": ["通勤", "简约"],
  "budget_range": "中档",
  "avoid_body_parts": ["肩部"]
}
```

**字段说明**:
| 字段 | 类型 | 必填 | 说明 | 有效值 |
|------|------|------|------|--------|
| height | integer | 否 | 身高（cm）| 100-250 |
| body_type | string | 否 | 体型 | 沙漏型/梨型/苹果型/矩形/倒三角 |
| skin_tone | string | 否 | 肤色 | 冷白/暖白/自然/小麦/深色 |
| style_preference | array | 否 | 风格偏好 | 见风格列表 |
| budget_range | string | 否 | 预算范围 | 平价/中档/高档/奢侈 |
| avoid_body_parts | array | 否 | 不希望强化的部位 | 肩部/腰部/臀部/腿部 |

**风格列表**: 通勤, 休闲, 正式, 运动, 街头, 学院, 甜美, 简约, 复古, 朋克, 民族, 优雅

**成功响应** (201 Created):
```json
{
  "profile_id": "uuid",
  "user_id": "uuid",
  "height": 170,
  "body_type": "沙漏型",
  "skin_tone": "冷白",
  "style_preference": ["通勤", "简约"],
  "budget_range": "中档",
  "avoid_body_parts": ["肩部"],
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

**错误响应**:
- 400: 画像已存在（使用 PUT 更新）
- 422: 数据验证失败

---

### 2.2 获取用户画像

**端点**: `GET /profile`

**描述**: 获取当前用户的画像信息

**请求头**: 需要认证

**成功响应** (200 OK):
```json
{
  "profile_id": "uuid",
  "user_id": "uuid",
  "height": 170,
  "body_type": "沙漏型",
  "skin_tone": "冷白",
  "style_preference": ["通勤", "简约"],
  "budget_range": "中档",
  "avoid_body_parts": ["肩部"],
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

**错误响应**:
- 404: 画像不存在

---

### 2.3 更新用户画像

**端点**: `PUT /profile`

**描述**: 更新用户画像信息（部分更新）

**请求头**: 需要认证

**请求体**: 同创建画像，所有字段可选

**成功响应** (200 OK): 同获取画像

**错误响应**:
- 404: 画像不存在（使用 POST 创建）
- 422: 数据验证失败

---

## 3. 图像识别模块 (Recognition)

### 3.1 品类识别

**端点**: `POST /recognition/category`

**描述**: 识别服饰品类

**请求头**: 无需认证

**请求体**: `multipart/form-data`
- `file`: 图片文件（JPEG, PNG, WebP）

**成功响应** (200 OK):
```json
{
  "category": "上衣",
  "confidence": 0.85,
  "confidence_level": "高置信度"
}
```

**支持的品类**:
- 上衣 (Tops)
- 裤子 (Pants)
- 裙子 (Skirts)
- 外套 (Outerwear)
- 鞋 (Shoes)
- 包 (Bags)

**错误响应**:
- 400: 文件格式错误或文件为空
- 500: 识别失败

**示例**:
```bash
curl -X POST "http://127.0.0.1:8010/api/v1/recognition/category" \
  -F "file=@/path/to/image.jpg"
```

---

### 3.2 颜色识别

**端点**: `POST /recognition/colors`

**描述**: 提取服饰主色和辅助色

**请求头**: 无需认证

**请求体**: `multipart/form-data`
- `file`: 图片文件

**成功响应** (200 OK):
```json
{
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
  ]
}
```

**标准色系**: 红, 橙, 黄, 绿, 蓝, 紫, 黑, 白, 灰, 棕

---

### 3.3 完整图像分析

**端点**: `POST /recognition/analyze`

**描述**: 完整的图像识别分析（品类+颜色+风格+特征向量）

**请求头**: 无需认证

**请求体**: `multipart/form-data`
- `file`: 图片文件

**成功响应** (200 OK):
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
  "secondary_colors": [ ... ],
  "style_tags": ["通勤", "简约"],
  "fit_type": null,
  "feature_vector": [0.123, 0.456, ...],
  "processing_time": 1.23
}
```

**性能要求**: < 2 秒

---

## 4. 衣橱管理模块 (Wardrobe)

### 4.1 添加服饰

**端点**: `POST /wardrobe/garments`

**描述**: 添加服饰到衣橱

**请求头**: 需要认证

**请求体**: `multipart/form-data`
- `file`: 图片文件（必填）
- `category`: 品类（必填）
- `main_color_name`: 主色名称（必填）
- `main_color_rgb`: RGB 值，格式 "r,g,b"（必填）
- `main_color_hsv`: HSV 值，格式 "h,s,v"（必填）
- `main_color_hex`: 十六进制颜色码（必填）
- `style_tags`: 风格标签，逗号分隔（可选）
- `fit_type`: 版型（可选）
- `notes`: 备注（可选）

**成功响应** (201 Created):
```json
{
  "garment_id": "uuid",
  "user_id": "uuid",
  "category": "上衣",
  "main_color": { ... },
  "secondary_colors": [],
  "style_tags": ["通勤", "简约"],
  "fit_type": "修身",
  "image_url": "/uploads/user123/image.jpg",
  "feature_vector": [ ... ],
  "notes": "蓝色衬衫",
  "created_at": "2024-01-01T00:00:00Z"
}
```

---

### 4.2 查询衣橱

**端点**: `GET /wardrobe/garments`

**描述**: 获取用户衣橱列表（支持分页和筛选）

**请求头**: 需要认证

**查询参数**:
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| page | integer | 否 | 1 | 页码 |
| page_size | integer | 否 | 20 | 每页数量 |
| category | string | 否 | - | 按品类筛选 |

**成功响应** (200 OK):
```json
{
  "total": 50,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "garment_id": "uuid",
      "category": "上衣",
      "main_color": { ... },
      "style_tags": ["通勤"],
      "image_url": "/uploads/user123/image.jpg",
      "created_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

---

### 4.3 获取单个服饰

**端点**: `GET /wardrobe/garments/{garment_id}`

**描述**: 获取服饰详情

**请求头**: 需要认证

**路径参数**:
- `garment_id`: 服饰 UUID

**成功响应** (200 OK): 同添加服饰响应

**错误响应**:
- 400: 无效的 UUID 格式
- 403: 无权访问（不是自己的服饰）
- 404: 服饰不存在

---

### 4.4 更新服饰

**端点**: `PUT /wardrobe/garments/{garment_id}`

**描述**: 更新服饰信息

**请求头**: 需要认证

**请求体**:
```json
{
  "category": "上衣",
  "style_tags": ["通勤", "简约"],
  "fit_type": "宽松",
  "notes": "更新后的备注"
}
```

所有字段可选，只更新提供的字段。

**成功响应** (200 OK): 同获取服饰响应

---

### 4.5 删除服饰

**端点**: `DELETE /wardrobe/garments/{garment_id}`

**描述**: 删除服饰

**请求头**: 需要认证

**成功响应** (204 No Content): 无返回内容

**错误响应**:
- 403: 无权删除
- 404: 服饰不存在

---

## 5. 分析模块 (Analysis)

### 5.1 相似度分析

**端点**: `POST /analysis/similarity`

**描述**: 分析上传服饰与衣橱中服饰的相似度

**请求头**: 需要认证

**请求体**: `multipart/form-data`
- `file`: 图片文件

**成功响应** (200 OK):
```json
{
  "target_garment": {
    "category": "上衣",
    "main_color": { ... },
    "style_tags": ["通勤", "简约"]
  },
  "similar_garments": [
    {
      "garment_id": "uuid",
      "similarity_score": 0.85,
      "similarity_level": "高相似度",
      "image_url": "/uploads/user123/image.jpg",
      "category": "上衣",
      "main_color": { ... }
    }
  ],
  "has_duplicate_warning": true,
  "recommendation": "您的衣橱中已有 1 件高度相似的单品，建议谨慎购买。"
}
```

**相似度等级**:
- 高相似度: ≥ 0.8
- 中相似度: 0.5 - 0.8
- 低相似度: < 0.5

**性能要求**: < 2 秒

---

### 5.2 搭配推荐

**端点**: `POST /api/v1/analysis/outfits`

**描述**: 为上传的服饰生成搭配方案；支持单图或多图（多图合并识别后一次推荐）

**请求头**: 需要认证

**请求体**: `multipart/form-data`
- `file`: 单张图片（可选，兼容旧客户端）
- `files`: 多张图片（可选；同一字段名多次，最多 5 张；若 `files` 非空则忽略单独的 `file`）
- 至少提供 `file` 或 `files` 之一

**查询参数**:
- `num_outfits`: 推荐数量（1-10，默认 3）

**成功响应** (200 OK):
```json
{
  "target_garment": {
    "category": "上衣",
    "main_color": { ... },
    "style_tags": ["简约", "通勤"]
  },
  "outfit_cards": [
    {
      "outfit_id": "outfit_1",
      "items": [
        {
          "garment_id": "uuid",
          "category": "裤子",
          "image_url": "/uploads/user123/pants.jpg",
          "role": "下装"
        }
      ],
      "occasion": "商务",
      "description": "白色衬衫搭配黑色西裤，适合正式场合",
      "color_harmony": "中性色搭配",
      "color_harmony_score": 0.9,
      "style_consistency": 0.95,
      "overall_score": 0.92
    }
  ]
}
```

**性能要求**: < 3 秒

---

### 5.3 智能穿搭（参考图 + 天气 + 情绪）

**Base 路径前缀**: 与其它 v1 接口相同，为 `/api/v1`。本节端点完整路径形如 **`/api/v1/smart-outfit/...`**（勿省略 `/v1`）。

#### 5.3.1 天气（经纬度）

**端点**: `GET /api/v1/smart-outfit/weather`

**描述**: 根据 GPS 经纬度返回城市名、气温、天气中文描述等（Open-Meteo）。

**请求头**: 需要认证

**查询参数**:
- `latitude`: 纬度（float）
- `longitude`: 经度（float）

#### 5.3.2 天气（城市名）

**端点**: `GET /api/v1/smart-outfit/weather-by-city`

**描述**: 手动切换城市时使用。

**查询参数**:
- `name`: 城市名（如 `上海`）

#### 5.3.3 上传参考衣物图

**端点**: `POST /api/v1/smart-outfit/upload-reference`

**请求体**: `multipart/form-data`
- `file`: 图片文件

**成功响应** (200 OK): JSON 含 `image_url`，供生成接口使用。

#### 5.3.4 生成多套搭配

**端点**: `POST /api/v1/smart-outfit/generate`

**描述**: 结合参考图、城市/天气/气温与可选情绪文本，优先从衣橱组合多套搭配；重新生成时保持请求体一致并递增 `regeneration_index`。

**请求头**: 需要认证

**请求体**: `application/json`
- `image_url` (string, 必填)
- `location`（可选，完整地址文本）
- `city`, `weather`, `temperature`, `mood`（可选；`mood` 可为空字符串）
- `address`（可选，结构化地址对象：`province/city/district/street/full_address/display_address`）
- `count`（可选，默认 3，范围 1–5）
- `regeneration_index`（可选，非负整数）
- `gender_expression`（可选，0.0–1.0）

**成功响应** (200 OK): JSON 含 `outfits`（数组，每项含效果图 URL、单品列表、风格与天气适配说明等），以及 `city`、`address`、`weather`、`temperature`、`mood`、`weather_fallback` 等。

**`outfits[i].ai_recommendation` 结构**:
- `outfit`: string，推荐标题
- `style`: string，推荐风格
- `score`: number，范围 0-100
- `reasons`: string[3]，固定 3 条推荐理由

**AI 推荐解析规则**:
- 后端向 AI 发送严格 JSON Prompt（只允许 `outfit/style/score/reasons`）。
- 后端强制解析 JSON；若 AI 返回非 JSON、字段缺失、超时或未配置，将自动 fallback。
- fallback 仍返回相同结构，保证前端渲染稳定。

**业务约束**:
- 推荐必须结合用户衣橱数据。
- 若衣橱为空，接口返回 400，并提示先添加衣物后再生成推荐。

---

### 5.4 适合度评分

**端点**: `POST /analysis/suitability`

**描述**: 基于用户画像评估服饰适合度

**请求头**: 需要认证

**前置条件**: 用户必须已创建画像

**请求体**: `multipart/form-data`
- `file`: 图片文件

**成功响应** (200 OK):
```json
{
  "garment": {
    "category": "上衣",
    "main_color": { ... },
    "style_tags": ["甜美"],
    "fit_type": "修身"
  },
  "suitability_score": 75,
  "color_score": 80,
  "fit_score": 70,
  "style_score": 75,
  "explanation": {
    "color": "粉色与您的冷白肤色搭配度较高，能提亮肤色",
    "fit": "修身版型可能会强化肩部线条，建议选择落肩款式",
    "style": "甜美风格与您的通勤偏好有一定差异"
  },
  "recommended_occasions": ["约会", "聚会"],
  "suggestions": [
    "建议选择落肩或宽松版型以避免强化肩部",
    "可搭配简约配饰平衡甜美感"
  ]
}
```

**评分说明**:
- 90-100: 非常适合
- 70-89: 比较适合
- 50-69: 一般适合
- < 50: 不太适合

**错误响应**:
- 404: 用户画像不存在

---

## 6. 数据字典

### 6.1 品类 (Category)

| 值 | 说明 | 英文 |
|----|------|------|
| 上衣 | 衬衫、T恤、毛衣等 | Tops |
| 裤子 | 长裤、短裤等 | Pants |
| 裙子 | 各类裙装 | Skirts |
| 外套 | 夹克、大衣等 | Outerwear |
| 鞋 | 各类鞋履 | Shoes |
| 包 | 各类包袋 | Bags |

### 6.2 风格标签 (Style Tags)

通勤, 休闲, 正式, 运动, 街头, 学院, 甜美, 简约, 复古, 朋克, 民族, 优雅

### 6.3 版型 (Fit Type)

修身, 合身, 宽松, 超宽松, 落肩

### 6.4 体型 (Body Type)

沙漏型, 梨型, 苹果型, 矩形, 倒三角

### 6.5 肤色 (Skin Tone)

冷白, 暖白, 自然, 小麦, 深色

### 6.6 预算范围 (Budget Range)

平价, 中档, 高档, 奢侈

### 6.7 身体部位 (Body Parts)

肩部, 腰部, 臀部, 腿部

---

## 7. 错误码参考

| 错误码 | HTTP 状态 | 说明 |
|--------|-----------|------|
| VALIDATION_ERROR | 422 | 数据验证失败 |
| AUTHENTICATION_ERROR | 401 | 认证失败 |
| AUTHORIZATION_ERROR | 403 | 权限不足 |
| NOT_FOUND | 404 | 资源不存在 |
| CONFLICT | 409 | 资源冲突 |
| IMAGE_PROCESSING_ERROR | 500 | 图像处理失败 |
| INTERNAL_ERROR | 500 | 服务器内部错误 |

---

## 8. 性能指标

| 端点 | 目标响应时间 | 说明 |
|------|--------------|------|
| 图像识别 | < 2 秒 | 单张图片完整识别 |
| 相似度分析 | < 2 秒 | 与衣橱对比 |
| 搭配推荐 | < 3 秒 | 生成 3 套搭配 |
| 其他 API | < 500 毫秒 | 数据库操作 |

---

## 9. 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| v1.0 | 2024-01-01 | 初始版本 |

---

## 10. 联系方式

- **技术支持**: support@smartoutfit.example.com
- **API 文档**: http://127.0.0.1:8010/docs
- **ReDoc 文档**: http://127.0.0.1:8010/redoc
