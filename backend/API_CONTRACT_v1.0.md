# API 契约 v1.0 - 冻结版本

**发布日期**: 2024-01-01
**状态**: ✅ 已冻结 (Frozen)
**向后兼容承诺**: 本版本 API 将保持稳定，不会进行破坏性变更

---

## 契约承诺

### 我们承诺

1. **端点稳定性**: 所有 v1.0 端点路径不会改变
2. **响应格式稳定性**: 响应 JSON 结构不会删除或重命名现有字段
3. **请求格式稳定性**: 必填参数不会增加，现有参数类型不会改变
4. **HTTP 状态码稳定性**: 现有状态码含义不会改变
5. **向后兼容**: 新增功能只会添加可选字段或新端点

### 允许的变更

1. ✅ 添加新的可选请求参数
2. ✅ 在响应中添加新字段
3. ✅ 添加新的 API 端点
4. ✅ 改进错误消息文本
5. ✅ 性能优化（不影响接口）

### 禁止的变更

1. ❌ 删除或重命名现有端点
2. ❌ 删除或重命名响应字段
3. ❌ 改变现有字段的数据类型
4. ❌ 将可选参数改为必填
5. ❌ 改变 HTTP 状态码的语义

---

## 核心端点清单

### 1. 认证 (Authentication)

#### 1.1 注册
- **端点**: `POST /api/v1/auth/register`
- **状态**: ✅ 已冻结
- **请求体**:
  ```typescript
  {
    username: string;  // 必填，3-50字符
    email: string;     // 必填，有效邮箱
    password: string;  // 必填，8-128字符
  }
  ```
- **响应** (201):
  ```typescript
  {
    user_id: string;      // UUID
    username: string;
    email: string;
    is_active: boolean;
    created_at: string;   // ISO 8601
  }
  ```

#### 1.2 登录
- **端点**: `POST /api/v1/auth/login`
- **状态**: ✅ 已冻结
- **请求体**:
  ```typescript
  {
    username: string;  // 必填
    password: string;  // 必填
  }
  ```
- **响应** (200):
  ```typescript
  {
    access_token: string;
    token_type: "bearer";
  }
  ```

---

### 2. 用户画像 (User Profile)

#### 2.1 创建画像
- **端点**: `POST /api/v1/profile`
- **认证**: 必需
- **状态**: ✅ 已冻结
- **请求体**:
  ```typescript
  {
    height?: number;              // 可选，100-250
    body_type?: string;           // 可选，枚举值
    skin_tone?: string;           // 可选，枚举值
    style_preference?: string[];  // 可选，风格数组
    budget_range?: string;        // 可选，枚举值
    avoid_body_parts?: string[];  // 可选，部位数组
  }
  ```
- **响应** (201):
  ```typescript
  {
    profile_id: string;
    user_id: string;
    height: number | null;
    body_type: string | null;
    skin_tone: string | null;
    style_preference: string[];
    budget_range: string | null;
    avoid_body_parts: string[];
    created_at: string;
    updated_at: string;
  }
  ```

#### 2.2 获取画像
- **端点**: `GET /api/v1/profile`
- **认证**: 必需
- **状态**: ✅ 已冻结
- **响应** (200): 同创建画像

#### 2.3 更新画像
- **端点**: `PUT /api/v1/profile`
- **认证**: 必需
- **状态**: ✅ 已冻结
- **请求体**: 同创建画像（所有字段可选）
- **响应** (200): 同创建画像

---

### 3. 图像识别 (Recognition)

#### 3.1 品类识别
- **端点**: `POST /api/v1/recognition/category`
- **认证**: 不需要
- **状态**: ✅ 已冻结
- **请求**: multipart/form-data
  - `file`: 图片文件
- **响应** (200):
  ```typescript
  {
    category: string;           // 品类名称
    confidence: number;         // 0-1
    confidence_level: string;   // 置信度等级
  }
  ```

#### 3.2 颜色识别
- **端点**: `POST /api/v1/recognition/colors`
- **认证**: 不需要
- **状态**: ✅ 已冻结
- **请求**: multipart/form-data
  - `file`: 图片文件
- **响应** (200):
  ```typescript
  {
    main_color: {
      name: string;
      rgb: [number, number, number];
      hsv: [number, number, number];
      hex_code: string;
    };
    secondary_colors: Array<{
      name: string;
      rgb: [number, number, number];
      hsv: [number, number, number];
      hex_code: string;
    }>;
  }
  ```

#### 3.3 完整分析
- **端点**: `POST /api/v1/recognition/analyze`
- **认证**: 不需要
- **状态**: ✅ 已冻结
- **请求**: multipart/form-data
  - `file`: 图片文件
