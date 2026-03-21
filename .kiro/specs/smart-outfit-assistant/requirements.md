# 需求文档 - 智能穿搭助手

## 简介

智能穿搭助手是一款面向个人用户的穿搭决策与衣橱管理应用，旨在解决用户在线上购物和线下试衣时的三大核心痛点：重复购买困惑、搭配不确定性、适合度判断困难。系统通过轻量级图像识别与多模态推荐技术，围绕用户的真实衣橱构建智能决策工具，支持移动端 APP、后端服务、CLI 工具和 MCP 服务多种交互方式。

re## 术语表

- **System**: 智能穿搭助手系统的总称
- **User_Profile_Manager**: 用户画像管理模块
- **Wardrobe_Manager**: 衣橱管理模块
- **Similarity_Analyzer**: 相似度分析模块
- **Outfit_Recommender**: 搭配推荐模块
- **Suitability_Scorer**: 适合度评分模块
- **Image_Recognizer**: 图像识别模块
- **Feature_Extractor**: 特征提取模块
- **Mobile_App**: Flutter 移动端应用
- **Backend_Service**: FastAPI 后端服务
- **CLI_Tool**: 命令行工具
- **MCP_Service**: Model Context Protocol 服务
- **Garment**: 服饰单品
- **Wardrobe**: 用户的虚拟衣橱
- **Similarity_Score**: 相似度分数（0-1之间）
- **Suitability_Score**: 适合度分数（0-100之间）
- **Body_Type**: 体型类型（偏瘦/微胖/梨形/倒三角等）
- **Skin_Tone**: 肤色类型（冷白/黄皮/小麦等）
- **Style_Preference**: 风格偏好（通勤/学院/甜酷/简约/街头等）
- **Garment_Category**: 服饰品类（上衣/裤子/裙子/外套/鞋/包等）
- **Outfit_Card**: 搭配卡片，展示推荐的搭配方案
- **Feature_Vector**: 特征向量，用于相似度计算

## 需求

### 需求 1: 用户注册与认证

**用户故事:** 作为新用户，我想要注册账号并登录系统，以便使用智能穿搭助手的各项功能。

#### 验收标准

1. WHEN 用户提供有效的注册信息（用户名、密码、邮箱），THE System SHALL 创建新用户账号
2. WHEN 用户提供已存在的用户名或邮箱，THE System SHALL 返回注册失败提示
3. WHEN 用户提供有效的登录凭证，THE System SHALL 验证身份并授予访问权限
4. WHEN 用户提供无效的登录凭证，THE System SHALL 返回认证失败提示
5. THE System SHALL 使用加密方式存储用户密码

### 需求 2: 用户画像管理

**用户故事:** 作为用户，我想要创建和管理我的个人画像信息，以便系统能够提供个性化的穿搭建议。

#### 验收标准

1. WHEN 用户首次登录，THE User_Profile_Manager SHALL 引导用户填写基本画像信息
2. THE User_Profile_Manager SHALL 收集用户的身高信息（单位：厘米）
3. THE User_Profile_Manager SHALL 收集用户的 Body_Type 信息
4. THE User_Profile_Manager SHALL 收集用户的 Skin_Tone 信息
5. THE User_Profile_Manager SHALL 收集用户的 Style_Preference 信息
6. THE User_Profile_Manager SHALL 收集用户的预算范围信息
7. THE User_Profile_Manager SHALL 收集用户不希望强化的身体部位信息（肩/腰/臀/大腿等）
8. WHEN 用户请求修改画像信息，THE User_Profile_Manager SHALL 更新用户画像数据
9. THE User_Profile_Manager SHALL 持久化存储用户画像数据

### 需求 3: 图像导入与识别

**用户故事:** 作为用户，我想要通过拍照或导入图片的方式添加服饰单品，以便系统能够识别和管理我的衣橱。

#### 验收标准

