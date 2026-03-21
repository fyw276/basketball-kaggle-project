# 技术设计文档 - 智能穿搭助手

## 概述

智能穿搭助手是一个多端协同的智能穿搭决策系统，通过轻量级图像识别技术和多维度推荐算法，帮助用户解决重复购买、搭配不确定性和适合度判断三大核心痛点。

### 设计目标

- 提供快速响应的图像识别服务（单张图片 < 2 秒）
- 实现准确的相似度计算和重复预警（相似度计算 < 2 秒）
- 生成个性化的搭配推荐方案（推荐生成 < 3 秒）
- 支持多端访问（移动端、CLI、MCP 服务）
- 保证用户数据安全和隐私保护

### 技术栈选择

**后端服务:**
- FastAPI (Python 3.9+): 高性能异步 Web 框架，原生支持 OpenAPI 文档
- TensorFlow Lite / PyTorch Mobile: 轻量级深度学习推理引擎
- MobileNetV2: 轻量级 CNN 模型，适合移动端和边缘计算
- PostgreSQL: 关系型数据库，存储用户和衣橱数据
- Redis: 缓存层，优化重复请求响应时间
- NumPy: 高效的数值计算库，用于特征向量运算

**移动端:**
- Flutter 3.x: 跨平台移动应用框架
- Provider / Riverpod: 状态管理
- Dio: HTTP 客户端
- Image Picker: 相机和相册访问

**CLI 工具:**
- Python Click: 命令行接口框架
- Rich: 终端美化输出

**MCP 服务:**
- MCP Python SDK: Model Context Protocol 实现
- FastAPI 集成: 复用后端业务逻辑

## 架构设计

### 整体架构

系统采用分层架构，包含以下主要组件：

```
┌─────────────────────────────────────────────────────────┐
│                    客户端层                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Flutter App  │  │  CLI Tool    │  │ MCP Service  │  │
│  │  (iOS/Android)│  │              │  │              │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                          │
                          │ HTTPS / RESTful API
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    API 网关层                            │
│  ┌──────────────────────────────────────────────────┐  │
│  │  FastAPI Router (认证、限流、日志)                │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    业务逻辑层                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │用户画像管理  │  │  衣橱管理    │  │  图像识别    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │相似度分析    │  │  搭配推荐    │  │  适合度评分  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    数据访问层                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ PostgreSQL   │  │    Redis     │  │ 文件存储     │  │
│  │  (用户数据)  │  │   (缓存)     │  │  (图片)      │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 模块划分

**1. 认证与授权模块 (Auth Module)**
- 用户注册、登录
- JWT Token 生成与验证
- 密码加密（bcrypt）

**2. 用户画像管理模块 (User Profile Manager)**
- 用户画像 CRUD 操作
- 画像数据验证
- 画像数据持久化

**3. 图像识别模块 (Image Recognition Module)**
- 图像预处理（缩放、归一化）
- MobileNetV2 模型推理
- 品类分类（6 类）
- 颜色识别与聚类（K-Means）
- 风格标签识别

**4. 特征提取模块 (Feature Extraction Module)**
- 使用 MobileNetV2 倒数第二层作为特征提取器
- 生成 1280 维特征向量
- 特征向量归一化

**5. 衣橱管理模块 (Wardrobe Manager)**
- 服饰单品 CRUD 操作
- 按品类、颜色、风格筛选
- 图片存储管理

**6. 相似度分析模块 (Similarity Analyzer)**
- 余弦相似度计算
- 批量相似度对比
- 相似度阈值判断（高/中/低）

**7. 搭配推荐模块 (Outfit Recommender)**
- 基于品类的搭配规则引擎
- 颜色搭配规则（同色系、邻近色、互补色）
- 风格一致性匹配
- 搭配方案生成与排序

**8. 适合度评分模块 (Suitability Scorer)**
- 颜色适合度评分（肤色匹配）
- 版型适合度评分（体型匹配）
- 风格适合度评分（偏好匹配）
- 综合评分计算（加权平均）
- 评分说明生成

## 组件与接口

### 核心组件

#### 1. ImageRecognizer

```python
class ImageRecognizer:
    """图像识别组件"""

    def __init__(self, model_path: str):
        """初始化模型"""
        pass

    def recognize(self, image: Image) -> RecognitionResult:
        """
        识别服饰图片

        Args:
            image: PIL Image 对象

        Returns:
            RecognitionResult: 包含品类、颜色、风格标签
        """
        pass

    def extract_features(self, image: Image) -> np.ndarray:
        """
        提取特征向量

        Args:
            image: PIL Image 对象

        Returns:
            np.ndarray: 1280 维特征向量
        """
        pass
```

#### 2. SimilarityAnalyzer

```python
class SimilarityAnalyzer:
    """相似度分析组件"""

    def calculate_similarity(
        self,
        feature1: np.ndarray,
        feature2: np.ndarray
    ) -> float:
        """
        计算两个特征向量的余弦相似度

        Args:
            feature1: 特征向量 1
            feature2: 特征向量 2

        Returns:
            float: 相似度分数 [0, 1]
        """
        pass

    def find_similar_garments(
        self,
        target_feature: np.ndarray,
        wardrobe_features: List[Tuple[str, np.ndarray]],
        threshold: float = 0.5
    ) -> List[SimilarityMatch]:
        """
        在衣橱中查找相似服饰

        Args:
            target_feature: 目标服饰特征向量
            wardrobe_features: 衣橱中的服饰特征列表
            threshold: 相似度阈值

        Returns:
            List[SimilarityMatch]: 相似度匹配结果列表
        """
        pass
```

#### 3. OutfitRecommender

```python
class OutfitRecommender:
    """搭配推荐组件"""

    def __init__(self, color_rules: ColorRules, style_rules: StyleRules):
        """初始化推荐规则"""
        pass

    def recommend_outfits(
        self,
        target_garment: Garment,
        wardrobe: List[Garment],
        user_profile: UserProfile,
        num_outfits: int = 3
    ) -> List[OutfitCard]:
        """
        生成搭配推荐方案

        Args:
            target_garment: 目标服饰
            wardrobe: 用户衣橱
            user_profile: 用户画像
            num_outfits: 推荐方案数量

        Returns:
            List[OutfitCard]: 搭配方案列表
        """
        pass
```

#### 4. SuitabilityScorer

```python
class SuitabilityScorer:
    """适合度评分组件"""

    def calculate_score(
        self,
        garment: Garment,
        user_profile: UserProfile
    ) -> SuitabilityResult:
        """
        计算服饰适合度评分

        Args:
            garment: 服饰单品
            user_profile: 用户画像

        Returns:
            SuitabilityResult: 包含总分和各维度分数
        """
        pass

    def _color_score(self, garment_color: Color, skin_tone: str) -> float:
        """计算颜色适合度"""
        pass

    def _fit_score(self, garment_fit: str, body_type: str, avoid_parts: List[str]) -> float:
        """计算版型适合度"""
        pass

    def _style_score(self, garment_style: List[str], style_preference: List[str]) -> float:
        """计算风格适合度"""
        pass
```

### API 接口设计

#### 认证接口

**POST /api/v1/auth/register**
```json
Request:
{
  "username": "string",
  "email": "string",
  "password": "string"
}

Response:
{
  "user_id": "string",
  "username": "string",
  "created_at": "datetime"
}
```

**POST /api/v1/auth/login**
```json
Request:
{
  "username": "string",
  "password": "string"
}

Response:
{
  "access_token": "string",
  "token_type": "bearer",
  "expires_in": 3600
}
```

#### 用户画像接口

**POST /api/v1/profile**
```json
Request:
{
  "height": 170,
  "body_type": "偏瘦",
  "skin_tone": "冷白",
  "style_preference": ["通勤", "简约"],
  "budget_range": "中等",
  "avoid_body_parts": ["肩"]
}

Response:
{
  "profile_id": "string",
  "user_id": "string",
  "created_at": "datetime"
}
```

**GET /api/v1/profile**
```json
Response:
{
  "profile_id": "string",
  "height": 170,
  "body_type": "偏瘦",
  "skin_tone": "冷白",
  "style_preference": ["通勤", "简约"],
  "budget_range": "中等",
  "avoid_body_parts": ["肩"]
}
```

**PUT /api/v1/profile**
```json
Request:
{
  "height": 172,
  "body_type": "微胖"
}

Response:
{
  "profile_id": "string",
  "updated_at": "datetime"
}
```

#### 衣橱管理接口

**POST /api/v1/wardrobe/garments**
```json
Request (multipart/form-data):
{
  "image": "file",
  "manual_category": "上衣" (optional),
  "notes": "string" (optional)
}

Response:
{
  "garment_id": "string",
  "category": "上衣",
  "main_color": {"name": "蓝色", "rgb": [0, 100, 200], "hsv": [210, 100, 78]},
  "style_tags": ["通勤", "简约"],
  "image_url": "string",
  "created_at": "datetime"
}
```

**GET /api/v1/wardrobe/garments**
```json
Query Parameters:
- category: string (optional)
- color: string (optional)
- style: string (optional)
- page: int (default: 1)
- page_size: int (default: 20)

Response:
{
  "total": 50,
  "page": 1,
  "page_size": 20,
  "garments": [
    {
      "garment_id": "string",
      "category": "上衣",
      "main_color": {"name": "蓝色", "rgb": [0, 100, 200]},
      "style_tags": ["通勤"],
      "image_url": "string",
      "created_at": "datetime"
    }
  ]
}
```

**DELETE /api/v1/wardrobe/garments/{garment_id}**
```json
Response:
{
  "message": "Garment deleted successfully"
}
```

#### 相似度分析接口

**POST /api/v1/analysis/similarity**
```json
Request (multipart/form-data):
{
  "image": "file"
}

Response:
{
  "target_garment": {
    "category": "上衣",
    "main_color": {"name": "蓝色"},
    "style_tags": ["通勤"]
  },
  "similar_garments": [
    {
      "garment_id": "string",
      "similarity_score": 0.85,
      "similarity_level": "高相似度",
      "image_url": "string",
      "category": "上衣",
      "main_color": {"name": "深蓝色"}
    }
  ],
  "has_duplicate_warning": true,
  "recommendation": "您的衣橱中已有相似单品，建议谨慎购买"
}
```

#### 搭配推荐接口

**POST /api/v1/recommendations/outfits**
```json
Request (multipart/form-data):
{
  "image": "file"
}

Response:
{
  "target_garment": {
    "category": "上衣",
    "main_color": {"name": "白色"},
    "style_tags": ["简约"]
  },
  "outfit_cards": [
    {
      "outfit_id": "string",
      "items": [
        {
          "garment_id": "string",
          "category": "上衣",
          "image_url": "string",
          "role": "target"
        },
        {
          "garment_id": "string",
          "category": "裤子",
          "image_url": "string",
          "role": "bottom"
        },
        {
          "garment_id": "string",
          "category": "鞋",
          "image_url": "string",
          "role": "shoes"
        }
      ],
      "occasion": "商务",
      "description": "白色衬衫搭配黑色西裤和皮鞋，适合正式场合",
      "color_harmony": "经典黑白配",
      "style_consistency": 0.9
    }
  ]
}
```

#### 适合度评分接口

**POST /api/v1/analysis/suitability**
```json
Request (multipart/form-data):
{
  "image": "file"
}

