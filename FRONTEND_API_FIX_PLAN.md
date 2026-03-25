# 前端 API 对接修复方案

## 问题总结

前端代码假设后端 API 会自动处理图像识别，但实际上需要：
1. 先调用识别 API (`/recognition/analyze`)
2. 再用识别结果调用业务 API

## 需要修复的功能

### 1. 衣橱管理 - 添加服饰

**当前问题**:
- 前端直接上传图片到 `/wardrobe/garments`
- 后端需要 category, main_color 等参数（需要先识别）

**修复方案**:
1. 上传图片到 `/recognition/analyze` 获取识别结果
2. 使用识别结果调用 `/wardrobe/garments` 创建服饰

### 2. 相似度分析

**当前问题**:
- API 返回的数据结构与前端期望不一致

**修复方案**:
- 调整前端代码以匹配后端返回的数据结构

### 3. 搭配推荐

**当前问题**:
- API 返回的数据结构与前端期望不一致

**修复方案**:
- 调整前端代码以匹配后端返回的数据结构

### 4. 适合度评分

**当前问题**:
- API 返回的数据结构与前端期望不一致

**修复方案**:
- 调整前端代码以匹配后端返回的数据结构

## 后端 API 数据结构

### 识别 API (`POST /api/v1/recognition/analyze`)

**请求**:
- `file`: 图片文件

**响应**:
```json
{
  "category": "上衣",
  "category_confidence": 0.95,
  "main_color": {
    "name": "蓝",
    "rgb": [52, 120, 180],
    "hsv": [210.0, 71.1, 70.6],
    "hex_code": "#3478b4"
  },
  "secondary_colors": [...],
  "style_tags": ["通勤", "简约"],
  "fit_type": "标准",
  "feature_vector": [0.1, 0.2, ...] // 1280维
}
```

### 添加服饰 API (`POST /api/v1/wardrobe/garments`)

**请求** (Form Data):
- `file`: 图片文件
- `category`: 品类
- `main_color_name`: 主色名称
- `main_color_rgb`: RGB值 (格式: "r,g,b")
- `main_color_hsv`: HSV值 (格式: "h,s,v")
- `main_color_hex`: 十六进制颜色
- `style_tags`: 风格标签 (逗号分隔)
- `fit_type`: 版型 (可选)
- `notes`: 备注 (可选)

### 获取服饰列表 API (`GET /api/v1/wardrobe/garments`)

**响应**:
```json
{
  "total": 10,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "garment_id": "uuid",
      "category": "上衣",
      "main_color": {...},
      "secondary_colors": [...],
      "style_tags": ["通勤"],
      "fit_type": "标准",
      "image_url": "/uploads/...",
      "created_at": "2024-01-01T00:00:00"
    }
  ]
}
```

### 相似度分析 API (`POST /api/v1/analysis/similarity`)

**响应**:
```json
{
  "target_garment": {
    "category": "上衣",
    "category_confidence": 0.95,
    "main_color": {...},
    "secondary_colors": [...],
    "style_tags": ["通勤"]
  },
  "similar_garments": [
    {
      "garment_id": "uuid",
      "similarity_score": 0.85,
      "similarity_level": "高相似度",
      "image_url": "/uploads/...",
      "category": "上衣",
      "main_color": {...}
    }
  ],
  "has_duplicate_warning": true,
  "recommendation": "您的衣橱中已有 1 件高度相似的单品..."
}
```

### 搭配推荐 API (`POST /api/v1/analysis/outfits`)

**请求参数**:
- `file`: 图片文件
- `num_outfits`: 推荐数量 (query参数, 默认3)

**响应**:
```json
{
  "target_garment": {...},
  "outfit_cards": [
    {
      "outfit_id": "outfit_1",
      "items": [
        {
          "garment_id": "uuid",
          "category": "上衣",
          "image_url": "/uploads/...",
          "main_color": {...}
        }
      ],
      "occasion": "商务",
      "description": "白色衬衫搭配黑色西裤...",
      "color_harmony": "中性色搭配",
      "color_harmony_score": 0.9,
      "style_consistency": 0.95,
      "overall_score": 0.92
    }
  ]
}
```

### 适合度评分 API (`POST /api/v1/analysis/suitability`)

**响应**:
```json
{
  "garment": {
    "category": "上衣",
    "category_confidence": 0.95,
    "main_color": {...},
    "secondary_colors": [...],
    "style_tags": ["甜美"],
    "fit_type": "修身"
  },
  "suitability_score": 75,
  "color_score": 80,
  "fit_score": 70,
  "style_score": 75,
  "explanation": {
    "color": "粉色与您的冷白肤色搭配度较高...",
    "fit": "修身版型可能会强化肩部线条...",
    "style": "甜美风格与您的通勤偏好有一定差异"
  },
  "recommended_occasions": ["约会", "聚会"],
  "suggestions": [
    "建议选择落肩或宽松版型...",
    "可搭配简约配饰平衡甜美感"
  ]
}
```

## 修复优先级

1. ✅ 用户画像 - 已修复
2. 🔧 衣橱管理 - 需要修复添加服饰流程
3. 🔧 相似度分析 - 需要调整数据结构映射
4. 🔧 搭配推荐 - 需要调整数据结构映射
5. 🔧 适合度评分 - 需要调整数据结构映射

## 下一步

创建修复后的代码文件。