1. WHERE Mobile_App 运行，THE System SHALL 支持通过相机拍照导入 Garment 图片
2. WHERE Mobile_App 运行，THE System SHALL 支持从相册选择导入 Garment 图片
3. WHERE CLI_Tool 运行，THE System SHALL 支持通过文件路径导入 Garment 图片
4. WHEN 用户导入 Garment 图片，THE Image_Recognizer SHALL 识别 Garment_Category
5. WHEN 用户导入 Garment 图片，THE Image_Recognizer SHALL 识别主色信息
6. WHEN 用户导入 Garment 图片，THE Image_Recognizer SHALL 识别风格标签
7. WHEN 用户导入 Garment 图片，THE Feature_Extractor SHALL 提取 Feature_Vector
8. IF 图片格式不支持或图片损坏，THEN THE System SHALL 返回导入失败提示
9. THE System SHALL 支持 JPEG、PNG、WebP 格式的图片

### 需求 4: 衣橱管理

**用户故事:** 作为用户，我想要管理我的虚拟衣橱，以便系统能够基于我的真实衣橱提供建议。

#### 验收标准

1. WHEN 用户添加 Garment，THE Wardrobe_Manager SHALL 将 Garment 信息存储到 Wardrobe
2. WHEN 用户添加 Garment，THE Wardrobe_Manager SHALL 存储 Garment 的 Feature_Vector
3. WHEN 用户请求查看 Wardrobe，THE Wardrobe_Manager SHALL 返回所有 Garment 列表
4. WHEN 用户请求删除 Garment，THE Wardrobe_Manager SHALL 从 Wardrobe 中移除该 Garment
5. WHEN 用户请求编辑 Garment 信息，THE Wardrobe_Manager SHALL 更新 Garment 的元数据
6. THE Wardrobe_Manager SHALL 支持按 Garment_Category 筛选 Garment
7. THE Wardrobe_Manager SHALL 支持按颜色筛选 Garment
8. THE Wardrobe_Manager SHALL 支持按风格标签筛选 Garment

### 需求 5: 相似度分析与重复预警

**用户故事:** 作为用户，我想要在购买新衣服前知道它是否与我已有的衣服重复，以便避免重复购买。

#### 验收标准

1. WHEN 用户上传待购买的 Garment 图片，THE Similarity_Analyzer SHALL 计算该 Garment 与 Wardrobe 中所有 Garment 的 Similarity_Score
2. THE Similarity_Analyzer SHALL 使用余弦相似度算法计算 Feature_Vector 之间的相似度
3. WHEN Similarity_Score 大于 0.8，THE Similarity_Analyzer SHALL 标记为高相似度
4. WHEN Similarity_Score 在 0.5 到 0.8 之间，THE Similarity_Analyzer SHALL 标记为中度相似度
5. WHEN Similarity_Score 小于 0.5，THE Similarity_Analyzer SHALL 标记为低相似度
6. WHEN 存在高相似度 Garment，THE System SHALL 显示重复预警提示
7. WHEN 存在相似 Garment，THE System SHALL 展示相似 Garment 的对比图
8. THE System SHALL 结合用户预算和 Style_Preference 提供购买决策建议

### 需求 6: 智能搭配推荐

**用户故事:** 作为用户，我想要获得基于我衣橱的搭配推荐，以便知道新衣服能和哪些已有单品搭配。

#### 验收标准

1. WHEN 用户上传待购买的 Garment 图片，THE Outfit_Recommender SHALL 生成搭配推荐方案
2. WHEN 待购买 Garment 为上衣类，THE Outfit_Recommender SHALL 推荐 Wardrobe 中的下装和鞋子
3. WHEN 待购买 Garment 为下装类，THE Outfit_Recommender SHALL 推荐 Wardrobe 中的上衣和鞋子
4. WHEN 待购买 Garment 为外套类，THE Outfit_Recommender SHALL 推荐 Wardrobe 中的上衣、下装和鞋子
5. THE Outfit_Recommender SHALL 应用颜色搭配规则（同色系/邻近色/互补色）
6. THE Outfit_Recommender SHALL 应用风格一致性规则
7. THE Outfit_Recommender SHALL 生成至少 3 套搭配方案
8. WHEN 生成搭配方案，THE System SHALL 以 Outfit_Card 形式展示推荐结果
9. THE Outfit_Card SHALL 包含 Garment 缩略图、推荐场合和搭配说明

### 需求 7: 适合度评分

**用户故事:** 作为用户，我想要知道一件衣服是否适合我的肤色、身材和风格，以便做出更好的购买决策。

#### 验收标准