Response:
{
  "garment": {
    "category": "上衣",
    "main_color": {"name": "粉色"},
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

## 数据模型

### 用户模型 (User)

```python
class User(BaseModel):
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password_hash: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True
```

**数据库表结构:**
```sql
CREATE TABLE users (
    user_id UUID PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
```

### 用户画像模型 (UserProfile)

```python
class UserProfile(BaseModel):
    profile_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    height: int = Field(ge=100, le=250)  # 厘米
    body_type: str = Field(...)  # 偏瘦/微胖/梨形/倒三角/沙漏/矩形
    skin_tone: str = Field(...)  # 冷白/黄皮/小麦/深色
    style_preference: List[str] = Field(...)  # 通勤/学院/甜酷/简约/街头/复古等
    budget_range: str = Field(...)  # 经济/中等/高端
    avoid_body_parts: List[str] = Field(default_factory=list)  # 肩/腰/臀/大腿/小腿等
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

**数据库表结构:**
```sql
CREATE TABLE user_profiles (
    profile_id UUID PRIMARY KEY,
    user_id UUID UNIQUE NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    height INTEGER NOT NULL CHECK (height >= 100 AND height <= 250),
    body_type VARCHAR(20) NOT NULL,
    skin_tone VARCHAR(20) NOT NULL,
    style_preference JSONB NOT NULL,
    budget_range VARCHAR(20) NOT NULL,
    avoid_body_parts JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_profiles_user_id ON user_profiles(user_id);
```

### 颜色模型 (Color)

```python
class Color(BaseModel):
    name: str  # 标准色系名称
    rgb: Tuple[int, int, int] = Field(...)  # RGB 值
    hsv: Tuple[float, float, float] = Field(...)  # HSV 值
    hex_code: str = Field(...)  # 十六进制颜色码
```

### 服饰单品模型 (Garment)

```python
class Garment(BaseModel):
    garment_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    category: str = Field(...)  # 上衣/裤子/裙子/外套/鞋/包
    main_color: Color
    secondary_colors: List[Color] = Field(default_factory=list)
    style_tags: List[str] = Field(default_factory=list)  # 通勤/休闲/正式等
    fit_type: Optional[str] = None  # 修身/宽松/标准/oversized
    image_path: str
    image_url: str
    feature_vector: List[float] = Field(...)  # 1280 维特征向量
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

**数据库表结构:**
```sql
CREATE TABLE garments (
    garment_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    category VARCHAR(20) NOT NULL,
    main_color JSONB NOT NULL,
    secondary_colors JSONB DEFAULT '[]',
    style_tags JSONB DEFAULT '[]',
    fit_type VARCHAR(20),
    image_path VARCHAR(500) NOT NULL,
    image_url VARCHAR(500) NOT NULL,
    feature_vector FLOAT8[] NOT NULL,  -- PostgreSQL 数组类型
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_garments_user_id ON garments(user_id);
CREATE INDEX idx_garments_category ON garments(category);
CREATE INDEX idx_garments_user_category ON garments(user_id, category);

-- 使用 pgvector 扩展支持向量相似度搜索（可选优化）
-- CREATE EXTENSION IF NOT EXISTS vector;
-- ALTER TABLE garments ADD COLUMN feature_vector_pgvector vector(1280);
-- CREATE INDEX idx_garments_feature_vector ON garments USING ivfflat (feature_vector_pgvector vector_cosine_ops);
```

### 衣橱模型 (Wardrobe)

衣橱是一个逻辑概念，通过 user_id 关联的所有 Garment 构成用户的衣橱。不需要单独的数据库表。

```python
class Wardrobe:
    """衣橱管理类"""

    def __init__(self, user_id: str, db_session):
        self.user_id = user_id
        self.db = db_session

    def get_all_garments(self) -> List[Garment]:
        """获取所有服饰"""
        pass

    def filter_by_category(self, category: str) -> List[Garment]:
        """按品类筛选"""
        pass

    def filter_by_color(self, color_name: str) -> List[Garment]:
        """按颜色筛选"""
        pass

    def filter_by_style(self, style: str) -> List[Garment]:
        """按风格筛选"""
        pass
```

### 搭配方案模型 (OutfitCard)

```python
class OutfitItem(BaseModel):
    garment_id: str
    category: str
    image_url: str
    role: str  # target/top/bottom/outer/shoes/bag

class OutfitCard(BaseModel):
    outfit_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    items: List[OutfitItem] = Field(min_items=2)
    occasion: str  # 商务/正式/校园/休闲/约会/聚会
    description: str
    color_harmony: str  # 颜色搭配说明
    style_consistency: float = Field(ge=0, le=1)  # 风格一致性分数
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

搭配方案通常是临时生成的，不需要持久化存储。如果需要保存用户喜欢的搭配，可以添加收藏功能。

### 相似度匹配结果模型 (SimilarityMatch)

```python
class SimilarityMatch(BaseModel):
    garment_id: str
    similarity_score: float = Field(ge=0, le=1)
    similarity_level: str  # 高相似度/中度相似度/低相似度
    garment: Garment
```

### 适合度评分结果模型 (SuitabilityResult)

```python
class SuitabilityResult(BaseModel):
    suitability_score: int = Field(ge=0, le=100)  # 综合评分
    color_score: int = Field(ge=0, le=100)  # 颜色适合度
    fit_score: int = Field(ge=0, le=100)  # 版型适合度
    style_score: int = Field(ge=0, le=100)  # 风格适合度
    explanation: Dict[str, str]  # 各维度评分说明
    recommended_occasions: List[str]  # 推荐场合
    suggestions: List[str]  # 改进建议
```

### 图像识别结果模型 (RecognitionResult)

```python
class RecognitionResult(BaseModel):
    category: str
    category_confidence: float = Field(ge=0, le=1)
    main_color: Color
    secondary_colors: List[Color] = Field(default_factory=list)
    style_tags: List[str] = Field(default_factory=list)
    fit_type: Optional[str] = None
    feature_vector: List[float] = Field(...)  # 1280 维
```

### 图像识别结果模型 (RecognitionResult)

```python
class RecognitionResult(BaseModel):
    category: str
    category_confidence: float = Field(ge=0, le=1)
    main_color: Color
    secondary_colors: List[Color] = Field(default_factory=list)
    style_tags: List[str] = Field(default_factory=list)
    fit_type: Optional[str] = None
    feature_vector: List[float] = Field(...)  # 1280 维
```

## 核心算法设计

### 图像识别模块 (Image Recognition Module)

图像识别模块是系统的核心组件之一，负责从服饰图片中提取结构化信息，包括品类、颜色、风格和特征向量。

#### 技术选型

**模型选择: MobileNetV2**

选择 MobileNetV2 作为基础模型的原因：
- 轻量级架构：模型大小约 14MB，适合移动端和边缘计算
- 高效推理：单张图片推理时间 < 100ms（CPU）
- 良好的特征提取能力：倒数第二层输出 1280 维特征向量
- 预训练模型可用：ImageNet 预训练权重可直接使用或微调

**框架选择:**
- 训练阶段：TensorFlow 2.x / PyTorch
- 部署阶段：TensorFlow Lite（移动端）/ ONNX Runtime（服务端）

#### 模型架构

```
输入图片 (224x224x3)
    ↓
MobileNetV2 Backbone
    ↓
┌─────────────────────────────────────┐
│  特征提取层 (1280 维)                │
│  用于相似度计算                      │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  品类分类头 (6 类)                   │
│  Softmax 输出                        │
│  类别: 上衣/裤子/裙子/外套/鞋/包     │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  风格分类头 (多标签)                 │
│  Sigmoid 输出                        │
│  标签: 通勤/休闲/正式/运动/街头等    │
└─────────────────────────────────────┘
```

#### 图像预处理流程

```python
def preprocess_image(image_path: str) -> np.ndarray:
    """
    图像预处理流程

    Args:
        image_path: 图片路径

    Returns:
        np.ndarray: 预处理后的图像张量 (1, 224, 224, 3)
    """
    # 1. 读取图片
    image = Image.open(image_path).convert('RGB')

    # 2. 缩放到 224x224
    image = image.resize((224, 224), Image.BILINEAR)

    # 3. 转换为 numpy 数组
    image_array = np.array(image, dtype=np.float32)

    # 4. 归一化到 [-1, 1]（MobileNetV2 预处理）
    image_array = (image_array / 127.5) - 1.0

    # 5. 添加 batch 维度
    image_array = np.expand_dims(image_array, axis=0)

    return image_array
```

#### 品类识别 (Category Classification)

**品类定义:**
```python
GARMENT_CATEGORIES = {
    0: "上衣",      # T恤、衬衫、毛衣、卫衣等
    1: "裤子",      # 牛仔裤、休闲裤、西裤等
    2: "裙子",      # 连衣裙、半身裙等
    3: "外套",      # 夹克、大衣、风衣等
    4: "鞋",        # 运动鞋、皮鞋、靴子等
    5: "包"         # 手提包、双肩包、斜挎包等
}
```

**分类流程:**
```python
def classify_category(model, image: np.ndarray) -> Tuple[str, float]:
    """
    品类分类

    Args:
        model: 训练好的分类模型
        image: 预处理后的图像

    Returns:
        Tuple[str, float]: (品类名称, 置信度)
    """
    # 前向推理
    logits = model.predict(image)

    # Softmax 归一化
    probabilities = softmax(logits[0])

    # 获取最高概率的类别
    category_id = np.argmax(probabilities)
    confidence = probabilities[category_id]

    category_name = GARMENT_CATEGORIES[category_id]

    return category_name, float(confidence)
```

**置信度阈值处理:**
- 置信度 >= 0.8: 高置信度，直接使用
- 0.5 <= 置信度 < 0.8: 中等置信度，提示用户确认
- 置信度 < 0.5: 低置信度，要求用户手动选择品类

#### 颜色识别与聚类 (Color Recognition)

**颜色识别流程:**

```python
def extract_dominant_colors(
    image: Image,
    num_colors: int = 3
) -> List[Color]:
    """
    提取主色和辅助色

    Args:
        image: PIL Image 对象
        num_colors: 提取颜色数量

    Returns:
        List[Color]: 颜色列表（按占比排序）
    """
    # 1. 缩放图片以加速处理
    image = image.resize((150, 150))

    # 2. 转换为 numpy 数组
    pixels = np.array(image).reshape(-1, 3)

    # 3. 使用 K-Means 聚类
    kmeans = KMeans(n_clusters=num_colors, random_state=42)
    kmeans.fit(pixels)

    # 4. 获取聚类中心（主色）
    colors = kmeans.cluster_centers_.astype(int)

    # 5. 计算每个颜色的占比
    labels = kmeans.labels_
    counts = np.bincount(labels)
    percentages = counts / len(labels)

    # 6. 按占比排序
    sorted_indices = np.argsort(percentages)[::-1]

    # 7. 转换为 Color 对象
    color_objects = []
    for idx in sorted_indices:
        rgb = tuple(colors[idx])
        hsv = rgb_to_hsv(rgb)
        color_name = map_to_standard_color(rgb)
        hex_code = rgb_to_hex(rgb)

        color_objects.append(Color(
            name=color_name,
            rgb=rgb,
            hsv=hsv,
            hex_code=hex_code
        ))

    return color_objects
```

**标准色系映射:**

```python
STANDARD_COLORS = {
    "红色": {"h_range": (0, 15), "s_min": 50, "v_min": 50},
    "橙色": {"h_range": (16, 30), "s_min": 50, "v_min": 50},
    "黄色": {"h_range": (31, 60), "s_min": 50, "v_min": 50},
    "绿色": {"h_range": (61, 150), "s_min": 50, "v_min": 50},
    "蓝色": {"h_range": (151, 240), "s_min": 50, "v_min": 50},
    "紫色": {"h_range": (241, 300), "s_min": 50, "v_min": 50},
    "粉色": {"h_range": (301, 359), "s_min": 30, "v_min": 70},
    "黑色": {"s_max": 30, "v_max": 30},
    "白色": {"s_max": 30, "v_min": 70},
    "灰色": {"s_max": 30, "v_range": (31, 69)},
    "棕色": {"h_range": (16, 30), "s_min": 30, "v_max": 60}
}

def map_to_standard_color(rgb: Tuple[int, int, int]) -> str:
    """
    将 RGB 颜色映射到标准色系

    Args:
        rgb: RGB 值

    Returns:
        str: 标准色系名称
    """
    h, s, v = rgb_to_hsv(rgb)

    # 先判断无彩色（黑白灰）
    if s <= 30:
        if v <= 30:
            return "黑色"
        elif v >= 70:
            return "白色"
        else:
            return "灰色"

    # 判断有彩色
    for color_name, rules in STANDARD_COLORS.items():
        if "h_range" in rules:
            h_min, h_max = rules["h_range"]
            if h_min <= h <= h_max:
                if s >= rules.get("s_min", 0) and v >= rules.get("v_min", 0):
                    return color_name

    return "其他"

def rgb_to_hsv(rgb: Tuple[int, int, int]) -> Tuple[float, float, float]:
    """RGB 转 HSV"""
    r, g, b = [x / 255.0 for x in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return (h * 360, s * 100, v * 100)

def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    """RGB 转十六进制"""
    return "#{:02x}{:02x}{:02x}".format(*rgb)
```

#### 风格标签识别 (Style Tagging)

**风格定义:**
```python
STYLE_TAGS = [
    "通勤",      # 适合办公室穿着
    "休闲",      # 日常休闲风格
    "正式",      # 正式场合
    "运动",      # 运动风格
    "街头",      # 街头潮流
    "学院",      # 学院风
    "甜美",      # 甜美可爱
    "简约",      # 极简风格
    "复古",      # 复古风格
    "朋克",      # 朋克风格
    "民族",      # 民族风格
    "优雅"       # 优雅风格
]
```

**多标签分类:**
```python
def classify_style(model, image: np.ndarray, threshold: float = 0.3) -> List[str]:
    """
    风格多标签分类

    Args:
        model: 训练好的风格分类模型
        image: 预处理后的图像
        threshold: 置信度阈值

    Returns:
        List[str]: 风格标签列表
    """
    # 前向推理
    logits = model.predict_style(image)

    # Sigmoid 激活
    probabilities = sigmoid(logits[0])

    # 筛选超过阈值的标签
    style_tags = []
    for idx, prob in enumerate(probabilities):
        if prob >= threshold:
            style_tags.append(STYLE_TAGS[idx])

    # 如果没有标签超过阈值，选择概率最高的
    if not style_tags:
        max_idx = np.argmax(probabilities)
        style_tags.append(STYLE_TAGS[max_idx])

    return style_tags
```

#### 版型识别 (Fit Type Detection)

版型识别可以通过以下方式实现：

**方法 1: 基于规则的启发式方法**
```python
def detect_fit_type(image: Image, category: str) -> Optional[str]:
    """
    基于图像特征检测版型

    Args:
        image: PIL Image 对象
        category: 服饰品类

    Returns:
        Optional[str]: 版型类型（修身/宽松/标准/oversized）
    """
    if category not in ["上衣", "裤子", "外套"]:
        return None

    # 转换为灰度图
    gray = image.convert('L')

    # 边缘检测
    edges = cv2.Canny(np.array(gray), 50, 150)

    # 轮廓检测
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return "标准"

    # 获取最大轮廓
    max_contour = max(contours, key=cv2.contourArea)

    # 计算轮廓的宽高比
    x, y, w, h = cv2.boundingRect(max_contour)
    aspect_ratio = w / h if h > 0 else 1.0

    # 根据宽高比判断版型
    if category == "上衣":
        if aspect_ratio > 1.2:
            return "宽松"
        elif aspect_ratio < 0.8:
            return "修身"
        else:
            return "标准"
    elif category == "裤子":
        if aspect_ratio > 0.6:
            return "宽松"
        elif aspect_ratio < 0.4:
            return "修身"
        else:
            return "标准"

    return "标准"
```

**方法 2: 深度学习分类（可选）**
- 训练一个专门的版型分类器
- 输入：服饰图片
- 输出：修身/宽松/标准/oversized 四分类

#### 特征提取 (Feature Extraction)

特征向量用于相似度计算，是系统的核心功能之一。

```python
class FeatureExtractor:
    """特征提取器"""

    def __init__(self, model_path: str):
        """
        初始化特征提取器

        Args:
            model_path: MobileNetV2 模型路径
        """
        # 加载 MobileNetV2 模型
        base_model = tf.keras.applications.MobileNetV2(
            input_shape=(224, 224, 3),
            include_top=False,
            weights='imagenet',
            pooling='avg'  # 全局平均池化，输出 1280 维
        )

        self.model = base_model
        self.model.trainable = False  # 冻结权重

    def extract(self, image: np.ndarray) -> np.ndarray:
        """
        提取特征向量

        Args:
            image: 预处理后的图像 (1, 224, 224, 3)

        Returns:
            np.ndarray: 1280 维特征向量
        """
        # 前向推理
        features = self.model.predict(image, verbose=0)

        # L2 归一化
        features = features / np.linalg.norm(features, axis=1, keepdims=True)

        return features[0]  # 返回一维数组
```

**特征向量归一化:**
- 使用 L2 归一化确保特征向量的模长为 1
- 归一化后的余弦相似度等价于点积
- 加速相似度计算

#### 完整识别流程

```python
class ImageRecognizer:
    """图像识别器"""

    def __init__(
        self,
        category_model_path: str,
        style_model_path: str,
        feature_extractor: FeatureExtractor
    ):
        self.category_model = load_model(category_model_path)
        self.style_model = load_model(style_model_path)
        self.feature_extractor = feature_extractor

    def recognize(self, image_path: str) -> RecognitionResult:
        """
        完整的图像识别流程

        Args:
            image_path: 图片路径

        Returns:
            RecognitionResult: 识别结果
        """
        # 1. 读取图片
        image = Image.open(image_path).convert('RGB')

        # 2. 预处理
        processed_image = preprocess_image(image_path)

        # 3. 品类识别
        category, category_confidence = self.classify_category(processed_image)

        # 4. 颜色识别
        colors = extract_dominant_colors(image, num_colors=3)
        main_color = colors[0]
        secondary_colors = colors[1:] if len(colors) > 1 else []

        # 5. 风格识别
        style_tags = self.classify_style(processed_image)

        # 6. 版型识别
        fit_type = detect_fit_type(image, category)

        # 7. 特征提取
        feature_vector = self.feature_extractor.extract(processed_image)

        # 8. 构建结果
        result = RecognitionResult(
            category=category,
            category_confidence=category_confidence,
            main_color=main_color,
            secondary_colors=secondary_colors,
            style_tags=style_tags,
            fit_type=fit_type,
            feature_vector=feature_vector.tolist()
        )

        return result

    def classify_category(self, image: np.ndarray) -> Tuple[str, float]:
        """品类分类"""
        logits = self.category_model.predict(image, verbose=0)
        probabilities = softmax(logits[0])
        category_id = np.argmax(probabilities)
        confidence = probabilities[category_id]
        return GARMENT_CATEGORIES[category_id], float(confidence)

    def classify_style(self, image: np.ndarray, threshold: float = 0.3) -> List[str]:
        """风格分类"""
        logits = self.style_model.predict(image, verbose=0)
        probabilities = sigmoid(logits[0])

        style_tags = []
        for idx, prob in enumerate(probabilities):
            if prob >= threshold:
                style_tags.append(STYLE_TAGS[idx])

        if not style_tags:
            max_idx = np.argmax(probabilities)
            style_tags.append(STYLE_TAGS[max_idx])

        return style_tags
```

#### 性能优化

**1. 模型量化**
```python
# TensorFlow Lite 量化
converter = tf.lite.TFLiteConverter.from_keras_model(model)
converter.optimizations = [tf.lite.Optimize.DEFAULT]
tflite_model = converter.convert()

# 保存量化模型
with open('model_quantized.tflite', 'wb') as f:
    f.write(tflite_model)
```

**2. 批量推理**
```python
def batch_recognize(image_paths: List[str], batch_size: int = 8) -> List[RecognitionResult]:
    """批量识别"""
    results = []

    for i in range(0, len(image_paths), batch_size):
        batch_paths = image_paths[i:i+batch_size]
        batch_images = [preprocess_image(path) for path in batch_paths]
        batch_tensor = np.vstack(batch_images)

        # 批量推理
        batch_results = model.predict(batch_tensor)

        # 处理每个结果
        for j, path in enumerate(batch_paths):
            result = process_single_result(batch_results[j], path)
            results.append(result)

    return results
```

**3. 缓存机制**
```python
from functools import lru_cache
import hashlib

def get_image_hash(image_path: str) -> str:
    """计算图片哈希值"""
    with open(image_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

@lru_cache(maxsize=1000)
def cached_recognize(image_hash: str, image_path: str) -> RecognitionResult:
    """带缓存的识别"""
    return recognizer.recognize(image_path)
```

**4. 异步处理**
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

async def async_recognize(image_path: str) -> RecognitionResult:
    """异步识别"""
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        result = await loop.run_in_executor(
            executor,
            recognizer.recognize,
            image_path
        )
    return result
```

#### 模型训练数据集

**推荐数据集:**
1. **DeepFashion**: 大规模服饰数据集，包含品类、属性标注
2. **Fashion-MNIST**: 基础服饰分类数据集
3. **iMaterialist Fashion**: Kaggle 竞赛数据集，包含细粒度属性
4. **自建数据集**: 从电商平台爬取并标注

**数据增强策略:**
```python
from tensorflow.keras.preprocessing.image import ImageDataGenerator

datagen = ImageDataGenerator(
    rotation_range=20,           # 随机旋转
    width_shift_range=0.2,       # 水平平移
    height_shift_range=0.2,      # 垂直平移
    horizontal_flip=True,        # 水平翻转
    zoom_range=0.2,              # 随机缩放
    brightness_range=[0.8, 1.2], # 亮度调整
    fill_mode='nearest'
)
```

#### 错误处理

```python
class ImageRecognitionError(Exception):
    """图像识别错误基类"""
    pass

class InvalidImageError(ImageRecognitionError):
    """无效图片错误"""
    pass

class ModelInferenceError(ImageRecognitionError):
    """模型推理错误"""
    pass

def safe_recognize(image_path: str) -> Optional[RecognitionResult]:
    """安全的识别函数，包含错误处理"""
    try:
        # 验证图片格式
        if not image_path.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
            raise InvalidImageError(f"不支持的图片格式: {image_path}")

        # 验证图片是否可读
        try:
            image = Image.open(image_path)
            image.verify()
        except Exception as e:
            raise InvalidImageError(f"图片损坏或无法读取: {str(e)}")

        # 执行识别
        result = recognizer.recognize(image_path)

        return result

    except InvalidImageError as e:
        logger.error(f"Invalid image: {str(e)}")
        return None
    except ModelInferenceError as e:
        logger.error(f"Model inference failed: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return None
```


### 相似度分析模块 (Similarity Analyzer)

相似度分析模块负责计算服饰之间的相似度，帮助用户识别衣橱中的重复单品。

#### 余弦相似度算法

余弦相似度是衡量两个向量方向相似程度的指标，取值范围为 [-1, 1]，但在特征向量已归一化的情况下，取值范围为 [0, 1]。

**数学定义:**

```
cosine_similarity(A, B) = (A · B) / (||A|| × ||B||)
```

当向量已经 L2 归一化（||A|| = ||B|| = 1）时，简化为：

```
cosine_similarity(A, B) = A · B
```

**实现:**

```python
import numpy as np

def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """
    计算两个特征向量的余弦相似度

    Args:
        vec1: 特征向量 1（已归一化）
        vec2: 特征向量 2（已归一化）

    Returns:
        float: 相似度分数 [0, 1]
    """
    # 如果向量已归一化，直接计算点积
    similarity = np.dot(vec1, vec2)

    # 确保结果在 [0, 1] 范围内
    similarity = np.clip(similarity, 0.0, 1.0)

    return float(similarity)
```


#### 批量相似度计算

```python
def batch_cosine_similarity(
    target_vec: np.ndarray,
    wardrobe_vecs: np.ndarray
) -> np.ndarray:
    """
    批量计算目标向量与衣橱中所有向量的相似度

    Args:
        target_vec: 目标特征向量 (1280,)
        wardrobe_vecs: 衣橱特征向量矩阵 (N, 1280)

    Returns:
        np.ndarray: 相似度分数数组 (N,)
    """
    # 矩阵乘法：(N, 1280) × (1280,) = (N,)
    similarities = np.dot(wardrobe_vecs, target_vec)

    # 确保结果在 [0, 1] 范围内
    similarities = np.clip(similarities, 0.0, 1.0)

    return similarities
```

#### 相似度分级

根据相似度分数，将结果分为三个等级：

```python
class SimilarityLevel(Enum):
    HIGH = "高相似度"
    MEDIUM = "中度相似度"
    LOW = "低相似度"

def classify_similarity_level(score: float) -> SimilarityLevel:
    """
    根据相似度分数分级

    Args:
        score: 相似度分数 [0, 1]

    Returns:
        SimilarityLevel: 相似度等级
    """
    if score >= 0.8:
        return SimilarityLevel.HIGH
    elif score >= 0.5:
        return SimilarityLevel.MEDIUM
    else:
        return SimilarityLevel.LOW
```


#### SimilarityAnalyzer 完整实现

```python
class SimilarityAnalyzer:
    """相似度分析器"""

    def __init__(self, high_threshold: float = 0.8, medium_threshold: float = 0.5):
        """
        初始化相似度分析器

        Args:
            high_threshold: 高相似度阈值
            medium_threshold: 中度相似度阈值
        """
        self.high_threshold = high_threshold
        self.medium_threshold = medium_threshold

    def calculate_similarity(
        self,
        feature1: np.ndarray,
        feature2: np.ndarray
    ) -> float:
        """计算两个特征向量的余弦相似度"""
        return cosine_similarity(feature1, feature2)

    def find_similar_garments(
        self,
        target_feature: np.ndarray,
        wardrobe_garments: List[Garment],
        threshold: float = 0.5
    ) -> List[SimilarityMatch]:
        """
        在衣橱中查找相似服饰

        Args:
            target_feature: 目标服饰特征向量
            wardrobe_garments: 衣橱中的服饰列表
            threshold: 相似度阈值

        Returns:
            List[SimilarityMatch]: 相似度匹配结果列表（按相似度降序）
        """
        if not wardrobe_garments:
            return []

        # 提取所有特征向量
        wardrobe_features = np.array([
            g.feature_vector for g in wardrobe_garments
        ])

        # 批量计算相似度
        similarities = batch_cosine_similarity(target_feature, wardrobe_features)

        # 筛选并构建结果
        matches = []
        for idx, (garment, score) in enumerate(zip(wardrobe_garments, similarities)):
            if score >= threshold:
                level = classify_similarity_level(score)
                matches.append(SimilarityMatch(
                    garment_id=garment.garment_id,
                    similarity_score=float(score),
                    similarity_level=level.value,
                    garment=garment
                ))

        # 按相似度降序排序
        matches.sort(key=lambda x: x.similarity_score, reverse=True)

        return matches

    def has_duplicate_warning(self, matches: List[SimilarityMatch]) -> bool:
        """
        判断是否需要重复预警

        Args:
            matches: 相似度匹配结果列表

        Returns:
            bool: 是否存在高相似度服饰
        """
        return any(m.similarity_score >= self.high_threshold for m in matches)
```


### 搭配推荐模块 (Outfit Recommender)

搭配推荐模块基于品类搭配规则、颜色和谐度和风格一致性，生成个性化的搭配方案。

#### 品类搭配规则

定义不同品类之间的搭配关系：

```python
CATEGORY_MATCHING_RULES = {
    "上衣": {
        "required": ["裤子", "裙子"],  # 必须搭配下装
        "optional": ["鞋", "包", "外套"],  # 可选配件
        "combinations": [
            ["裤子", "鞋"],
            ["裙子", "鞋"],
            ["裤子", "鞋", "包"],
            ["裙子", "鞋", "包"]
        ]
    },
    "裤子": {
        "required": ["上衣"],
        "optional": ["鞋", "包", "外套"],
        "combinations": [
            ["上衣", "鞋"],
            ["上衣", "鞋", "包"],
            ["上衣", "外套", "鞋"]
        ]
    },
    "裙子": {
        "required": ["上衣"],
        "optional": ["鞋", "包", "外套"],
        "combinations": [
            ["上衣", "鞋"],
            ["上衣", "鞋", "包"],
            ["上衣", "外套", "鞋"]
        ]
    },
    "外套": {
        "required": ["上衣", "裤子", "裙子"],
        "optional": ["鞋", "包"],
        "combinations": [
            ["上衣", "裤子", "鞋"],
            ["上衣", "裙子", "鞋"],
            ["上衣", "裤子", "鞋", "包"]
        ]
    },
    "鞋": {
        "required": ["上衣", "裤子", "裙子"],
        "optional": ["包", "外套"],
        "combinations": [
            ["上衣", "裤子"],
            ["上衣", "裙子"],
            ["上衣", "裤子", "外套"]
        ]
    },
    "包": {
        "required": ["上衣", "裤子", "裙子"],
        "optional": ["鞋", "外套"],
        "combinations": [
            ["上衣", "裤子", "鞋"],
            ["上衣", "裙子", "鞋"]
        ]
    }
}
```


#### 颜色搭配规则

基于色彩理论定义颜色搭配规则：

```python
class ColorHarmonyType(Enum):
    MONOCHROMATIC = "同色系"  # 同一色相，不同明度/饱和度
    ANALOGOUS = "邻近色"      # 色环上相邻的颜色
    COMPLEMENTARY = "互补色"  # 色环上相对的颜色
    NEUTRAL = "中性色搭配"    # 黑白灰与其他颜色

# 色相环定义（HSV 中的 H 值）
COLOR_HUE_RANGES = {
    "红色": (0, 15),
    "橙色": (16, 30),
    "黄色": (31, 60),
    "绿色": (61, 150),
    "蓝色": (151, 240),
    "紫色": (241, 300),
    "粉色": (301, 359)
}

NEUTRAL_COLORS = ["黑色", "白色", "灰色"]

def calculate_color_harmony(color1: Color, color2: Color) -> Tuple[ColorHarmonyType, float]:
    """
    计算两个颜色的和谐度

    Args:
        color1: 颜色 1
        color2: 颜色 2

    Returns:
        Tuple[ColorHarmonyType, float]: (和谐类型, 和谐度分数 [0, 1])
    """
    # 中性色与任何颜色都和谐
    if color1.name in NEUTRAL_COLORS or color2.name in NEUTRAL_COLORS:
        return ColorHarmonyType.NEUTRAL, 0.9

    h1, s1, v1 = color1.hsv
    h2, s2, v2 = color2.hsv

    # 计算色相差
    hue_diff = abs(h1 - h2)
    if hue_diff > 180:
        hue_diff = 360 - hue_diff

    # 同色系：色相差 < 30 度
    if hue_diff < 30:
        return ColorHarmonyType.MONOCHROMATIC, 0.95

    # 邻近色：色相差 30-60 度
    if 30 <= hue_diff < 60:
        return ColorHarmonyType.ANALOGOUS, 0.85

    # 互补色：色相差 150-210 度
    if 150 <= hue_diff <= 210:
        return ColorHarmonyType.COMPLEMENTARY, 0.8

    # 其他情况：和谐度较低
    return ColorHarmonyType.ANALOGOUS, 0.6
```


#### 风格一致性评分

```python
def calculate_style_consistency(styles1: List[str], styles2: List[str]) -> float:
    """
    计算两个风格标签列表的一致性

    Args:
        styles1: 风格标签列表 1
        styles2: 风格标签列表 2

    Returns:
        float: 一致性分数 [0, 1]
    """
    if not styles1 or not styles2:
        return 0.5  # 缺少风格信息时返回中性分数

    # 计算交集
    common_styles = set(styles1) & set(styles2)

    # 计算并集
    all_styles = set(styles1) | set(styles2)

    # Jaccard 相似度
    consistency = len(common_styles) / len(all_styles) if all_styles else 0.0

    return consistency

def calculate_outfit_style_consistency(garments: List[Garment]) -> float:
    """
    计算整套搭配的风格一致性

    Args:
        garments: 搭配中的服饰列表

    Returns:
        float: 整体风格一致性分数 [0, 1]
    """
    if len(garments) < 2:
        return 1.0

    # 计算所有两两组合的一致性
    consistencies = []
    for i in range(len(garments)):
        for j in range(i + 1, len(garments)):
            consistency = calculate_style_consistency(
                garments[i].style_tags,
                garments[j].style_tags
            )
            consistencies.append(consistency)

    # 返回平均一致性
    return sum(consistencies) / len(consistencies) if consistencies else 0.0
```


#### OutfitRecommender 完整实现

```python
class OutfitRecommender:
    """搭配推荐器"""

    def __init__(self):
        self.category_rules = CATEGORY_MATCHING_RULES

    def recommend_outfits(
        self,
        target_garment: Garment,
        wardrobe: List[Garment],
        user_profile: UserProfile,
        num_outfits: int = 3
    ) -> List[OutfitCard]:
        """
        生成搭配推荐方案

        Args:
            target_garment: 目标服饰（待购买）
            wardrobe: 用户衣橱
            user_profile: 用户画像
            num_outfits: 推荐方案数量

        Returns:
            List[OutfitCard]: 搭配方案列表
        """
        # 获取品类搭配规则
        category = target_garment.category
        if category not in self.category_rules:
            return []

        rules = self.category_rules[category]
        combinations = rules["combinations"]

        # 生成候选搭配方案
        candidate_outfits = []
        for combination in combinations:
            outfits = self._generate_outfits_for_combination(
                target_garment,
                combination,
                wardrobe
            )
            candidate_outfits.extend(outfits)

        # 评分和排序
        scored_outfits = []
        for outfit_items in candidate_outfits:
            score = self._score_outfit(outfit_items, user_profile)
            scored_outfits.append((score, outfit_items))

        scored_outfits.sort(key=lambda x: x[0], reverse=True)

        # 构建 OutfitCard
        outfit_cards = []
        for score, items in scored_outfits[:num_outfits]:
            card = self._build_outfit_card(items, target_garment)
            outfit_cards.append(card)

        return outfit_cards
```


    def _generate_outfits_for_combination(
        self,
        target_garment: Garment,
        combination: List[str],
        wardrobe: List[Garment]
    ) -> List[List[Garment]]:
        """
        为指定品类组合生成搭配方案

        Args:
            target_garment: 目标服饰
            combination: 品类组合列表
            wardrobe: 衣橱

        Returns:
            List[List[Garment]]: 搭配方案列表
        """
        # 按品类分组衣橱服饰
        category_groups = {}
        for garment in wardrobe:
            if garment.category not in category_groups:
                category_groups[garment.category] = []
            category_groups[garment.category].append(garment)

        # 为每个品类选择候选服饰（最多 5 个）
        category_candidates = {}
        for category in combination:
            if category in category_groups:
                # 按风格一致性排序
                candidates = category_groups[category][:5]
                category_candidates[category] = candidates
            else:
                # 缺少必需品类，无法生成搭配
                return []

        # 生成笛卡尔积（所有可能的组合）
        import itertools
        all_combinations = list(itertools.product(*category_candidates.values()))

        # 限制组合数量
        max_combinations = 20
        if len(all_combinations) > max_combinations:
            all_combinations = all_combinations[:max_combinations]

        # 构建搭配方案（包含目标服饰）
        outfits = []
        for combo in all_combinations:
            outfit = [target_garment] + list(combo)
            outfits.append(outfit)

        return outfits
```


    def _score_outfit(
        self,
        outfit_items: List[Garment],
        user_profile: UserProfile
    ) -> float:
        """
        评分搭配方案

        Args:
            outfit_items: 搭配中的服饰列表
            user_profile: 用户画像

        Returns:
            float: 搭配评分 [0, 1]
        """
        # 计算颜色和谐度
        color_scores = []
        for i in range(len(outfit_items)):
            for j in range(i + 1, len(outfit_items)):
                _, harmony_score = calculate_color_harmony(
                    outfit_items[i].main_color,
                    outfit_items[j].main_color
                )
                color_scores.append(harmony_score)

        avg_color_score = sum(color_scores) / len(color_scores) if color_scores else 0.5

        # 计算风格一致性
        style_consistency = calculate_outfit_style_consistency(outfit_items)

        # 综合评分（颜色 60%，风格 40%）
        total_score = 0.6 * avg_color_score + 0.4 * style_consistency

        return total_score

    def _build_outfit_card(
        self,
        outfit_items: List[Garment],
        target_garment: Garment
    ) -> OutfitCard:
        """
        构建搭配卡片

        Args:
            outfit_items: 搭配中的服饰列表
            target_garment: 目标服饰

        Returns:
            OutfitCard: 搭配卡片
        """
        # 构建 OutfitItem 列表
        items = []
        for garment in outfit_items:
            role = "target" if garment.garment_id == target_garment.garment_id else garment.category.lower()
            items.append(OutfitItem(
                garment_id=garment.garment_id,
                category=garment.category,
                image_url=garment.image_url,
                role=role
            ))

        # 生成颜色和谐说明
        color_harmony_desc = self._generate_color_harmony_description(outfit_items)

        # 计算风格一致性
        style_consistency = calculate_outfit_style_consistency(outfit_items)

        # 推荐场合
        occasion = self._recommend_occasion(outfit_items)

        # 生成搭配说明
        description = self._generate_outfit_description(outfit_items, occasion)

        return OutfitCard(
            items=items,
            occasion=occasion,
            description=description,
            color_harmony=color_harmony_desc,
            style_consistency=style_consistency
        )
```


    def _generate_color_harmony_description(self, outfit_items: List[Garment]) -> str:
        """生成颜色和谐说明"""
        if len(outfit_items) < 2:
            return "单品搭配"

        # 获取主要颜色
        colors = [item.main_color.name for item in outfit_items]

        # 判断和谐类型
        harmony_type, _ = calculate_color_harmony(
            outfit_items[0].main_color,
            outfit_items[1].main_color
        )

        if harmony_type == ColorHarmonyType.MONOCHROMATIC:
            return f"{colors[0]}系同色搭配"
        elif harmony_type == ColorHarmonyType.ANALOGOUS:
            return f"{colors[0]}与{colors[1]}邻近色搭配"
        elif harmony_type == ColorHarmonyType.COMPLEMENTARY:
            return f"{colors[0]}与{colors[1]}互补色搭配"
        elif harmony_type == ColorHarmonyType.NEUTRAL:
            return "经典中性色搭配"
        else:
            return "多色混搭"

    def _recommend_occasion(self, outfit_items: List[Garment]) -> str:
        """推荐穿着场合"""
        # 统计风格标签
        style_counts = {}
        for item in outfit_items:
            for style in item.style_tags:
                style_counts[style] = style_counts.get(style, 0) + 1

        # 找出最常见的风格
        if not style_counts:
            return "休闲"

        dominant_style = max(style_counts, key=style_counts.get)

        # 风格到场合的映射
        style_to_occasion = {
            "通勤": "商务",
            "正式": "正式",
            "学院": "校园",
            "休闲": "休闲",
            "甜美": "约会",
            "街头": "聚会",
            "运动": "运动",
            "简约": "日常",
            "复古": "聚会",
            "优雅": "正式"
        }

        return style_to_occasion.get(dominant_style, "休闲")

    def _generate_outfit_description(
        self,
        outfit_items: List[Garment],
        occasion: str
    ) -> str:
        """生成搭配说明"""
        # 提取品类和颜色
        categories = [item.category for item in outfit_items]
        colors = [item.main_color.name for item in outfit_items]

        # 构建描述
        desc_parts = []
        for category, color in zip(categories, colors):
            desc_parts.append(f"{color}{category}")

        description = "搭配".join(desc_parts) + f"，适合{occasion}场合"

        return description
```


### 适合度评分模块 (Suitability Scorer)

适合度评分模块基于用户画像，从颜色、版型、风格三个维度评估服饰的适合度。

#### 颜色适合度评分

基于肤色与服饰颜色的匹配规则：

```python
# 肤色与颜色匹配规则
SKIN_TONE_COLOR_RULES = {
    "冷白": {
        "高分": ["蓝色", "紫色", "粉色", "灰色", "黑色"],
        "中分": ["绿色", "白色", "红色"],
        "低分": ["橙色", "黄色", "棕色"]
    },
    "黄皮": {
        "高分": ["蓝色", "绿色", "白色", "灰色"],
        "中分": ["紫色", "粉色", "黑色"],
        "低分": ["黄色", "橙色", "棕色"]
    },
    "小麦": {
        "高分": ["白色", "蓝色", "绿色", "红色"],
        "中分": ["黑色", "灰色", "紫色"],
        "低分": ["黄色", "棕色"]
    },
    "深色": {
        "高分": ["白色", "红色", "蓝色", "黄色"],
        "中分": ["绿色", "紫色", "粉色"],
        "低分": ["黑色", "棕色", "灰色"]
    }
}

def calculate_color_suitability(
    garment_color: Color,
    skin_tone: str
) -> Tuple[int, str]:
    """
    计算颜色适合度

    Args:
        garment_color: 服饰颜色
        skin_tone: 肤色类型

    Returns:
        Tuple[int, str]: (评分 0-100, 说明文字)
    """
    if skin_tone not in SKIN_TONE_COLOR_RULES:
        return 70, "无法判断颜色适合度"

    rules = SKIN_TONE_COLOR_RULES[skin_tone]
    color_name = garment_color.name

    if color_name in rules["高分"]:
        score = 90
        explanation = f"{color_name}与您的{skin_tone}肤色搭配度很高，能提亮肤色"
    elif color_name in rules["中分"]:
        score = 70
        explanation = f"{color_name}与您的{skin_tone}肤色搭配度适中"
    elif color_name in rules["低分"]:
        score = 50
        explanation = f"{color_name}可能不太适合{skin_tone}肤色，建议选择其他颜色"
    else:
        score = 70
        explanation = f"{color_name}与您的{skin_tone}肤色搭配度适中"

    return score, explanation
```


#### 版型适合度评分

基于体型与版型的匹配规则，并考虑用户不希望强化的身体部位：

```python
# 体型与版型匹配规则
BODY_TYPE_FIT_RULES = {
    "偏瘦": {
        "修身": 85,
        "标准": 75,
        "宽松": 60,
        "oversized": 50
    },
    "微胖": {
        "修身": 50,
        "标准": 75,
        "宽松": 85,
        "oversized": 80
    },
    "梨形": {
        "修身": 60,
        "标准": 75,
        "宽松": 85,
        "oversized": 80
    },
    "倒三角": {
        "修身": 65,
        "标准": 80,
        "宽松": 75,
        "oversized": 70
    },
    "沙漏": {
        "修身": 90,
        "标准": 80,
        "宽松": 70,
        "oversized": 60
    },
    "矩形": {
        "修身": 70,
        "标准": 80,
        "宽松": 75,
        "oversized": 70
    }
}

# 版型对身体部位的影响
FIT_BODY_PART_IMPACT = {
    "修身": ["肩", "腰", "臀", "大腿"],
    "标准": ["肩", "腰"],
    "宽松": [],
    "oversized": []
}

def calculate_fit_suitability(
    garment_fit: Optional[str],
    body_type: str,
    avoid_parts: List[str]
) -> Tuple[int, str]:
    """
    计算版型适合度

    Args:
        garment_fit: 服饰版型
        body_type: 体型类型
        avoid_parts: 不希望强化的身体部位

    Returns:
        Tuple[int, str]: (评分 0-100, 说明文字)
    """
    if not garment_fit or body_type not in BODY_TYPE_FIT_RULES:
        return 70, "无法判断版型适合度"

    # 基础评分
    base_score = BODY_TYPE_FIT_RULES[body_type].get(garment_fit, 70)

    # 检查是否会强化不希望强化的部位
    impacted_parts = FIT_BODY_PART_IMPACT.get(garment_fit, [])
    conflicting_parts = set(impacted_parts) & set(avoid_parts)

    # 每个冲突部位扣 15 分
    penalty = len(conflicting_parts) * 15
    final_score = max(base_score - penalty, 30)

    # 生成说明
    if conflicting_parts:
        parts_str = "、".join(conflicting_parts)
        explanation = f"{garment_fit}版型可能会强化{parts_str}线条，建议选择宽松或落肩款式"
    else:
        explanation = f"{garment_fit}版型与您的{body_type}体型搭配度较好"

    return final_score, explanation
```


#### 风格适合度评分

基于用户风格偏好与服饰风格的匹配度：

```python
def calculate_style_suitability(
    garment_styles: List[str],
    style_preference: List[str]
) -> Tuple[int, str]:
    """
    计算风格适合度

    Args:
        garment_styles: 服饰风格标签
        style_preference: 用户风格偏好

    Returns:
        Tuple[int, str]: (评分 0-100, 说明文字)
    """
    if not garment_styles or not style_preference:
        return 70, "无法判断风格适合度"

    # 计算交集
    common_styles = set(garment_styles) & set(style_preference)

    # 计算匹配度
    match_ratio = len(common_styles) / len(style_preference)

    # 转换为评分
    score = int(50 + match_ratio * 50)  # 50-100 分

    # 生成说明
    if match_ratio >= 0.5:
        styles_str = "、".join(common_styles)
        explanation = f"服饰风格（{styles_str}）与您的偏好高度匹配"
    elif match_ratio > 0:
        styles_str = "、".join(common_styles)
        explanation = f"服饰风格（{styles_str}）与您的偏好部分匹配"
    else:
        garment_styles_str = "、".join(garment_styles)
        preference_str = "、".join(style_preference)
        explanation = f"服饰风格（{garment_styles_str}）与您的偏好（{preference_str}）有一定差异"

    return score, explanation
```


#### SuitabilityScorer 完整实现

```python
class SuitabilityScorer:
    """适合度评分器"""

    def __init__(
        self,
        color_weight: float = 0.4,
        fit_weight: float = 0.3,
        style_weight: float = 0.3
    ):
        """
        初始化评分器

        Args:
            color_weight: 颜色权重
            fit_weight: 版型权重
            style_weight: 风格权重
        """
        self.color_weight = color_weight
        self.fit_weight = fit_weight
        self.style_weight = style_weight

    def calculate_score(
        self,
        garment: Garment,
        user_profile: UserProfile
    ) -> SuitabilityResult:
        """
        计算服饰适合度评分

        Args:
            garment: 服饰单品
            user_profile: 用户画像

        Returns:
            SuitabilityResult: 适合度评分结果
        """
        # 计算各维度评分
        color_score, color_explanation = calculate_color_suitability(
            garment.main_color,
            user_profile.skin_tone
        )

        fit_score, fit_explanation = calculate_fit_suitability(
            garment.fit_type,
            user_profile.body_type,
            user_profile.avoid_body_parts
        )

        style_score, style_explanation = calculate_style_suitability(
            garment.style_tags,
            user_profile.style_preference
        )

        # 计算综合评分（加权平均）
        suitability_score = int(
            self.color_weight * color_score +
            self.fit_weight * fit_score +
            self.style_weight * style_score
        )

        # 推荐场合
        recommended_occasions = self._recommend_occasions(
            garment,
            suitability_score
        )

        # 生成改进建议
        suggestions = self._generate_suggestions(
            suitability_score,
            color_score,
            fit_score,
            style_score,
            garment,
            user_profile
        )

        return SuitabilityResult(
            suitability_score=suitability_score,
            color_score=color_score,
            fit_score=fit_score,
            style_score=style_score,
            explanation={
                "color": color_explanation,
                "fit": fit_explanation,
                "style": style_explanation
            },
            recommended_occasions=recommended_occasions,
            suggestions=suggestions
        )
```


    def _recommend_occasions(
        self,
        garment: Garment,
        suitability_score: int
    ) -> List[str]:
        """
        推荐适合的穿着场合

        Args:
            garment: 服饰单品
            suitability_score: 综合适合度评分

        Returns:
            List[str]: 推荐场合列表
        """
        # 基于风格标签推荐场合
        style_to_occasions = {
            "通勤": ["商务", "日常"],
            "正式": ["正式", "商务"],
            "学院": ["校园", "日常"],
            "休闲": ["休闲", "日常"],
            "甜美": ["约会", "聚会"],
            "街头": ["聚会", "休闲"],
            "运动": ["运动", "休闲"],
            "简约": ["日常", "商务"],
            "复古": ["聚会", "约会"],
            "优雅": ["正式", "约会"]
        }

        occasions = set()
        for style in garment.style_tags:
            if style in style_to_occasions:
                occasions.update(style_to_occasions[style])

        # 如果适合度低，减少推荐场合
        if suitability_score < 60:
            occasions = list(occasions)[:2]

        return list(occasions) if occasions else ["休闲"]

    def _generate_suggestions(
        self,
        suitability_score: int,
        color_score: int,
        fit_score: int,
        style_score: int,
        garment: Garment,
        user_profile: UserProfile
    ) -> List[str]:
        """
        生成改进建议

        Args:
            suitability_score: 综合评分
            color_score: 颜色评分
            fit_score: 版型评分
            style_score: 风格评分
            garment: 服饰单品
            user_profile: 用户画像

        Returns:
            List[str]: 建议列表
        """
        suggestions = []

        # 综合评分低于 60 分时提供建议
        if suitability_score < 60:
            # 颜色建议
            if color_score < 70:
                high_score_colors = SKIN_TONE_COLOR_RULES[user_profile.skin_tone]["高分"]
                suggestions.append(f"建议选择{'/'.join(high_score_colors[:3])}等更适合您肤色的颜色")

            # 版型建议
            if fit_score < 70:
                if user_profile.avoid_body_parts:
                    parts_str = "、".join(user_profile.avoid_body_parts)
                    suggestions.append(f"建议选择宽松或落肩款式以避免强化{parts_str}")
                else:
                    suggestions.append("建议选择更适合您体型的版型")

            # 风格建议
            if style_score < 70:
                preference_str = "、".join(user_profile.style_preference[:2])
                suggestions.append(f"建议选择{preference_str}风格的服饰以匹配您的偏好")

        return suggestions
```


## 正确性属性 (Correctness Properties)

*属性是一个特征或行为，应该在系统的所有有效执行中保持为真——本质上是关于系统应该做什么的正式陈述。属性作为人类可读规范和机器可验证正确性保证之间的桥梁。*

以下属性基于需求文档中的验收标准，用于指导属性测试（Property-Based Testing）的实现。每个属性都使用"对于任意"（For any）的通用量化形式，确保在所有有效输入下系统行为的正确性。

### 属性 1: 用户注册往返

*对于任意*有效的注册信息（用户名、密码、邮箱），注册后应能在数据库中查询到对应的用户记录，且密码已加密存储（不是明文）。

**验证需求: 1.1, 1.5**

### 属性 2: 重复注册拒绝

*对于任意*已存在的用户，使用相同的用户名或邮箱再次注册应被系统拒绝，并返回错误提示。

**验证需求: 1.2**

### 属性 3: 登录认证往返

*对于任意*已注册用户，使用正确的凭证登录应返回有效的 JWT Token，使用该 Token 应能访问受保护的资源。

**验证需求: 1.3**

### 属性 4: 无效登录拒绝

*对于任意*无效的登录凭证（错误密码或不存在的用户名），系统应拒绝登录并返回认证失败提示。

**验证需求: 1.4**

### 属性 5: 用户画像数据往返

*对于任意*有效的用户画像数据（身高、体型、肤色、风格偏好、预算范围、避免部位），创建画像后重新查询应返回相同的数据。

**验证需求: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.9**

### 属性 6: 用户画像更新往返

*对于任意*已存在的用户画像，更新任意字段后重新查询应返回更新后的数据。

**验证需求: 2.8**


### 属性 7: 图片格式支持

*对于任意* JPEG、PNG 或 WebP 格式的有效图片文件，系统应能成功导入并进行识别处理。

**验证需求: 3.9**

### 属性 8: 品类识别正确性

*对于任意*服饰图片，图像识别器应返回 6 种品类之一（上衣/裤子/裙子/外套/鞋/包），且置信度在 [0, 1] 范围内。

**验证需求: 3.4**

### 属性 9: 颜色识别正确性

*对于任意*服饰图片，图像识别器应返回主色信息，包含有效的 RGB 和 HSV 值，且主色名称应映射到标准色系。

**验证需求: 3.5**

### 属性 10: 风格识别正确性

*对于任意*服饰图片，图像识别器应返回至少一个风格标签，且所有标签都应在预定义的风格列表中。

**验证需求: 3.6**

### 属性 11: 特征向量维度正确性

*对于任意*服饰图片，特征提取器应返回 1280 维的特征向量，且向量已 L2 归一化（模长为 1）。

**验证需求: 3.7**

### 属性 12: 衣橱添加往返

*对于任意*服饰信息，添加到衣橱后查询应能找到该服饰，且所有字段（包括特征向量）应与添加时一致。

**验证需求: 4.1, 4.2**

### 属性 13: 衣橱查询完整性

*对于任意*用户，添加 N 个服饰后查询衣橱应返回 N 个服饰。

**验证需求: 4.3**

### 属性 14: 衣橱删除正确性

*对于任意*衣橱中的服饰，删除后查询该服饰应返回不存在。

**验证需求: 4.4**

### 属性 15: 衣橱更新往返

*对于任意*衣橱中的服饰，更新元数据后重新查询应返回更新后的数据。

**验证需求: 4.5**


### 属性 16: 衣橱筛选正确性

*对于任意*筛选条件（品类、颜色或风格），筛选结果中的所有服饰都应满足该筛选条件。

**验证需求: 4.6, 4.7, 4.8**

### 属性 17: 余弦相似度数学正确性

*对于任意*两个已归一化的特征向量，计算的余弦相似度应等于两向量的点积，且结果在 [0, 1] 范围内。

**验证需求: 5.2**

### 属性 18: 相似度计算完整性

*对于任意*目标服饰和衣橱，相似度分析应计算目标服饰与衣橱中所有服饰的相似度。

**验证需求: 5.1**

### 属性 19: 相似度分级正确性

*对于任意*相似度分数，分级应遵循规则：>= 0.8 为高相似度，[0.5, 0.8) 为中度相似度，< 0.5 为低相似度。

**验证需求: 5.3, 5.4, 5.5**

### 属性 20: 重复预警触发

*对于任意*相似度分析结果，当存在相似度 >= 0.8 的服饰时，系统应显示重复预警。

**验证需求: 5.6**

### 属性 21: 搭配推荐数量

*对于任意*目标服饰和非空衣橱，搭配推荐应生成至少 3 套搭配方案（如果衣橱中有足够的服饰）。

**验证需求: 6.7**

### 属性 22: 品类搭配规则正确性

*对于任意*目标服饰品类，推荐的搭配方案中应包含符合品类搭配规则的服饰组合（例如上衣应搭配下装和鞋）。

**验证需求: 6.2, 6.3, 6.4**

### 属性 23: 颜色搭配规则应用

*对于任意*搭配方案，方案中的颜色组合应符合颜色搭配规则（同色系/邻近色/互补色/中性色搭配）。

**验证需求: 6.5**


### 属性 24: 风格一致性应用

*对于任意*搭配方案，方案中的服饰应具有一定的风格一致性（风格标签有交集或一致性分数 > 0）。

**验证需求: 6.6**

### 属性 25: OutfitCard 数据完整性

*对于任意*搭配推荐结果，每个 OutfitCard 应包含服饰列表、推荐场合和搭配说明。

**验证需求: 6.8, 6.9**

### 属性 26: 颜色适合度评分范围

*对于任意*服饰颜色和用户肤色组合，颜色适合度评分应在 [0, 100] 范围内。

**验证需求: 7.2**

### 属性 27: 版型适合度评分范围

*对于任意*服饰版型和用户体型组合，版型适合度评分应在 [0, 100] 范围内。

**验证需求: 7.3**

### 属性 28: 风格适合度评分范围

*对于任意*服饰风格和用户风格偏好组合，风格适合度评分应在 [0, 100] 范围内。

**验证需求: 7.4**

### 属性 29: 综合适合度评分计算

*对于任意*服饰和用户画像，综合适合度评分应等于颜色、版型、风格评分的加权平均，且在 [0, 100] 范围内。

**验证需求: 7.5**

### 属性 30: 评分说明完整性

*对于任意*适合度评分结果，应包含颜色、版型、风格三个维度的文字说明。

**验证需求: 7.6**

### 属性 31: 场合推荐非空

*对于任意*适合度评分结果，推荐场合列表应非空且包含有效的场合类型。

**验证需求: 7.7**

### 属性 32: 避免部位考虑

*对于任意*用户画像中指定的避免部位，当服饰版型会强化这些部位时，版型适合度评分应降低。

**验证需求: 7.9**


## 错误处理 (Error Handling)

系统采用分层错误处理策略，确保所有错误都能被正确捕获、记录和返回给客户端。

### 错误分类

#### 1. 客户端错误 (4xx)

**400 Bad Request - 请求参数无效**
- 场景：用户输入验证失败、图片格式不支持、必填字段缺失
- 响应示例：
```json
{
  "error": "ValidationError",
  "message": "Invalid request parameters",
  "details": {
    "field": "height",
    "issue": "Height must be between 100 and 250 cm"
  }
}
```

**401 Unauthorized - 未授权**
- 场景：Token 缺失、Token 无效、Token 过期
- 响应示例：
```json
{
  "error": "AuthenticationError",
  "message": "Invalid or expired token",
  "details": null
}
```

**403 Forbidden - 禁止访问**
- 场景：用户尝试访问其他用户的资源
- 响应示例：
```json
{
  "error": "AuthorizationError",
  "message": "You don't have permission to access this resource",
  "details": null
}
```

**404 Not Found - 资源不存在**
- 场景：请求的服饰、用户画像不存在
- 响应示例：
```json
{
  "error": "NotFoundError",
  "message": "Garment not found",
  "details": {
    "garment_id": "abc123"
  }
}
```

**409 Conflict - 资源冲突**
- 场景：用户名或邮箱已存在
- 响应示例：
```json
{
  "error": "ConflictError",
  "message": "Username already exists",
  "details": {
    "username": "john_doe"
  }
}
```


#### 2. 服务器错误 (5xx)

**500 Internal Server Error - 服务器内部错误**
- 场景：未预期的异常、数据库连接失败、模型推理失败
- 响应示例：
```json
{
  "error": "InternalServerError",
  "message": "An unexpected error occurred",
  "details": null
}
```

**503 Service Unavailable - 服务不可用**
- 场景：数据库维护、模型加载失败
- 响应示例：
```json
{
  "error": "ServiceUnavailableError",
  "message": "Service temporarily unavailable",
  "details": {
    "retry_after": 60
  }
}
```

### 自定义异常类

```python
class SmartOutfitError(Exception):
    """基础异常类"""
    def __init__(self, message: str, details: Optional[Dict] = None):
        self.message = message
        self.details = details
        super().__init__(self.message)

class ValidationError(SmartOutfitError):
    """验证错误"""
    pass

class AuthenticationError(SmartOutfitError):
    """认证错误"""
    pass

class AuthorizationError(SmartOutfitError):
    """授权错误"""
    pass

class NotFoundError(SmartOutfitError):
    """资源不存在错误"""
    pass

class ConflictError(SmartOutfitError):
    """资源冲突错误"""
    pass

class ImageProcessingError(SmartOutfitError):
    """图像处理错误"""
    pass

class ModelInferenceError(SmartOutfitError):
    """模型推理错误"""
    pass
```


### 全局异常处理器

```python
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)

def setup_exception_handlers(app: FastAPI):
    """配置全局异常处理器"""

    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError):
        logger.warning(f"Validation error: {exc.message}", extra={"details": exc.details})
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "ValidationError",
                "message": exc.message,
                "details": exc.details
            }
        )

    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(request: Request, exc: AuthenticationError):
        logger.warning(f"Authentication error: {exc.message}")
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "error": "AuthenticationError",
                "message": exc.message,
                "details": exc.details
            }
        )

    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(request: Request, exc: AuthorizationError):
        logger.warning(f"Authorization error: {exc.message}")
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": "AuthorizationError",
                "message": exc.message,
                "details": exc.details
            }
        )

    @app.exception_handler(NotFoundError)
    async def not_found_error_handler(request: Request, exc: NotFoundError):
        logger.info(f"Resource not found: {exc.message}")
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": "NotFoundError",
                "message": exc.message,
                "details": exc.details
            }
        )

    @app.exception_handler(ConflictError)
    async def conflict_error_handler(request: Request, exc: ConflictError):
        logger.warning(f"Resource conflict: {exc.message}")
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": "ConflictError",
                "message": exc.message,
                "details": exc.details
            }
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unexpected error: {str(exc)}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "InternalServerError",
                "message": "An unexpected error occurred",
                "details": None
            }
        )
```


### 错误日志记录

```python
import logging
from logging.handlers import RotatingFileHandler
import sys

def setup_logging():
    """配置日志系统"""

    # 创建 logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)

    # 文件处理器（自动轮转）
    file_handler = RotatingFileHandler(
        'logs/app.log',
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5
    )
    file_handler.setLevel(logging.WARNING)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(message)s'
    )
    file_handler.setFormatter(file_formatter)

    # 添加处理器
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger
```

### 错误处理最佳实践

1. **输入验证**：在业务逻辑执行前验证所有输入参数
2. **资源检查**：访问资源前检查资源是否存在和用户是否有权限
3. **事务管理**：数据库操作使用事务，确保原子性
4. **优雅降级**：当非关键服务失败时，返回部分结果而不是完全失败
5. **错误传播**：底层错误应被捕获并转换为有意义的业务错误
6. **敏感信息保护**：错误响应中不应包含敏感信息（如数据库连接字符串、内部路径）
7. **错误监控**：集成错误监控服务（如 Sentry）以实时追踪生产环境错误


## 测试策略 (Testing Strategy)

系统采用双重测试方法：单元测试验证具体示例和边缘情况，属性测试验证通用属性在所有输入下的正确性。两者互补，共同确保系统的全面覆盖和正确性。

### 测试方法论

#### 单元测试 (Unit Tests)

单元测试专注于：
- **具体示例**：验证特定输入的预期输出
- **边缘情况**：测试边界条件、空值、极端值
- **错误条件**：验证错误处理逻辑
- **集成点**：测试组件之间的交互

**测试框架**：pytest

**示例：用户注册单元测试**
```python
import pytest
from app.services.auth import AuthService
from app.exceptions import ConflictError

def test_register_valid_user():
    """测试有效用户注册"""
    auth_service = AuthService()
    user = auth_service.register(
        username="john_doe",
        email="john@example.com",
        password="SecurePass123"
    )
    assert user.username == "john_doe"
    assert user.email == "john@example.com"
    assert user.password_hash != "SecurePass123"  # 密码已加密

def test_register_duplicate_username():
    """测试重复用户名注册"""
    auth_service = AuthService()
    auth_service.register("john_doe", "john@example.com", "pass123")

    with pytest.raises(ConflictError) as exc_info:
        auth_service.register("john_doe", "jane@example.com", "pass456")

    assert "username already exists" in str(exc_info.value).lower()

def test_register_invalid_email():
    """测试无效邮箱格式"""
    auth_service = AuthService()

    with pytest.raises(ValidationError):
        auth_service.register("john_doe", "invalid-email", "pass123")
```


#### 属性测试 (Property-Based Tests)

属性测试通过生成大量随机输入，验证系统在所有情况下都满足通用属性。

**测试框架**：Hypothesis (Python)

**配置要求**：
- 每个属性测试至少运行 100 次迭代
- 每个测试必须引用设计文档中的属性编号
- 使用注释标记：`# Feature: smart-outfit-assistant, Property X: [property text]`

**示例：用户注册往返属性测试**
```python
from hypothesis import given, strategies as st
from app.services.auth import AuthService
from app.database import get_db_session

# Feature: smart-outfit-assistant, Property 1: 用户注册往返
@given(
    username=st.text(min_size=3, max_size=50, alphabet=st.characters(blacklist_categories=('Cs',))),
    email=st.emails(),
    password=st.text(min_size=8, max_size=100)
)
def test_user_registration_roundtrip(username, password, email):
    """
    对于任意有效的注册信息，注册后应能在数据库中查询到对应的用户记录，
    且密码已加密存储（不是明文）
    """
    auth_service = AuthService()
    db = get_db_session()

    try:
        # 注册用户
        user = auth_service.register(username, email, password)

        # 从数据库查询
        db_user = db.query(User).filter(User.user_id == user.user_id).first()

        # 验证数据一致性
        assert db_user is not None
        assert db_user.username == username
        assert db_user.email == email

        # 验证密码已加密
        assert db_user.password_hash != password
        assert len(db_user.password_hash) > 50  # bcrypt hash 长度

    finally:
        # 清理测试数据
        db.rollback()
```


**示例：余弦相似度数学正确性属性测试**
```python
from hypothesis import given, strategies as st
import numpy as np
from app.services.similarity import cosine_similarity

# Feature: smart-outfit-assistant, Property 17: 余弦相似度数学正确性
@given(
    vec1=st.lists(st.floats(min_value=-1, max_value=1), min_size=1280, max_size=1280),
    vec2=st.lists(st.floats(min_value=-1, max_value=1), min_size=1280, max_size=1280)
)
def test_cosine_similarity_mathematical_correctness(vec1, vec2):
    """
    对于任意两个已归一化的特征向量，计算的余弦相似度应等于两向量的点积，
    且结果在 [0, 1] 范围内
    """
    # 转换为 numpy 数组并归一化
    vec1 = np.array(vec1)
    vec2 = np.array(vec2)
    vec1 = vec1 / np.linalg.norm(vec1)
    vec2 = vec2 / np.linalg.norm(vec2)

    # 计算相似度
    similarity = cosine_similarity(vec1, vec2)

    # 验证结果在 [0, 1] 范围内
    assert 0.0 <= similarity <= 1.0

    # 验证等于点积
    expected_similarity = np.dot(vec1, vec2)
    assert abs(similarity - expected_similarity) < 1e-6
```

**示例：衣橱筛选正确性属性测试**
```python
from hypothesis import given, strategies as st
from app.services.wardrobe import WardrobeManager
from app.models import Garment

# Feature: smart-outfit-assistant, Property 16: 衣橱筛选正确性
@given(
    category=st.sampled_from(["上衣", "裤子", "裙子", "外套", "鞋", "包"]),
    num_garments=st.integers(min_value=5, max_value=20)
)
def test_wardrobe_filter_correctness(category, num_garments):
    """
    对于任意筛选条件（品类），筛选结果中的所有服饰都应满足该筛选条件
    """
    wardrobe_manager = WardrobeManager(user_id="test_user")

    # 添加随机服饰（包含目标品类和其他品类）
    for i in range(num_garments):
        garment_category = category if i % 2 == 0 else st.sampled_from(["上衣", "裤子", "裙子"]).example()
        wardrobe_manager.add_garment(
            category=garment_category,
            main_color={"name": "蓝色", "rgb": [0, 100, 200]},
            style_tags=["通勤"],
            feature_vector=[0.1] * 1280
        )

    # 按品类筛选
    filtered_garments = wardrobe_manager.filter_by_category(category)

    # 验证所有结果都属于目标品类
    assert all(g.category == category for g in filtered_garments)
    assert len(filtered_garments) > 0  # 至少有一个结果
```


### 测试覆盖目标

#### 单元测试覆盖

- **代码覆盖率**：目标 80% 以上
- **关键路径**：100% 覆盖认证、图像识别、相似度计算、搭配推荐、适合度评分
- **错误处理**：100% 覆盖所有自定义异常类型
- **边缘情况**：覆盖空值、边界值、无效输入

#### 属性测试覆盖

- **正确性属性**：实现设计文档中定义的所有 32 个属性
- **迭代次数**：每个属性测试至少 100 次迭代
- **数据生成**：使用 Hypothesis 策略生成多样化的测试数据

### 性能测试

性能测试验证系统是否满足响应时间要求：

```python
import pytest
import time
from app.services.image_recognition import ImageRecognizer

def test_image_recognition_performance():
    """测试图像识别性能：单张图片 < 2 秒"""
    recognizer = ImageRecognizer()

    start_time = time.time()
    result = recognizer.recognize("test_images/shirt.jpg")
    end_time = time.time()

    elapsed_time = end_time - start_time
    assert elapsed_time < 2.0, f"Recognition took {elapsed_time:.2f}s, expected < 2s"

def test_similarity_analysis_performance():
    """测试相似度分析性能：< 2 秒"""
    analyzer = SimilarityAnalyzer()
    wardrobe = load_test_wardrobe(size=50)  # 50 个服饰

    start_time = time.time()
    matches = analyzer.find_similar_garments(
        target_feature=np.random.rand(1280),
        wardrobe_garments=wardrobe
    )
    end_time = time.time()

    elapsed_time = end_time - start_time
    assert elapsed_time < 2.0, f"Similarity analysis took {elapsed_time:.2f}s, expected < 2s"

def test_outfit_recommendation_performance():
    """测试搭配推荐性能：< 3 秒"""
    recommender = OutfitRecommender()
    wardrobe = load_test_wardrobe(size=50)
    target_garment = create_test_garment(category="上衣")
    user_profile = create_test_profile()

    start_time = time.time()
    outfits = recommender.recommend_outfits(
        target_garment=target_garment,
        wardrobe=wardrobe,
        user_profile=user_profile,
        num_outfits=3
    )
    end_time = time.time()

    elapsed_time = end_time - start_time
    assert elapsed_time < 3.0, f"Outfit recommendation took {elapsed_time:.2f}s, expected < 3s"
```


### 集成测试

集成测试验证多个组件协同工作的正确性：

```python
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_end_to_end_similarity_analysis():
    """端到端测试：从注册到相似度分析"""

    # 1. 注册用户
    register_response = client.post("/api/v1/auth/register", json={
        "username": "test_user",
        "email": "test@example.com",
        "password": "SecurePass123"
    })
    assert register_response.status_code == 200

    # 2. 登录获取 token
    login_response = client.post("/api/v1/auth/login", json={
        "username": "test_user",
        "password": "SecurePass123"
    })
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. 创建用户画像
    profile_response = client.post("/api/v1/profile", headers=headers, json={
        "height": 170,
        "body_type": "偏瘦",
        "skin_tone": "冷白",
        "style_preference": ["通勤", "简约"],
        "budget_range": "中等",
        "avoid_body_parts": ["肩"]
    })
    assert profile_response.status_code == 200

    # 4. 添加服饰到衣橱
    with open("test_images/shirt1.jpg", "rb") as f:
        add_response = client.post(
            "/api/v1/wardrobe/garments",
            headers=headers,
            files={"image": f}
        )
    assert add_response.status_code == 200

    # 5. 相似度分析
    with open("test_images/shirt2.jpg", "rb") as f:
        similarity_response = client.post(
            "/api/v1/analysis/similarity",
            headers=headers,
            files={"image": f}
        )
    assert similarity_response.status_code == 200

    # 验证响应结构
    data = similarity_response.json()
    assert "target_garment" in data
    assert "similar_garments" in data
    assert "has_duplicate_warning" in data
```


### 测试数据管理

#### 测试数据生成

```python
from faker import Faker
import numpy as np

fake = Faker()

def create_test_user():
    """生成测试用户"""
    return {
        "username": fake.user_name(),
        "email": fake.email(),
        "password": fake.password(length=12)
    }

def create_test_profile():
    """生成测试用户画像"""
    return UserProfile(
        height=fake.random_int(min=150, max=190),
        body_type=fake.random_element(["偏瘦", "微胖", "梨形", "倒三角", "沙漏", "矩形"]),
        skin_tone=fake.random_element(["冷白", "黄皮", "小麦", "深色"]),
        style_preference=fake.random_elements(
            ["通勤", "学院", "甜酷", "简约", "街头", "复古"],
            length=2,
            unique=True
        ),
        budget_range=fake.random_element(["经济", "中等", "高端"]),
        avoid_body_parts=fake.random_elements(
            ["肩", "腰", "臀", "大腿", "小腿"],
            length=fake.random_int(min=0, max=2),
            unique=True
        )
    )

def create_test_garment(category: str = None):
    """生成测试服饰"""
    if category is None:
        category = fake.random_element(["上衣", "裤子", "裙子", "外套", "鞋", "包"])

    return Garment(
        category=category,
        main_color=Color(
            name=fake.random_element(["红色", "蓝色", "绿色", "黑色", "白色"]),
            rgb=(fake.random_int(0, 255), fake.random_int(0, 255), fake.random_int(0, 255)),
            hsv=(fake.random_int(0, 360), fake.random_int(0, 100), fake.random_int(0, 100)),
            hex_code=fake.hex_color()
        ),
        style_tags=fake.random_elements(
            ["通勤", "休闲", "正式", "运动", "街头"],
            length=2,
            unique=True
        ),
        fit_type=fake.random_element(["修身", "标准", "宽松", "oversized"]),
        feature_vector=np.random.rand(1280).tolist(),
        image_path=f"test_images/{fake.uuid4()}.jpg",
        image_url=fake.image_url()
    )
```

#### 测试数据库

使用独立的测试数据库，避免污染生产数据：

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base

TEST_DATABASE_URL = "postgresql://test_user:test_pass@localhost/test_db"

@pytest.fixture(scope="function")
def test_db():
    """创建测试数据库会话"""
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(engine)

    TestingSessionLocal = sessionmaker(bind=engine)
    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)
```


### 持续集成 (CI)

测试应集成到 CI/CD 流程中，确保每次代码提交都经过验证：

```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:14
        env:
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_pass
          POSTGRES_DB: test_db
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov hypothesis

      - name: Run unit tests
        run: pytest tests/unit --cov=app --cov-report=xml

      - name: Run property tests
        run: pytest tests/property --hypothesis-profile=ci

      - name: Run integration tests
        run: pytest tests/integration

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
```

### 测试执行命令

```bash
# 运行所有测试
pytest

# 运行单元测试
pytest tests/unit

# 运行属性测试
pytest tests/property

# 运行集成测试
pytest tests/integration

# 运行性能测试
pytest tests/performance

# 生成覆盖率报告
pytest --cov=app --cov-report=html

# 运行特定测试
pytest tests/unit/test_auth.py::test_register_valid_user

# 详细输出
pytest -v

# 显示打印输出
pytest -s
```

### 测试最佳实践

1. **测试隔离**：每个测试应独立运行，不依赖其他测试的状态
2. **测试命名**：使用描述性名称，清楚表达测试意图
3. **AAA 模式**：Arrange（准备）、Act（执行）、Assert（断言）
4. **Mock 外部依赖**：使用 mock 隔离外部服务（数据库、API、文件系统）
5. **测试数据清理**：测试结束后清理所有测试数据
6. **快速反馈**：单元测试应快速执行（< 1 秒/测试）
7. **持续维护**：随着代码演进，及时更新测试

t_user:test_pass@localhost/test_db
          POSTGRES_DB: test_db
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov hypothesis

      - name: Run unit tests
        run: pytest tests/unit --cov=app --cov-report=xml

      - name: Run property tests
        run: pytest tests/property --hypothesis-profile=ci

      - name: Run integration tests
        run: pytest tests/integration

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
```


## CLI 工具设计 (CLI Tool Design)

CLI 工具为开发者和高级用户提供命令行接口，方便快速测试和自动化脚本调用。

### 技术选型

- **框架**: Python Click - 强大的命令行接口创建工具
- **输出美化**: Rich - 终端富文本和表格输出
- **HTTP 客户端**: Requests - 调用后端 API
- **配置管理**: 本地配置文件存储认证信息

### 命令结构

```
outfit-cli
├── auth
│   ├── register    # 注册新用户
│   └── login       # 登录获取 token
├── profile
│   ├── create      # 创建用户画像
│   ├── show        # 显示用户画像
│   └── update      # 更新用户画像
├── wardrobe
│   ├── add         # 添加服饰
│   ├── list        # 列出所有服饰
│   ├── show        # 显示服饰详情
│   └── delete      # 删除服饰
└── analyze
    ├── similarity  # 相似度分析
    ├── recommend   # 搭配推荐
    └── suitability # 适合度评分
```

### CLI 实现示例

```python
import click
import requests
from rich.console import Console
from rich.table import Table
from rich import print as rprint
import json
from pathlib import Path

console = Console()
CONFIG_FILE = Path.home() / ".outfit-cli" / "config.json"

class APIClient:
    """API 客户端"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.token = self._load_token()

    def _load_token(self) -> str:
        """从配置文件加载 token"""
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return config.get('token', '')
        return ''

    def _save_token(self, token: str):
        """保存 token 到配置文件"""
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            json.dump({'token': token}, f)

    def _headers(self) -> dict:
        """构建请求头"""
        if self.token:
            return {'Authorization': f'Bearer {self.token}'}
        return {}

    def register(self, username: str, email: str, password: str):
        """注册用户"""
        response = requests.post(
            f"{self.base_url}/api/v1/auth/register",
            json={"username": username, "email": email, "password": password}
        )
        response.raise_for_status()
        return response.json()

    def login(self, username: str, password: str):
        """登录"""
        response = requests.post(
            f"{self.base_url}/api/v1/auth/login",
            json={"username": username, "password": password}
        )
        response.raise_for_status()
        data = response.json()
        self._save_token(data['access_token'])
        self.token = data['access_token']
        return data

    def add_garment(self, image_path: str):
        """添加服饰"""
        with open(image_path, 'rb') as f:
            files = {'image': f}
            response = requests.post(
                f"{self.base_url}/api/v1/wardrobe/garments",
                headers=self._headers(),
                files=files
            )
        response.raise_for_status()
        return response.json()

    def list_wardrobe(self, category: str = None):
        """列出衣橱"""
        params = {'category': category} if category else {}
        response = requests.get(
            f"{self.base_url}/api/v1/wardrobe/garments",
            headers=self._headers(),
            params=params
        )
        response.raise_for_status()
        return response.json()

    def analyze_similarity(self, image_path: str):
        """相似度分析"""
        with open(image_path, 'rb') as f:
            files = {'image': f}
            response = requests.post(
                f"{self.base_url}/api/v1/analysis/similarity",
                headers=self._headers(),
                files=files
            )
        response.raise_for_status()
        return response.json()

client = APIClient()

@click.group()
def cli():
    """智能穿搭助手 CLI 工具"""
    pass

# 认证命令组
@cli.group()
def auth():
    """用户认证命令"""
    pass

@auth.command()
@click.option('--username', prompt=True, help='用户名')
@click.option('--email', prompt=True, help='邮箱')
@click.option('--password', prompt=True, hide_input=True, help='密码')
def register(username, email, password):
    """注册新用户"""
    try:
        result = client.register(username, email, password)
        console.print(f"[green]✓[/green] 注册成功！用户 ID: {result['user_id']}")
    except requests.HTTPError as e:
        console.print(f"[red]✗[/red] 注册失败: {e.response.json().get('message', str(e))}")

@auth.command()
@click.option('--username', prompt=True, help='用户名')
@click.option('--password', prompt=True, hide_input=True, help='密码')
def login(username, password):
    """登录获取访问令牌"""
    try:
        result = client.login(username, password)
        console.print(f"[green]✓[/green] 登录成功！")
        console.print(f"Token 已保存到 {CONFIG_FILE}")
    except requests.HTTPError as e:
        console.print(f"[red]✗[/red] 登录失败: {e.response.json().get('message', str(e))}")

# 衣橱命令组
@cli.group()
def wardrobe():
    """衣橱管理命令"""
    pass

@wardrobe.command()
@click.argument('image_path', type=click.Path(exists=True))
def add(image_path):
    """添加服饰到衣橱"""
    try:
        with console.status("[bold green]正在识别图片..."):
            result = client.add_garment(image_path)

        console.print(f"[green]✓[/green] 服饰添加成功！")
        console.print(f"品类: {result['category']}")
        console.print(f"主色: {result['main_color']['name']}")
        console.print(f"风格: {', '.join(result['style_tags'])}")
    except requests.HTTPError as e:
        console.print(f"[red]✗[/red] 添加失败: {e.response.json().get('message', str(e))}")

@wardrobe.command()
@click.option('--category', help='按品类筛选')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='输出格式')
def list(category, format):
    """列出衣橱中的所有服饰"""
    try:
        result = client.list_wardrobe(category)
        garments = result['garments']

        if format == 'json':
            console.print_json(data=garments)
        else:
            table = Table(title="我的衣橱")
            table.add_column("ID", style="cyan")
            table.add_column("品类", style="magenta")
            table.add_column("颜色", style="green")
            table.add_column("风格", style="yellow")

            for g in garments:
                table.add_row(
                    g['garment_id'][:8],
                    g['category'],
                    g['main_color']['name'],
                    ', '.join(g['style_tags'])
                )

            console.print(table)
            console.print(f"\n总计: {result['total']} 件")
    except requests.HTTPError as e:
        console.print(f"[red]✗[/red] 查询失败: {e.response.json().get('message', str(e))}")

# 分析命令组
@cli.group()
def analyze():
    """分析命令"""
    pass

@analyze.command()
@click.argument('image_path', type=click.Path(exists=True))
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='输出格式')
def similarity(image_path, format):
    """分析服饰相似度"""
    try:
        with console.status("[bold green]正在分析相似度..."):
            result = client.analyze_similarity(image_path)

        if format == 'json':
            console.print_json(data=result)
        else:
            # 显示目标服饰信息
            console.print("\n[bold]目标服饰:[/bold]")
            console.print(f"品类: {result['target_garment']['category']}")
            console.print(f"颜色: {result['target_garment']['main_color']['name']}")

            # 显示相似服饰
            if result['similar_garments']:
                table = Table(title="\n相似服饰")
                table.add_column("相似度", style="cyan")
                table.add_column("等级", style="magenta")
                table.add_column("品类", style="green")
                table.add_column("颜色", style="yellow")

                for g in result['similar_garments']:
                    table.add_row(
                        f"{g['similarity_score']:.2%}",
                        g['similarity_level'],
                        g['category'],
                        g['main_color']['name']
                    )

                console.print(table)

                # 重复预警
                if result['has_duplicate_warning']:
                    console.print(f"\n[bold red]⚠ 重复预警:[/bold red] {result['recommendation']}")
            else:
                console.print("\n[green]✓[/green] 未发现相似服饰")
    except requests.HTTPError as e:
        console.print(f"[red]✗[/red] 分析失败: {e.response.json().get('message', str(e))}")

if __name__ == '__main__':
    cli()
```


### CLI 配置管理

```python
# config.py
import json
from pathlib import Path
from typing import Optional

class CLIConfig:
    """CLI 配置管理"""

    def __init__(self, config_path: Path = None):
        self.config_path = config_path or Path.home() / ".outfit-cli" / "config.json"
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """加载配置"""
        if self.config_path.exists():
            with open(self.config_path, 'r') as f:
                return json.load(f)
        return {}

    def _save_config(self):
        """保存配置"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)

    def get(self, key: str, default=None):
        """获取配置项"""
        return self.config.get(key, default)

    def set(self, key: str, value):
        """设置配置项"""
        self.config[key] = value
        self._save_config()

    def get_token(self) -> Optional[str]:
        """获取认证 token"""
        return self.get('token')

    def set_token(self, token: str):
        """设置认证 token"""
        self.set('token', token)

    def get_base_url(self) -> str:
        """获取 API 基础 URL"""
        return self.get('base_url', 'http://localhost:8000')

    def set_base_url(self, url: str):
        """设置 API 基础 URL"""
        self.set('base_url', url)
```


## MCP 服务设计 (MCP Service Design)

MCP (Model Context Protocol) 服务允许 AI 智能体（如 ChatGPT、Claude）调用智能穿搭助手的功能。

### MCP 协议概述

MCP 是一个标准化协议，用于 AI 模型与外部工具之间的通信。它定义了：
- 工具发现机制
- 工具调用接口
- 参数验证规范
- 响应格式标准

### MCP 服务架构

```
┌─────────────────────────────────────┐
│      AI 智能体 (ChatGPT/Claude)      │
└─────────────────┬───────────────────┘
                  │ MCP Protocol
                  ▼
┌─────────────────────────────────────┐
│         MCP Server (Python)         │
│  ┌───────────────────────────────┐  │
│  │  Tool Registry                │  │
│  │  - add_garment_to_wardrobe    │  │
│  │  - analyze_similarity         │  │
│  │  - recommend_outfits          │  │
│  │  - score_suitability          │  │
│  └───────────────────────────────┘  │
└─────────────────┬───────────────────┘
                  │ HTTP/REST
                  ▼
┌─────────────────────────────────────┐
│      FastAPI Backend Service        │
└─────────────────────────────────────┘
```

### MCP 工具定义

```python
from mcp import MCPServer, Tool, ToolParameter
from typing import Dict, Any
import requests

class SmartOutfitMCPServer(MCPServer):
    """智能穿搭助手 MCP 服务器"""

    def __init__(self, backend_url: str = "http://localhost:8000"):
        super().__init__(name="smart-outfit-assistant", version="1.0.0")
        self.backend_url = backend_url
        self.register_tools()

    def register_tools(self):
        """注册所有工具"""

        # 工具 1: 添加服饰到衣橱
        self.add_tool(Tool(
            name="add_garment_to_wardrobe",
            description="添加服饰图片到用户衣橱，系统会自动识别品类、颜色和风格",
            parameters=[
                ToolParameter(
                    name="image_url",
                    type="string",
                    description="服饰图片的 URL",
                    required=True
                ),
                ToolParameter(
                    name="user_token",
                    type="string",
                    description="用户认证 token",
                    required=True
                )
            ],
            handler=self.add_garment_handler
        ))

        # 工具 2: 相似度分析
        self.add_tool(Tool(
            name="analyze_similarity",
            description="分析待购买服饰与用户衣橱中服饰的相似度，提供重复预警",
            parameters=[
                ToolParameter(
                    name="image_url",
                    type="string",
                    description="待购买服饰图片的 URL",
                    required=True
                ),
                ToolParameter(
                    name="user_token",
                    type="string",
                    description="用户认证 token",
                    required=True
                )
            ],
            handler=self.analyze_similarity_handler
        ))

        # 工具 3: 搭配推荐
        self.add_tool(Tool(
            name="recommend_outfits",
            description="基于用户衣橱生成搭配推荐方案",
            parameters=[
                ToolParameter(
                    name="image_url",
                    type="string",
                    description="待购买服饰图片的 URL",
                    required=True
                ),
                ToolParameter(
                    name="user_token",
                    type="string",
                    description="用户认证 token",
                    required=True
                ),
                ToolParameter(
                    name="num_outfits",
                    type="integer",
                    description="推荐方案数量（默认 3）",
                    required=False,
                    default=3
                )
            ],
            handler=self.recommend_outfits_handler
        ))

        # 工具 4: 适合度评分
        self.add_tool(Tool(
            name="score_suitability",
            description="评估服饰是否适合用户的肤色、身材和风格偏好",
            parameters=[
                ToolParameter(
                    name="image_url",
                    type="string",
                    description="待购买服饰图片的 URL",
                    required=True
                ),
                ToolParameter(
                    name="user_token",
                    type="string",
                    description="用户认证 token",
                    required=True
                )
            ],
            handler=self.score_suitability_handler
        ))

    async def add_garment_handler(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """添加服饰处理器"""
        image_url = params['image_url']
        user_token = params['user_token']

        # 下载图片
        image_data = requests.get(image_url).content

        # 调用后端 API
        response = requests.post(
            f"{self.backend_url}/api/v1/wardrobe/garments",
            headers={'Authorization': f'Bearer {user_token}'},
            files={'image': ('garment.jpg', image_data, 'image/jpeg')}
        )

        if response.status_code == 200:
            return {
                "success": True,
                "data": response.json(),
                "message": "服饰添加成功"
            }
        else:
            return {
                "success": False,
                "error": response.json().get('message', 'Unknown error'),
                "message": "服饰添加失败"
            }

    async def analyze_similarity_handler(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """相似度分析处理器"""
        image_url = params['image_url']
        user_token = params['user_token']

        # 下载图片
        image_data = requests.get(image_url).content

        # 调用后端 API
        response = requests.post(
            f"{self.backend_url}/api/v1/analysis/similarity",
            headers={'Authorization': f'Bearer {user_token}'},
            files={'image': ('garment.jpg', image_data, 'image/jpeg')}
        )

        if response.status_code == 200:
            data = response.json()
            return {
                "success": True,
                "data": data,
                "message": self._format_similarity_message(data)
            }
        else:
            return {
                "success": False,
                "error": response.json().get('message', 'Unknown error'),
                "message": "相似度分析失败"
            }

    async def recommend_outfits_handler(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """搭配推荐处理器"""
        image_url = params['image_url']
        user_token = params['user_token']

        # 下载图片
        image_data = requests.get(image_url).content

        # 调用后端 API
        response = requests.post(
            f"{self.backend_url}/api/v1/recommendations/outfits",
            headers={'Authorization': f'Bearer {user_token}'},
            files={'image': ('garment.jpg', image_data, 'image/jpeg')}
        )

        if response.status_code == 200:
            data = response.json()
            return {
                "success": True,
                "data": data,
                "message": self._format_outfit_message(data)
            }
        else:
            return {
                "success": False,
                "error": response.json().get('message', 'Unknown error'),
                "message": "搭配推荐失败"
            }

    async def score_suitability_handler(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """适合度评分处理器"""
        image_url = params['image_url']
        user_token = params['user_token']

        # 下载图片
        image_data = requests.get(image_url).content

        # 调用后端 API
        response = requests.post(
            f"{self.backend_url}/api/v1/analysis/suitability",
            headers={'Authorization': f'Bearer {user_token}'},
            files={'image': ('garment.jpg', image_data, 'image/jpeg')}
        )

        if response.status_code == 200:
            data = response.json()
            return {
                "success": True,
                "data": data,
                "message": self._format_suitability_message(data)
            }
        else:
            return {
                "success": False,
                "error": response.json().get('message', 'Unknown error'),
                "message": "适合度评分失败"
            }

    def _format_similarity_message(self, data: Dict) -> str:
        """格式化相似度分析消息"""
        target = data['target_garment']
        similar = data['similar_garments']

        msg = f"目标服饰：{target['category']}，{target['main_color']['name']}色\n\n"

        if similar:
            msg += f"发现 {len(similar)} 件相似服饰：\n"
            for g in similar[:3]:
                msg += f"- {g['category']}，{g['main_color']['name']}色，相似度 {g['similarity_score']:.0%}（{g['similarity_level']}）\n"

            if data['has_duplicate_warning']:
                msg += f"\n⚠️ {data['recommendation']}"
        else:
            msg += "未发现相似服饰，可以放心购买。"

        return msg

    def _format_outfit_message(self, data: Dict) -> str:
        """格式化搭配推荐消息"""
        target = data['target_garment']
        outfits = data['outfit_cards']

        msg = f"为您的{target['category']}（{target['main_color']['name']}色）推荐了 {len(outfits)} 套搭配：\n\n"

        for i, outfit in enumerate(outfits, 1):
            msg += f"{i}. {outfit['description']}\n"
            msg += f"   场合：{outfit['occasion']}\n"
            msg += f"   颜色搭配：{outfit['color_harmony']}\n\n"

        return msg

    def _format_suitability_message(self, data: Dict) -> str:
        """格式化适合度评分消息"""
        garment = data['garment']
        score = data['suitability_score']

        msg = f"服饰：{garment['category']}，{garment['main_color']['name']}色\n"
        msg += f"综合适合度：{score} 分\n\n"
        msg += f"颜色适合度：{data['color_score']} 分 - {data['explanation']['color']}\n"
        msg += f"版型适合度：{data['fit_score']} 分 - {data['explanation']['fit']}\n"
        msg += f"风格适合度：{data['style_score']} 分 - {data['explanation']['style']}\n\n"
        msg += f"推荐场合：{', '.join(data['recommended_occasions'])}\n"

        if data['suggestions']:
            msg += f"\n改进建议：\n"
            for suggestion in data['suggestions']:
                msg += f"- {suggestion}\n"

        return msg

# 启动 MCP 服务器
if __name__ == '__main__':
    server = SmartOutfitMCPServer()
    server.run(host='0.0.0.0', port=5000)
```


## Flutter 移动端设计 (Flutter Mobile App Design)

Flutter 移动端应用为用户提供直观的图形界面，支持 iOS 和 Android 平台。

### 技术架构

**架构模式**: Clean Architecture + MVVM

```
┌─────────────────────────────────────────────────────┐
│                  Presentation Layer                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐    │
│  │   Pages    │  │  Widgets   │  │ ViewModels │    │
│  └────────────┘  └────────────┘  └────────────┘    │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│                   Domain Layer                       │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐    │
│  │  Entities  │  │  Use Cases │  │Repositories│    │
│  └────────────┘  └────────────┘  └────────────┘    │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│                    Data Layer                        │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐    │
│  │API Client  │  │Local Cache │  │Data Models │    │
│  └────────────┘  └────────────┘  └────────────┘    │
└─────────────────────────────────────────────────────┘
```

### 状态管理

使用 Riverpod 进行状态管理：

```dart
// providers.dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:dio/dio.dart';

// API 客户端 Provider
final dioProvider = Provider<Dio>((ref) {
  final dio = Dio(BaseOptions(
    baseUrl: 'http://localhost:8000/api/v1',
    connectTimeout: Duration(seconds: 5),
    receiveTimeout: Duration(seconds: 3),
  ));

  // 添加认证拦截器
  dio.interceptors.add(InterceptorsWrapper(
    onRequest: (options, handler) {
      final token = ref.read(authTokenProvider);
      if (token != null) {
        options.headers['Authorization'] = 'Bearer $token';
      }
      handler.next(options);
    },
  ));

  return dio;
});

// 认证状态 Provider
final authTokenProvider = StateProvider<String?>((ref) => null);

final authStateProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  return AuthNotifier(ref.read(dioProvider));
});

// 衣橱状态 Provider
final wardrobeProvider = StateNotifierProvider<WardrobeNotifier, WardrobeState>((ref) {
  return WardrobeNotifier(ref.read(dioProvider));
});

// 用户画像 Provider
final profileProvider = StateNotifierProvider<ProfileNotifier, ProfileState>((ref) {
  return ProfileNotifier(ref.read(dioProvider));
});
```

### 核心页面设计

#### 1. 登录/注册页面

```dart
// pages/auth/login_page.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class LoginPage extends ConsumerStatefulWidget {
  @override
  _LoginPageState createState() => _LoginPageState();
}

class _LoginPageState extends ConsumerState<LoginPage> {
  final _formKey = GlobalKey<FormState>();
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _isLoading = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('登录')),
      body: Padding(
        padding: EdgeInsets.all(16.0),
        child: Form(
          key: _formKey,
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              TextFormField(
                controller: _usernameController,
                decoration: InputDecoration(
                  labelText: '用户名',
                  border: OutlineInputBorder(),
                ),
                validator: (value) {
                  if (value == null || value.isEmpty) {
                    return '请输入用户名';
                  }
                  return null;
                },
              ),
              SizedBox(height: 16),
              TextFormField(
                controller: _passwordController,
                decoration: InputDecoration(
                  labelText: '密码',
                  border: OutlineInputBorder(),
                ),
                obscureText: true,
                validator: (value) {
                  if (value == null || value.isEmpty) {
                    return '请输入密码';
                  }
                  return null;
                },
              ),
              SizedBox(height: 24),
              ElevatedButton(
                onPressed: _isLoading ? null : _handleLogin,
                child: _isLoading
                    ? CircularProgressIndicator()
                    : Text('登录'),
                style: ElevatedButton.styleFrom(
                  minimumSize: Size(double.infinity, 48),
                ),
              ),
              TextButton(
                onPressed: () {
                  Navigator.pushNamed(context, '/register');
                },
                child: Text('还没有账号？立即注册'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _handleLogin() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _isLoading = true);

    try {
      await ref.read(authStateProvider.notifier).login(
        _usernameController.text,
        _passwordController.text,
      );

      Navigator.pushReplacementNamed(context, '/home');
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('登录失败: $e')),
      );
    } finally {
      setState(() => _isLoading = false);
    }
  }
}
```

#### 2. 衣橱列表页面

```dart
// pages/wardrobe/wardrobe_page.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class WardrobePage extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final wardrobeState = ref.watch(wardrobeProvider);

    return Scaffold(
      appBar: AppBar(
        title: Text('我的衣橱'),
        actions: [
          IconButton(
            icon: Icon(Icons.filter_list),
            onPressed: () => _showFilterDialog(context, ref),
          ),
        ],
      ),
      body: wardrobeState.when(
        loading: () => Center(child: CircularProgressIndicator()),
        error: (error, stack) => Center(child: Text('加载失败: $error')),
        data: (garments) {
          if (garments.isEmpty) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.checkroom, size: 64, color: Colors.grey),
                  SizedBox(height: 16),
                  Text('衣橱还是空的', style: TextStyle(fontSize: 18)),
                  SizedBox(height: 8),
                  Text('点击右下角按钮添加服饰'),
                ],
              ),
            );
          }

          return GridView.builder(
            padding: EdgeInsets.all(8),
            gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 2,
              crossAxisSpacing: 8,
              mainAxisSpacing: 8,
              childAspectRatio: 0.75,
            ),
            itemCount: garments.length,
            itemBuilder: (context, index) {
              final garment = garments[index];
              return GarmentCard(garment: garment);
            },
          );
        },
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _showAddGarmentOptions(context),
        child: Icon(Icons.add),
      ),
    );
  }

  void _showFilterDialog(BuildContext context, WidgetRef ref) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('筛选'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              title: Text('全部'),
              onTap: () {
                ref.read(wardrobeProvider.notifier).filterByCategory(null);
                Navigator.pop(context);
              },
            ),
            ListTile(
              title: Text('上衣'),
              onTap: () {
                ref.read(wardrobeProvider.notifier).filterByCategory('上衣');
                Navigator.pop(context);
              },
            ),
            // 其他品类...
          ],
        ),
      ),
    );
  }

  void _showAddGarmentOptions(BuildContext context) {
    showModalBottomSheet(
      context: context,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: Icon(Icons.camera_alt),
              title: Text('拍照'),
              onTap: () {
                Navigator.pop(context);
                Navigator.pushNamed(context, '/add-garment', arguments: 'camera');
              },
            ),
            ListTile(
              leading: Icon(Icons.photo_library),
              title: Text('从相册选择'),
              onTap: () {
                Navigator.pop(context);
                Navigator.pushNamed(context, '/add-garment', arguments: 'gallery');
              },
            ),
          ],
        ),
      ),
    );
  }
}

class GarmentCard extends StatelessWidget {
  final Garment garment;

  const GarmentCard({required this.garment});

  @override
  Widget build(BuildContext context) {
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () {
          Navigator.pushNamed(
            context,
            '/garment-detail',
            arguments: garment.id,
          );
        },
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Image.network(
                garment.imageUrl,
                fit: BoxFit.cover,
                width: double.infinity,
                loadingBuilder: (context, child, loadingProgress) {
                  if (loadingProgress == null) return child;
                  return Center(child: CircularProgressIndicator());
                },
              ),
            ),
            Padding(
              padding: EdgeInsets.all(8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    garment.category,
                    style: TextStyle(fontWeight: FontWeight.bold),
                  ),
                  SizedBox(height: 4),
                  Row(
                    children: [
                      Container(
                        width: 16,
                        height: 16,
                        decoration: BoxDecoration(
                          color: Color(int.parse(
                            garment.mainColor.hexCode.substring(1),
                            radix: 16,
                          ) + 0xFF000000),
                          shape: BoxShape.circle,
                        ),
                      ),
                      SizedBox(width: 4),
                      Text(
                        garment.mainColor.name,
                        style: TextStyle(fontSize: 12),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
```

#### 3. 添加服饰页面

```dart
// pages/wardrobe/add_garment_page.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';
import 'dart:io';

class AddGarmentPage extends ConsumerStatefulWidget {
  final String source; // 'camera' or 'gallery'

  const AddGarmentPage({required this.source});

  @override
  _AddGarmentPageState createState() => _AddGarmentPageState();
}

class _AddGarmentPageState extends ConsumerState<AddGarmentPage> {
  File? _imageFile;
  bool _isProcessing = false;
  RecognitionResult? _result;

  @override
  void initState() {
    super.initState();
    _pickImage();
  }

  Future<void> _pickImage() async {
    final picker = ImagePicker();
    final source = widget.source == 'camera'
        ? ImageSource.camera
        : ImageSource.gallery;

    final pickedFile = await picker.pickImage(source: source);

    if (pickedFile != null) {
      setState(() {
        _imageFile = File(pickedFile.path);
      });
      _processImage();
    } else {
      Navigator.pop(context);
    }
  }

  Future<void> _processImage() async {
    if (_imageFile == null) return;

    setState(() => _isProcessing = true);

    try {
      final result = await ref
          .read(wardrobeProvider.notifier)
          .addGarment(_imageFile!);

      setState(() {
        _result = result;
        _isProcessing = false;
      });
    } catch (e) {
      setState(() => _isProcessing = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('识别失败: $e')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('添加服饰')),
      body: _imageFile == null
          ? Center(child: CircularProgressIndicator())
          : Column(
              children: [
                Expanded(
                  child: Image.file(_imageFile!, fit: BoxFit.contain),
                ),
                if (_isProcessing)
                  Padding(
                    padding: EdgeInsets.all(16),
                    child: Column(
                      children: [
                        CircularProgressIndicator(),
                        SizedBox(height: 8),
                        Text('正在识别...'),
                      ],
                    ),
                  ),
                if (_result != null)
                  Container(
                    padding: EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black12,
                          blurRadius: 4,
                          offset: Offset(0, -2),
                        ),
                      ],
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '识别结果',
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        SizedBox(height: 12),
                        _buildResultRow('品类', _result!.category),
                        _buildResultRow('颜色', _result!.mainColor.name),
                        _buildResultRow(
                          '风格',
                          _result!.styleTags.join(', '),
                        ),
                        SizedBox(height: 16),
                        ElevatedButton(
                          onPressed: () {
                            Navigator.pop(context);
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(content: Text('服饰添加成功')),
                            );
                          },
                          child: Text('确认添加'),
                          style: ElevatedButton.styleFrom(
                            minimumSize: Size(double.infinity, 48),
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
    );
  }

  Widget _buildResultRow(String label, String value) {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Text('$label: ', style: TextStyle(fontWeight: FontWeight.w500)),
          Text(value),
        ],
      ),
    );
  }
}
```


#### 4. 相似度分析页面

```dart
// pages/analysis/similarity_page.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class SimilarityAnalysisPage extends ConsumerWidget {
  final File imageFile;

  const SimilarityAnalysisPage({required this.imageFile});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final analysisState = ref.watch(similarityAnalysisProvider(imageFile));

    return Scaffold(
      appBar: AppBar(title: Text('相似度分析')),
      body: analysisState.when(
        loading: () => Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              CircularProgressIndicator(),
              SizedBox(height: 16),
              Text('正在分析...'),
            ],
          ),
        ),
        error: (error, stack) => Center(
          child: Text('分析失败: $error'),
        ),
        data: (result) => SingleChildScrollView(
          padding: EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // 目标服饰
              Text(
                '目标服饰',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
              ),
              SizedBox(height: 12),
              Card(
                child: Padding(
                  padding: EdgeInsets.all(12),
                  child: Row(
                    children: [
                      Image.file(imageFile, width: 80, height: 80, fit: BoxFit.cover),
                      SizedBox(width: 12),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('品类: ${result.targetGarment.category}'),
                          Text('颜色: ${result.targetGarment.mainColor.name}'),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
              SizedBox(height: 24),

              // 相似服饰列表
              Text(
                '相似服饰',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
              ),
              SizedBox(height: 12),

              if (result.similarGarments.isEmpty)
                Card(
                  child: Padding(
                    padding: EdgeInsets.all(16),
                    child: Row(
                      children: [
                        Icon(Icons.check_circle, color: Colors.green, size: 32),
                        SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            '未发现相似服饰，可以放心购买！',
                            style: TextStyle(fontSize: 16),
                          ),
                        ),
                      ],
                    ),
                  ),
                )
              else
                ...result.similarGarments.map((match) => Card(
                  child: ListTile(
                    leading: Image.network(
                      match.garment.imageUrl,
                      width: 60,
                      height: 60,
                      fit: BoxFit.cover,
                    ),
                    title: Text(match.garment.category),
                    subtitle: Text(
                      '${match.garment.mainColor.name} · ${match.similarityLevel}',
                    ),
                    trailing: Container(
                      padding: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                      decoration: BoxDecoration(
                        color: _getSimilarityColor(match.similarityScore),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Text(
                        '${(match.similarityScore * 100).toInt()}%',
                        style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                      ),
                    ),
                  ),
                )),

              // 重复预警
              if (result.hasDuplicateWarning)
                Container(
                  margin: EdgeInsets.only(top: 16),
                  padding: EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Colors.orange.shade50,
                    border: Border.all(color: Colors.orange),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.warning, color: Colors.orange),
                      SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          result.recommendation,
                          style: TextStyle(fontSize: 14),
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Color _getSimilarityColor(double score) {
    if (score >= 0.8) return Colors.red;
    if (score >= 0.5) return Colors.orange;
    return Colors.green;
  }
}
```

### 数据模型

```dart
// models/garment.dart
class Garment {
  final String id;
  final String category;
  final Color mainColor;
  final List<String> styleTags;
  final String? fitType;
  final String imageUrl;

  Garment({
    required this.id,
    required this.category,
    required this.mainColor,
    required this.styleTags,
    this.fitType,
    required this.imageUrl,
  });

  factory Garment.fromJson(Map<String, dynamic> json) {
    return Garment(
      id: json['garment_id'],
      category: json['category'],
      mainColor: Color.fromJson(json['main_color']),
      styleTags: List<String>.from(json['style_tags']),
      fitType: json['fit_type'],
      imageUrl: json['image_url'],
    );
  }
}

class Color {
  final String name;
  final List<int> rgb;
  final String hexCode;

  Color({
    required this.name,
    required this.rgb,
    required this.hexCode,
  });

  factory Color.fromJson(Map<String, dynamic> json) {
    return Color(
      name: json['name'],
      rgb: List<int>.from(json['rgb']),
      hexCode: json['hex_code'],
    );
  }
}
```


## 部署架构设计 (Deployment Architecture)

### 生产环境架构

```
┌─────────────────────────────────────────────────────────┐
│                      Load Balancer                       │
│                     (Nginx / ALB)                        │
└────────────────────┬────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
         ▼                       ▼
┌──────────────────┐    ┌──────────────────┐
│  FastAPI Server  │    │  FastAPI Server  │
│    (Instance 1)  │    │    (Instance 2)  │
└────────┬─────────┘    └────────┬─────────┘
         │                       │
         └───────────┬───────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
         ▼                       ▼
┌──────────────────┐    ┌──────────────────┐
│   PostgreSQL     │    │      Redis       │
│   (Primary)      │    │     (Cache)      │
└────────┬─────────┘    └──────────────────┘
         │
         ▼
┌──────────────────┐
│   PostgreSQL     │
│   (Replica)      │
└──────────────────┘
```

### Docker 容器化

**Dockerfile (Backend)**
```dockerfile
FROM python:3.9-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 下载模型文件
RUN python scripts/download_models.py

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

**docker-compose.yml**
```yaml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:password@postgres:5432/outfit_db
      - REDIS_URL=redis://redis:6379/0
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
    depends_on:
      - postgres
      - redis
    volumes:
      - ./models:/app/models
      - ./uploads:/app/uploads
    restart: unless-stopped

  postgres:
    image: postgres:14
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=password
      - POSTGRES_DB=outfit_db
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - backend
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

### Nginx 配置

```nginx
# nginx.conf
upstream backend {
    least_conn;
    server backend:8000 max_fails=3 fail_timeout=30s;
}

server {
    listen 80;
    server_name api.outfit-assistant.com;

    # 重定向到 HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.outfit-assistant.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    client_max_body_size 10M;

    location / {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 超时设置
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    location /static {
        alias /app/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /uploads {
        alias /app/uploads;
        expires 7d;
        add_header Cache-Control "public";
    }
}
```

### 环境变量配置

```bash
# .env.production
# 数据库配置
DATABASE_URL=postgresql://user:password@postgres:5432/outfit_db
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# Redis 配置
REDIS_URL=redis://redis:6379/0
REDIS_MAX_CONNECTIONS=50

# JWT 配置
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# 文件存储
UPLOAD_DIR=/app/uploads
MAX_UPLOAD_SIZE=10485760  # 10 MB

# 模型配置
MODEL_PATH=/app/models
MODEL_CACHE_SIZE=1000

# 日志配置
LOG_LEVEL=INFO
LOG_FILE=/app/logs/app.log

# CORS 配置
CORS_ORIGINS=https://outfit-assistant.com,https://app.outfit-assistant.com

# 性能配置
WORKERS=4
WORKER_CLASS=uvicorn.workers.UvicornWorker
```


## 安全设计 (Security Design)

### 认证与授权

#### JWT Token 实现

```python
# security/jwt.py
from datetime import datetime, timedelta
from typing import Optional
import jwt
from passlib.context import CryptContext

# 密码加密上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT 配置
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

def hash_password(password: str) -> str:
    """哈希密码"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建访问令牌"""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    return encoded_jwt

def decode_access_token(token: str) -> dict:
    """解码访问令牌"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token has expired")
    except jwt.JWTError:
        raise AuthenticationError("Invalid token")
```

#### 认证依赖

```python
# dependencies/auth.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """获取当前用户"""
    token = credentials.credentials

    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )

    user = db.query(User).filter(User.user_id == user_id).first()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )

    return user
```

### 数据加密

#### 传输加密

- 使用 HTTPS/TLS 1.2+ 加密所有 API 通信
- 强制重定向 HTTP 到 HTTPS
- 使用 HSTS (HTTP Strict Transport Security) 头

#### 存储加密

```python
# security/encryption.py
from cryptography.fernet import Fernet
import os

# 加密密钥（从环境变量加载）
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY").encode()
cipher = Fernet(ENCRYPTION_KEY)

def encrypt_data(data: str) -> str:
    """加密数据"""
    encrypted = cipher.encrypt(data.encode())
    return encrypted.decode()

def decrypt_data(encrypted_data: str) -> str:
    """解密数据"""
    decrypted = cipher.decrypt(encrypted_data.encode())
    return decrypted.decode()
```

### 输入验证

```python
# validation/input_validator.py
from pydantic import BaseModel, validator, EmailStr
import re

class UserRegistrationInput(BaseModel):
    username: str
    email: EmailStr
    password: str

    @validator('username')
    def validate_username(cls, v):
        if len(v) < 3 or len(v) > 50:
            raise ValueError('Username must be between 3 and 50 characters')
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('Username can only contain letters, numbers, and underscores')
        return v

    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one digit')
        return v
```

### 速率限制

```python
# middleware/rate_limit.py
from fastapi import Request, HTTPException
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)

# 应用到路由
@app.post("/api/v1/auth/login")
@limiter.limit("5/minute")  # 每分钟最多 5 次登录尝试
async def login(request: Request, credentials: LoginCredentials):
    # 登录逻辑
    pass

@app.post("/api/v1/wardrobe/garments")
@limiter.limit("10/minute")  # 每分钟最多 10 次上传
async def add_garment(request: Request, image: UploadFile):
    # 添加服饰逻辑
    pass
```

### SQL 注入防护

使用 ORM (SQLAlchemy) 参数化查询，避免直接拼接 SQL：

```python
# 安全的查询方式
user = db.query(User).filter(User.username == username).first()

# 危险的查询方式（避免）
# query = f"SELECT * FROM users WHERE username = '{username}'"
# db.execute(query)
```

### XSS 防护

```python
# 输出转义
from markupsafe import escape

def sanitize_output(text: str) -> str:
    """转义 HTML 特殊字符"""
    return escape(text)
```

### CORS 配置

```python
# main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://outfit-assistant.com",
        "https://app.outfit-assistant.com"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    max_age=3600,
)
```

### 文件上传安全

```python
# security/file_upload.py
from fastapi import UploadFile, HTTPException
import magic
import hashlib

ALLOWED_MIME_TYPES = ['image/jpeg', 'image/png', 'image/webp']
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

async def validate_image_upload(file: UploadFile) -> bytes:
    """验证上传的图片文件"""

    # 读取文件内容
    content = await file.read()

    # 检查文件大小
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File size exceeds maximum allowed size of {MAX_FILE_SIZE} bytes"
        )

    # 检查 MIME 类型（基于文件内容，不是扩展名）
    mime = magic.from_buffer(content, mime=True)
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(ALLOWED_MIME_TYPES)}"
        )

    return content

def generate_secure_filename(content: bytes, extension: str) -> str:
    """生成安全的文件名"""
    # 使用内容哈希作为文件名
    hash_digest = hashlib.sha256(content).hexdigest()
    return f"{hash_digest}.{extension}"
```

### 日志与审计

```python
# logging/audit.py
import logging
from datetime import datetime

audit_logger = logging.getLogger('audit')

def log_user_action(user_id: str, action: str, details: dict = None):
    """记录用户操作"""
    audit_logger.info({
        'timestamp': datetime.utcnow().isoformat(),
        'user_id': user_id,
        'action': action,
        'details': details
    })

# 使用示例
log_user_action(
    user_id=current_user.user_id,
    action='garment_added',
    details={'garment_id': garment.garment_id, 'category': garment.category}
)
```

---

## 总结

本设计文档详细描述了智能穿搭助手系统的技术架构、核心算法、API 接口、数据模型、多端应用设计、部署架构和安全设计。系统采用模块化设计，各组件职责清晰，易于维护和扩展。

关键设计要点：
- 使用轻量级 MobileNetV2 模型实现快速图像识别
- 基于余弦相似度的高效相似度计算
- 规则引擎驱动的搭配推荐和适合度评分
- 多端支持（移动端、CLI、MCP）共享统一后端
- 完善的错误处理和安全机制
- 属性测试确保系统正确性

下一步可以根据本设计文档开始实现各个模块，并通过单元测试和属性测试验证功能正确性。