- **响应** (200):
  ```typescript
  {
    category: string;
    category_confidence: number;
    main_color: ColorSchema;
    secondary_colors: ColorSchema[];
    style_tags: string[];
    fit_type: string | null;
    feature_vector: number[];  // 长度 1280
    processing_time: number;
  }
  ```

---

### 4. 衣橱管理 (Wardrobe)

#### 4.1 添加服饰
- **端点**: `POST /api/v1/wardrobe/garments`
- **认证**: 必需
- **状态**: ✅ 已冻结
- **请求**: multipart/form-data
  - `file`: 图片文件（必填）
  - `category`: 品类（必填）
  - `main_color_name`: 主色名称（必填）
  - `main_color_rgb`: RGB值（必填）
  - `main_color_hsv`: HSV值（必填）
  - `main_color_hex`: 十六进制（必填）
  - `style_tags`: 风格标签（可选）
  - `fit_type`: 版型（可选）
  - `notes`: 备注（可选）
- **响应** (201):
  ```typescript
  {
    garment_id: string;
    user_id: string;
    category: string;
    main_color: ColorSchema;
    secondary_colors: ColorSchema[];
    style_tags: string[];
    fit_type: string | null;
    image_url: string;
    feature_vector: number[];
    notes: string | null;
    created_at: string;
  }
  ```

#### 4.2 查询衣橱
- **端点**: `GET /api/v1/wardrobe/garments`
- **认证**: 必需
- **状态**: ✅ 已冻结
- **查询参数**:
  - `page`: 页码（可选，默认1）
  - `page_size`: 每页数量（可选，默认20）
  - `category`: 品类筛选（可选）
- **响应** (200):
  ```typescript
  {
    total: number;
    page: number;
    page_size: number;
    items: GarmentSchema[];
  }
  ```

#### 4.3 获取服饰
- **端点**: `GET /api/v1/wardrobe/garments/{garment_id}`
- **认证**: 必需
- **状态**: ✅ 已冻结
- **响应** (200): 同添加服饰

#### 4.4 更新服饰
- **端点**: `PUT /api/v1/wardrobe/garments/{garment_id}`
- **认证**: 必需
- **状态**: ✅ 已冻结
- **请求体**:
  ```typescript
  {
    category?: string;
    style_tags?: string[];
    fit_type?: string;
    notes?: string;
  }
  ```
- **响应** (200): 同添加服饰

#### 4.5 删除服饰
- **端点**: `DELETE /api/v1/wardrobe/garments/{garment_id}`
- **认证**: 必需
- **状态**: ✅ 已冻结
- **响应** (204): 无内容

---

### 5. 智能分析 (Analysis)

#### 5.1 相似度分析
- **端点**: `POST /api/v1/analysis/similarity`
- **认证**: 必需
- **状态**: ✅ 已冻结
- **请求**: multipart/form-data
  - `file`: 图片文件
- **响应** (200):
  ```typescript
  {
    target_garment: {
      category: string;
      category_confidence: number;
      main_color: ColorSchema;
      secondary_colors: ColorSchema[];
      style_tags: string[];
    };
    similar_garments: Array<{
      garment_id: string;
      similarity_score: number;
      similarity_level: string;
      image_url: string;
      category: string;
      main_color: ColorSchema;
    }>;
    has_duplicate_warning: boolean;
    recommendation: string;
  }
  ```

#### 5.2 搭配推荐
- **端点**: `POST /api/v1/analysis/outfits`
- **认证**: 必需
- **状态**: ✅ 已冻结
- **查询参数**:
  - `num_outfits`: 推荐数量（可选，默认3，范围1-10）
  - `scene`（可选）、`gender_expression`（可选，0–1）
- **请求**: multipart/form-data
  - `file`: 单张图片（可选；与旧客户端兼容）
  - `files`: 多张图片（可选；字段名可重复，最多 5 张；若 `files` 非空则只使用 `files`，否则使用 `file`）
  - 至少提供 `file` 或 `files` 之一；多图时服务端合并识别特征后统一推荐，第一张为主图预览
- **响应** (200):
  ```typescript
  {
    target_garment: RecognitionResult;
    outfit_cards: Array<{
      outfit_id: string;
      items: Array<{
        garment_id: string;
        category: string;
        image_url: string;
        role: string;
      }>;
      occasion: string;
      description: string;
      color_harmony: string;
      color_harmony_score: number;
      style_consistency: number;
      overall_score: number;
    }>;
  }
  ```

#### 5.3 智能穿搭（参考图 + 天气 + 情绪）

> 路径前缀均为 **`/api/v1/smart-outfit`**（与 `app.main` 中 `include_router(..., prefix="/api/v1")` + 路由 `prefix="/smart-outfit"` 一致）。

##### 5.3.1 天气（经纬度）
- **端点**: `GET /api/v1/smart-outfit/weather`
- **认证**: 必需
- **查询参数**: `latitude`, `longitude`