1. WHEN 用户上传待购买的 Garment 图片，THE Suitability_Scorer SHALL 计算 Suitability_Score
2. THE Suitability_Scorer SHALL 基于 Skin_Tone 和 Garment 颜色计算颜色适合度分数（0-100）
3. THE Suitability_Scorer SHALL 基于 Body_Type 和 Garment 版型计算版型适合度分数（0-100）
4. THE Suitability_Scorer SHALL 基于 Style_Preference 和 Garment 风格计算风格适合度分数（0-100）
5. THE Suitability_Scorer SHALL 计算综合 Suitability_Score（颜色、版型、风格的加权平均）
6. THE Suitability_Scorer SHALL 提供文字说明解释评分理由
7. THE Suitability_Scorer SHALL 推荐适合的穿着场合（商务/正式/校园/休闲/约会/聚会等）
8. WHEN Suitability_Score 低于 60 分，THE Suitability_Scorer SHALL 提供款式或颜色修改建议
9. THE Suitability_Scorer SHALL 考虑用户不希望强化的身体部位信息

### 需求 8: 移动端应用

**用户故事:** 作为移动设备用户，我想要通过手机 APP 使用智能穿搭助手，以便随时随地获得穿搭建议。

#### 验收标准

1. THE Mobile_App SHALL 使用 Flutter 框架开发
2. THE Mobile_App SHALL 支持 iOS 平台
3. THE Mobile_App SHALL 支持 Android 平台
4. THE Mobile_App SHALL 提供相机拍照功能
5. THE Mobile_App SHALL 提供相册导入功能
6. THE Mobile_App SHALL 展示 Wardrobe 中的 Garment 列表
7. THE Mobile_App SHALL 展示 Outfit_Card 搭配推荐界面
8. THE Mobile_App SHALL 展示 Suitability_Score 和评分说明
9. THE Mobile_App SHALL 展示相似度对比界面
10. THE Mobile_App SHALL 通过 RESTful API 与 Backend_Service 通信

### 需求 9: 后端服务

**用户故事:** 作为系统架构师，我需要一个稳定的后端服务来处理业务逻辑和数据存储，以便支持多种客户端访问。

#### 验收标准

1. THE Backend_Service SHALL 使用 FastAPI 框架开发
2. THE Backend_Service SHALL 使用 Python 语言实现
3. THE Backend_Service SHALL 提供 RESTful API 接口
4. THE Backend_Service SHALL 实现用户认证与授权
5. THE Backend_Service SHALL 实现图像识别功能
6. THE Backend_Service SHALL 实现特征提取功能
7. THE Backend_Service SHALL 实现相似度计算功能
8. THE Backend_Service SHALL 实现搭配推荐逻辑
9. THE Backend_Service SHALL 实现适合度评分算法
10. THE Backend_Service SHALL 持久化存储用户数据和 Wardrobe 数据
11. WHEN API 请求失败，THE Backend_Service SHALL 返回标准化的错误响应

### 需求 10: 命令行工具

**用户故事:** 作为开发者，我想要使用命令行工具测试系统功能，以便快速验证和调试。

#### 验收标准

1. THE CLI_Tool SHALL 支持用户注册命令
2. THE CLI_Tool SHALL 支持用户登录命令
3. THE CLI_Tool SHALL 支持添加 Garment 到 Wardrobe 的命令
4. THE CLI_Tool SHALL 支持查看 Wardrobe 的命令
5. THE CLI_Tool SHALL 支持相似度分析命令
6. THE CLI_Tool SHALL 支持搭配推荐命令
7. THE CLI_Tool SHALL 支持适合度评分命令
8. THE CLI_Tool SHALL 接受图片文件路径作为输入参数
9. THE CLI_Tool SHALL 以结构化格式（JSON）输出结果
10. THE CLI_Tool SHALL 支持自动化脚本调用

### 需求 11: MCP 服务集成

**用户故事:** 作为 AI 智能体开发者，我想要通过 MCP 协议调用智能穿搭助手的功能，以便将其集成到其他 AI 系统中。

#### 验收标准

