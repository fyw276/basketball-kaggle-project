# VowWear 参考项目试跑与周反馈

日期：2026-06-02
分支：`codex/project-closure-deliverables`
参考项目：`Pallavi-kr6/VowWear`

## 1. 老师建议的理解

老师给出的方向可以拆成三类参考：

| 项目 | 参考价值 | 对本项目的启发 |
| --- | --- | --- |
| VowWear | 产品形态与交互闭环 | 观察“用户输入偏好 -> AI 推荐 -> 卡片结果 -> 收藏/浏览”的完整流程 |
| VoxIris-AI | 实时多模态 | 参考图像、文本、对话等多模态输入如何组合成一个智能助手体验 |
| fashion-icon- | 内容生产 | 参考穿搭展示、风格文案、推荐理由、视觉内容生成方式 |

本周建议优先试跑 VowWear，因为它最接近“智能穿搭产品闭环”，能直接帮助本项目优化相似度分析、智能穿搭推荐和结果展示。

## 2. VowWear 本地试跑记录

### 2.1 获取代码

GitHub clone 首次受网络影响失败：

```text
fatal: unable to access 'https://github.com/Pallavi-kr6/VowWear.git/':
Failed to connect to github.com port 443
```

后改用 GitHub codeload zip 下载成功，并解压到：

```text
outputs/vowwear-reference/VowWear-main
```

同时成功读取 README，确认 VowWear 是面向婚礼/庆典场景的 AI 穿搭推荐平台。

### 2.2 技术栈

根据 `package.json` 和 README，VowWear 使用：

| 类型 | 技术 |
| --- | --- |
| 前端框架 | Next.js 16.2.4 |
| UI | React 19.2.4 |
| 样式 | Tailwind CSS 4 |
| 动画 | Framer Motion、Lenis |
| 认证和数据库 | Supabase |
| AI 推荐 | Groq |
| 商品搜索 | SerpAPI 或 Google Custom Search |

### 2.3 安装结果

执行：

```powershell
npm install
```

结果：

```text
added 376 packages
4 vulnerabilities: 3 moderate, 1 high
```

说明依赖可以正常安装，但存在 npm 安全审计风险，需要后续评估是否影响部署。

### 2.4 启动结果

执行：

```powershell
npm run dev -- --port 3006
```

结果：

```text
Next.js 16.2.4 (Turbopack)
Local: http://localhost:3006
Ready in 839ms
```

访问首页：

```text
GET / -> 200
```

说明 VowWear 首页可以本地启动和访问。

### 2.5 构建验证

执行：

```powershell
npm run build
```

结果：Next.js 编译和 TypeScript 检查通过，但生产构建在收集 `/api/recommendations/search` 页面数据时失败：

```text
Compiled successfully
Finished TypeScript
Error: The GROQ_API_KEY environment variable is missing or empty
Failed to collect page data for /api/recommendations/search
```

说明项目基础代码可以编译，但生产构建需要配置 `GROQ_API_KEY`，否则推荐接口会在构建阶段报错。

## 3. 可观测结果

| 路径 | 结果 | 说明 |
| --- | --- | --- |
| `/` | 200 | 首页可打开，展示 landing page、动画、功能说明和流程说明 |
| `/login` | 200 | 登录页可打开 |
| `/api/health` | 400 | 缺少 Supabase 环境变量 |
| `/dashboard` | 500 | Dashboard 依赖 Supabase 用户状态，缺少 Supabase URL/API key |
| `/api/recommendations/search` | 500 | 推荐接口依赖 `GROQ_API_KEY`，未配置时服务端报错 |
| `npm run build` | 失败 | 编译通过，但因缺少 `GROQ_API_KEY` 无法完成生产构建 |

关键错误信息：

```text
Missing Supabase credentials
The GROQ_API_KEY environment variable is missing or empty
@supabase/ssr: Your project's URL and API key are required
```

结论：VowWear 的前台展示页可以试跑；完整推荐闭环需要配置 Supabase、Groq、SerpAPI 或 Google Custom Search。