##### 5.3.2 天气（城市名）
- **端点**: `GET /api/v1/smart-outfit/weather-by-city`
- **认证**: 必需
- **查询参数**: `name`（城市名）

##### 5.3.3 上传参考图
- **端点**: `POST /api/v1/smart-outfit/upload-reference`
- **认证**: 必需
- **请求**: `multipart/form-data`，字段 `file`

##### 5.3.4 生成搭配
- **端点**: `POST /api/v1/smart-outfit/generate`
- **认证**: 必需
- **请求**: `application/json`
  - `image_url`: string（必填）
  - `city`, `weather`, `temperature`, `mood`: 可选；`mood` 可为 `""`
  - `count`: 可选，默认 3（1–5）
  - `regeneration_index`: 可选，重新生成时递增
  - `gender_expression`: 可选，0–1
- **响应** (200): 含 `outfits: Array<Record<string, unknown>>` 及天气/城市回显字段

#### 5.4 适合度评分
- **端点**: `POST /api/v1/analysis/suitability`
- **认证**: 必需
- **状态**: ✅ 已冻结
- **前置条件**: 用户必须已创建画像
- **请求**: multipart/form-data
  - `file`: 图片文件
- **响应** (200):
  ```typescript
  {
    garment: RecognitionResult;
    suitability_score: number;  // 0-100
    color_score: number;        // 0-100
    fit_score: number;          // 0-100
    style_score: number;        // 0-100
    explanation: {
      color: string;
      fit: string;
      style: string;
    };
    recommended_occasions: string[];
    suggestions: string[];
  }
  ```

---

## 数据类型定义

### ColorSchema
```typescript
interface ColorSchema {
  name: string;                    // 标准色系名称
  rgb: [number, number, number];   // RGB值 (0-255)
  hsv: [number, number, number];   // HSV值
  hex_code: string;                // 十六进制颜色码
}
```

### RecognitionResult
```typescript
interface RecognitionResult {
  category: string;
  category_confidence: number;
  main_color: ColorSchema;
  secondary_colors: ColorSchema[];
  style_tags: string[];
  fit_type: string | null;
  feature_vector: number[];  // 长度 1280
  processing_time: number;
}
```

---

## 枚举值定义

### 品类 (Category)
```
上衣, 裤子, 裙子, 外套, 鞋, 包
```

### 风格标签 (Style Tags)
```
通勤, 休闲, 正式, 运动, 街头, 学院, 甜美, 简约, 复古, 朋克, 民族, 优雅
```

### 版型 (Fit Type)
```
修身, 合身, 宽松, 超宽松, 落肩
```

### 体型 (Body Type)
```
沙漏型, 梨型, 苹果型, 矩形, 倒三角
```

### 肤色 (Skin Tone)
```
冷白, 暖白, 自然, 小麦, 深色
```

### 预算范围 (Budget Range)
```
平价, 中档, 高档, 奢侈
```

### 身体部位 (Body Parts)
```
肩部, 腰部, 臀部, 腿部
```

---

## 错误响应格式

所有错误响应遵循统一格式：

```typescript
{
  error: {
    code: string;      // 错误码
    message: string;   // 错误描述
    details?: any;     // 详细信息（可选）
  }
}
```

### 标准错误码

| HTTP状态 | 错误码 | 说明 |
|---------|--------|------|
| 400 | BAD_REQUEST | 请求参数错误 |
| 401 | UNAUTHORIZED | 未认证 |
| 403 | FORBIDDEN | 无权限 |
| 404 | NOT_FOUND | 资源不存在 |
| 409 | CONFLICT | 资源冲突 |
| 422 | VALIDATION_ERROR | 数据验证失败 |
| 500 | INTERNAL_ERROR | 服务器错误 |

---

## 性能保证

| 端点类型 | 目标响应时间 | SLA |
|---------|-------------|-----|
| 图像识别 | < 2秒 | 95% |
| 相似度分析 | < 2秒 | 95% |
| 搭配推荐 | < 3秒 | 95% |
| 其他API | < 500ms | 99% |

---

## 版本升级路径

当需要破坏性变更时，我们将：

1. 发布新版本 API (v2.0)
2. 保持 v1.0 至少 12 个月
3. 提前 6 个月通知废弃计划
4. 提供迁移指南和工具

---

## 联系方式

- **技术支持**: support@smartoutfit.example.com
- **API 问题**: api-issues@smartoutfit.example.com
- **文档**: http://127.0.0.1:8010/docs

---

## 变更日志

### v1.0.0 (2024-01-01)
- ✅ 初始版本发布
- ✅ 所有核心端点已冻结
- ✅ API 契约生效

---

**签署**: Smart Outfit Assistant 开发团队
**日期**: 2024-01-01