1. THE MCP_Service SHALL 实现 Model Context Protocol 标准接口
2. THE MCP_Service SHALL 暴露添加 Garment 到 Wardrobe 的工具接口
3. THE MCP_Service SHALL 暴露相似度分析的工具接口
4. THE MCP_Service SHALL 暴露搭配推荐的工具接口
5. THE MCP_Service SHALL 暴露适合度评分的工具接口
6. THE MCP_Service SHALL 支持 ChatGPT 等 AI 智能体调用
7. THE MCP_Service SHALL 返回标准化的 JSON 格式响应
8. THE MCP_Service SHALL 处理工具调用的认证与授权

### 需求 12: 轻量化图像识别模型

**用户故事:** 作为系统架构师，我需要使用轻量化的图像识别模型，以便在有限的计算资源下提供快速响应。

#### 验收标准

1. THE Image_Recognizer SHALL 使用 MobileNet 或类似轻量级 CNN 模型
2. THE Image_Recognizer SHALL 识别至少 6 种 Garment_Category（上衣/裤子/裙子/外套/鞋/包）
3. THE Image_Recognizer SHALL 识别 Garment 的主色
4. THE Image_Recognizer SHALL 识别 Garment 的风格标签
5. THE Feature_Extractor SHALL 提取固定维度的 Feature_Vector
6. WHEN 处理单张图片，THE Image_Recognizer SHALL 在 2 秒内完成识别
7. THE Image_Recognizer SHALL 支持批量图片处理
8. THE System SHALL 支持模型的离线部署

### 需求 13: 颜色识别与聚类

**用户故事:** 作为用户，我希望系统能够准确识别服饰的颜色，以便进行颜色搭配推荐和适合度评分。

#### 验收标准

1. WHEN 识别 Garment 图片，THE Image_Recognizer SHALL 提取主色信息
2. THE Image_Recognizer SHALL 使用颜色聚类算法识别主色
3. THE Image_Recognizer SHALL 将颜色映射到标准色系（红/橙/黄/绿/蓝/紫/黑/白/灰/棕等）
4. THE Image_Recognizer SHALL 提取颜色的 HSV 值
5. THE System SHALL 存储颜色的 RGB 和 HSV 值用于后续计算

### 需求 14: 数据持久化与隐私保护

**用户故事:** 作为用户，我希望我的数据能够安全存储，并且我的隐私得到保护。

#### 验收标准

1. THE System SHALL 持久化存储用户账号信息
2. THE System SHALL 持久化存储用户画像数据
3. THE System SHALL 持久化存储 Wardrobe 数据
4. THE System SHALL 持久化存储 Garment 图片
5. THE System SHALL 持久化存储 Feature_Vector
6. THE System SHALL 加密存储用户密码
7. THE System SHALL 加密传输敏感数据
8. THE System SHALL 仅允许用户访问自己的数据
9. WHEN 用户请求删除账号，THE System SHALL 删除该用户的所有数据

### 需求 15: API 文档与错误处理

**用户故事:** 作为开发者，我需要清晰的 API 文档和标准化的错误处理，以便快速集成和调试。

#### 验收标准

1. THE Backend_Service SHALL 提供 OpenAPI（Swagger）格式的 API 文档
2. THE Backend_Service SHALL 在根路径提供交互式 API 文档界面
3. WHEN API 请求参数无效，THE Backend_Service SHALL 返回 400 状态码和错误详情
4. WHEN API 请求未授权，THE Backend_Service SHALL 返回 401 状态码
5. WHEN API 请求的资源不存在，THE Backend_Service SHALL 返回 404 状态码
6. WHEN API 服务器内部错误，THE Backend_Service SHALL 返回 500 状态码和错误信息
7. THE Backend_Service SHALL 记录所有错误日志
8. THE Backend_Service SHALL 返回标准化的 JSON 错误响应格式

### 需求 16: 性能与可扩展性

**用户故事:** 作为系统管理员，我需要系统具有良好的性能和可扩展性，以便支持更多用户使用。

#### 验收标准

1. WHEN 处理单个 Garment 图片识别请求，THE System SHALL 在 3 秒内返回结果
2. WHEN 计算相似度，THE System SHALL 在 2 秒内完成与 Wardrobe 中所有 Garment 的对比
3. WHEN 生成搭配推荐，THE System SHALL 在 3 秒内返回推荐结果
4. THE Backend_Service SHALL 支持并发请求处理
5. THE System SHALL 支持水平扩展以增加处理能力
6. THE System SHALL 使用缓存机制优化重复请求的响应时间