## 4. 对本项目的参考价值

### 4.1 产品闭环参考

VowWear 的推荐流程是：

```text
注册/登录 -> 填写风格偏好 -> 输入场景/预算/颜色 -> AI 推荐 -> 商品卡片 -> 收藏/浏览
```

本项目可以对应为：

```text
衣橱录入 -> 上传待购买衣服/整身 Look -> CLIP 相似度分析 -> 适合度评分 -> 购买建议/试衣候选
```

这说明本项目不需要只强调“能识别衣服”，更应该强调“帮用户完成购买决策”。

### 4.2 OmniParser + CLIP 的落点

老师提示的 “OmniParser + CLIP 可做图文穿搭相似度评分” 可以落到本项目已有模块：

| 能力 | 本项目已有位置 | 作用 |
| --- | --- | --- |
| Look 拆分 | `backend/app/services/look_parsers/omni_parser.py` | 从截图/穿搭图中切出服装区域 |
| CLIP 识别与向量 | `backend/app/services/look_clip_adapter.py` | 对每个服装区域提取品类、风格、颜色、特征向量 |
| 相似度评分 | `backend/app/services/look_similarity.py` | 将穿搭图中的部件与衣橱单品做相似度匹配 |
| 前端展示 | `mobile/lib/features/analysis/screens/similarity_screen.dart` | 展示整体相似度、部件匹配、缺失品类和试衣候选 |

因此后续可以把“图文穿搭相似度评分”包装成一个更清晰的演示点：

```text
上传穿搭图/商品截图 -> 自动拆分上装/下装/配饰 -> CLIP 向量匹配衣橱 -> 输出相似度、重复购买风险和可替代单品
```

### 4.3 内容生产参考

VowWear 的推荐卡片包含标题、图片、价格、来源、推荐理由等信息。
本项目可以增强结果页展示：

- 相似度分数：说明“像不像”。
- 重复购买风险：说明“要不要再买”。
- 风格标签：说明“适不适合当前风格”。
- 推荐理由：说明“为什么推荐/为什么谨慎购买”。
- 试衣候选：说明“可以直接进入虚拟试衣验证”。

## 5. 本周反馈可提交版本

本周我选择试跑 VowWear。VowWear 是一个基于 Next.js、Supabase 和 Groq 的 AI 婚礼穿搭推荐平台，产品流程包括用户登录、填写风格偏好、输入场景和预算、生成 AI 推荐、展示商品卡片和收藏结果。

本地试跑中，项目依赖安装成功，Next.js 开发服务成功启动，首页 `/` 和登录页 `/login` 都能正常访问。可观测结果包括：首页返回 200，登录页返回 200，`/api/health` 返回缺少 Supabase credentials，`/dashboard` 因缺少 Supabase URL/API key 返回 500，推荐接口 `/api/recommendations/search` 因缺少 `GROQ_API_KEY` 返回 500。`npm run build` 的编译和 TypeScript 检查通过，但最终也因缺少 `GROQ_API_KEY` 无法完成生产构建。因此，VowWear 的前台展示部分可以试跑，但完整 AI 推荐闭环需要配置 Supabase、Groq 和搜索 API。

对我的项目来说，VowWear 最大的参考价值是产品闭环：它不是单独展示 AI 能力，而是把“用户偏好输入 -> 推荐结果 -> 商品卡片 -> 收藏/浏览”做成连续体验。我的智能穿搭项目可以对应收束为“衣橱录入 -> 上传待购买衣服或整身 Look -> OmniParser/CLIP 图像理解 -> 相似度评分 -> 重复购买风险和购买建议”。老师提到的 OmniParser + CLIP 可以作为本项目的核心实验点：用 OmniParser 拆分穿搭图区域，用 CLIP 提取服装向量，再和衣橱单品做相似度匹配，最终输出可解释的穿搭相似度评分。

下周计划是把这次观察迁移到自己的相似度分析页面：强化整体分数、部件匹配、缺失品类、重复购买风险和试衣候选展示，让项目更像一个完整的购买决策助手，而不是单点识别 demo。
