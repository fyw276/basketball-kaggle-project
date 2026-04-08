# 📋 手动测试清单

## 测试准备

### 1. 启动后端服务
```bash
cd backend
python run.py
```

### 2. 访问 Swagger UI
```
http://127.0.0.1:8010/docs
```

### 3. 准备测试图片
准备以下品类的服饰图片各 2-3 张：
- 上衣（T恤、衬衫等）
- 裤子（牛仔裤、休闲裤等）
- 裙子
- 外套
- 鞋
- 包

---

## 测试流程

### ✅ 步骤 1: 注册并登录

1. 展开 `POST /api/v1/auth/register`
2. 点击 "Try it out"
3. 输入测试用户信息：
   ```json
   {
     "username": "manual_test_user",
     "email": "manual@test.com",
     "password": "Test123456"
   }
   ```
4. 点击 "Execute"
5. 确认返回 201 状态码

6. 展开 `POST /api/v1/auth/login`
7. 点击 "Try it out"
8. 输入登录信息：
   ```json
   {
     "username": "manual_test_user",
     "password": "Test123456"
   }
   ```
9. 点击 "Execute"
10. **复制返回的 access_token**

11. 点击页面右上角的 "Authorize" 🔓 按钮
12. **重要**: 在弹出框中**只输入 Token 本身**，不要包含 "Bearer" 前缀
    - ❌ 错误: `Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`
    - ✅ 正确: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`
13. 点击 "Authorize"，然后点击 "Close"
14. 确认右上角的锁图标变为 🔒（已授权状态）

---

### ✅ 步骤 2: 创建用户画像

1. 展开 `POST /api/v1/profile`
2. 点击 "Try it out"
3. 输入画像信息：
   ```json
   {
     "height": 170,
     "body_type": "矩形",
     "skin_tone": "冷白",
     "style_preference": ["通勤", "简约"],
     "budget_range": "中等",
     "avoid_body_parts": ["肩"]
   }
   ```
4. 点击 "Execute"
5. 确认返回 201 状态码

---

### 🧪 步骤 3: 测试图像识别

1. 展开 `POST /api/v1/recognition/analyze`
2. 点击 "Try it out"
3. 点击 "Choose File" 上传一张服饰图片
4. 点击 "Execute"
5. 检查返回结果：
   - ✅ category（品类）是否正确
   - ✅ main_color（主色）是否合理
   - ✅ secondary_colors（辅助色）是否合理
   - ✅ style_tags（风格标签）是否合理
   - ✅ feature_vector（特征向量）长度是否为 1280

**预期响应示例**：
```json
{
  "category": "上衣",
  "main_color": {
    "name": "蓝",
    "rgb": [52, 120, 180],
    "hex": "#3478B4"
  },
  "secondary_colors": [...],
  "style_tags": ["通勤", "简约"],
  "feature_vector": [0.123, 0.456, ...]
}
```

---

### 🧪 步骤 4: 添加服饰到衣橱

1. 展开 `POST /api/v1/wardrobe/garments`
2. 点击 "Try it out"
3. 上传第一张服饰图片（例如：上衣）
4. 点击 "Execute"
5. 确认返回 201 状态码
6. **记录返回的 garment_id**

7. 重复步骤 3-6，添加至少 3 件不同品类的服饰：
   - 1 件上衣
   - 1 件裤子或裙子
   - 1 件鞋

---

### 🧪 步骤 5: 查询衣橱

1. 展开 `GET /api/v1/wardrobe/garments`
2. 点击 "Try it out"
3. 点击 "Execute"
4. 检查返回结果：
   - ✅ 是否显示刚才添加的服饰
   - ✅ 每件服饰的信息是否完整

---

### 🧪 步骤 6: 测试相似度分析

1. 展开 `POST /api/v1/analysis/similarity`
2. 点击 "Try it out"
3. 上传一张与衣橱中某件服饰相似的图片
4. 点击 "Execute"
5. 检查返回结果：
   - ✅ 是否找到相似的服饰
   - ✅ 相似度评分是否合理（0-1）
   - ✅ 相似度等级（高/中/低）是否正确
   - ✅ 如果相似度 > 0.8，是否有重复预警

**预期响应示例**：
```json
{
  "target_garment": {
    "category": "上衣",
    "main_color": {...}
  },
  "similar_garments": [
    {
      "garment_id": "...",
      "similarity_score": 0.85,
      "similarity_level": "高",
      "category": "上衣"
    }
  ],
  "has_duplicate": true,
  "duplicate_warning": "发现高度相似的服饰..."
}
```

---

### 🧪 步骤 7: 测试搭配推荐

**前提条件**: 衣橱中至少有 3 件不同品类的服饰

1. 展开 `POST /api/v1/analysis/outfits`
2. 点击 "Try it out"
3. 上传一张服饰图片（例如：上衣）
4. 点击 "Execute"
5. 检查返回结果：
   - ✅ 是否返回至少 3 套搭配方案
   - ✅ 每套搭配是否包含多件服饰
   - ✅ 颜色和谐度评分是否合理
   - ✅ 风格一致性评分是否合理
   - ✅ 场合推荐是否合理

**预期响应示例**：
```json
{
  "outfits": [
    {
      "outfit_id": "...",
      "items": [
        {
          "garment_id": "...",
          "category": "上衣",
          "image_url": "..."
        },
        {
          "garment_id": "...",
          "category": "裤子",
          "image_url": "..."
        }
      ],
      "color_harmony_score": 0.85,
      "style_consistency_score": 0.90,
      "occasion": "通勤",
      "description": "简约通勤风格搭配"
    }
  ]
}
```

---

### 🧪 步骤 8: 测试适合度评分

**前提条件**: 已创建用户画像

1. 展开 `POST /api/v1/analysis/suitability`
2. 点击 "Try it out"
3. 上传一张服饰图片
4. 点击 "Execute"
5. 检查返回结果：
   - ✅ 综合评分（0-100）是否合理
   - ✅ 颜色适合度评分和说明
   - ✅ 版型适合度评分和说明
   - ✅ 风格适合度评分和说明
   - ✅ 场合推荐是否合理
   - ✅ 改进建议是否有用

**预期响应示例**：
```json
{
  "overall_score": 85,
  "color_score": 90,
  "color_explanation": "蓝色系非常适合冷白肤色",
  "fit_score": 80,
  "fit_explanation": "修身版型适合矩形体型",
  "style_score": 85,
  "style_explanation": "简约风格符合您的偏好",
  "recommended_occasions": ["通勤", "休闲"],
  "improvement_suggestions": [
    "可以搭配腰带强调腰线"
  ]
}
```

---

### 🧪 步骤 9: 测试服饰编辑和删除

1. 展开 `GET /api/v1/wardrobe/garments/{garment_id}`
2. 输入之前记录的 garment_id
3. 点击 "Execute"
4. 确认返回服饰详情

5. 展开 `PUT /api/v1/wardrobe/garments/{garment_id}`
6. 输入 garment_id
7. 修改服饰信息（例如添加标签）
8. 点击 "Execute"
9. 确认返回 200 状态码

10. 展开 `DELETE /api/v1/wardrobe/garments/{garment_id}`
11. 输入 garment_id
12. 点击 "Execute"
13. 确认返回 204 状态码

---

## 测试结果记录

### 图像识别功能
- [ ] 品类识别准确
- [ ] 颜色识别合理
- [ ] 风格识别合理
- [ ] 特征向量正确（1280 维）
- [ ] 响应时间 < 2 秒

### 衣橱管理功能
- [ ] 添加服饰成功
- [ ] 查询衣橱正常
- [ ] 编辑服饰成功
- [ ] 删除服饰成功

### 相似度分析功能
- [ ] 相似度计算准确
- [ ] 相似度分级正确
- [ ] 重复预警正常
- [ ] 响应时间 < 2 秒

### 搭配推荐功能
- [ ] 返回至少 3 套搭配
- [ ] 搭配方案合理
- [ ] 评分系统正常
- [ ] 场合推荐合理
- [ ] 响应时间 < 3 秒

### 适合度评分功能
- [ ] 综合评分合理
- [ ] 各维度评分准确
- [ ] 评分说明清晰
- [ ] 场合推荐合理
- [ ] 改进建议有用

---

## 常见问题

### Q1: 图像识别返回 500 错误
**解决方案**:
- 检查图片格式（支持 JPG、PNG）
- 检查图片大小（建议 < 5MB）
- 查看后端日志：`backend/logs/app.log`

### Q2: 相似度分析返回空结果
**解决方案**:
- 确保衣橱中至少有 1 件服饰
- 检查上传的图片是否为服饰图片

### Q3: 搭配推荐返回空结果
**解决方案**:
- 确保衣橱中至少有 3 件不同品类的服饰
- 尝试添加更多服饰到衣橱

### Q4: 适合度评分返回 404 错误
**解决方案**:
- 确保已创建用户画像
- 检查是否已登录（Token 是否有效）

---

## 测试完成后

如果所有测试都通过，恭喜！后端功能已完全验证。

**下一步**:
1. 记录测试结果
2. 报告任何发现的问题
3. 决定是否开始前端开发（Flutter 移动端、CLI 工具、MCP 服务）

---

**测试日期**: ___________
**测试人员**: ___________
**测试结果**: ⬜ 全部通过  ⬜ 部分通过  ⬜ 未通过
