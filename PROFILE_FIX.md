# 用户画像 422 错误修复

## 问题原因

前端发送的数据格式与后端 API 期望的格式不匹配，导致 422 验证错误。

## 字段差异

### 后端 API 要求的字段

```json
{
  "height": 175,                    // 必填，整数，100-250
  "body_type": "偏瘦",              // 必填，枚举值
  "skin_tone": "冷白",              // 必填，枚举值
  "style_preference": ["通勤", "简约"],  // 必填，数组，至少1个
  "budget_range": "中等",           // 必填，枚举值
  "avoid_body_parts": ["肩", "腰"]  // 可选，数组
}
```

### 前端之前发送的字段（错误）

```json
{
  "height": 175,
  "weight": 70,                     // ❌ 后端不支持
  "gender": "男",                   // ❌ 后端不支持
  "body_type": "标准",              // ❌ 枚举值不匹配
  "skin_tone": "自然",              // ❌ 枚举值不匹配
  "style_preferences": ["休闲"],    // ❌ 字段名错误（应该是单数）
  "color_preferences": ["黑色"]     // ❌ 后端不支持
}
```

## 修复内容

### 1. 字段名修正

- `style_preferences` → `style_preference` (单数)
- 移除 `weight`, `gender`, `color_preferences`
- 添加 `budget_range` (必填)
- 添加 `avoid_body_parts` (可选)

### 2. 枚举值修正

**体型 (body_type)**:
- ❌ 旧值: `瘦`, `标准`, `微胖`, `胖`, `健壮`
- ✅ 新值: `偏瘦`, `微胖`, `梨形`, `倒三角`, `沙漏`, `矩形`

**肤色 (skin_tone)**:
- ❌ 旧值: `白皙`, `自然`, `小麦色`, `深色`
- ✅ 新值: `冷白`, `黄皮`, `小麦`, `深色`

**风格偏好 (style_preference)**:
- ✅ 有效值: `通勤`, `学院`, `甜酷`, `简约`, `街头`, `复古`, `休闲`, `正式`, `运动`, `度假`

**预算范围 (budget_range)** - 新增必填字段:
- ✅ 有效值: `经济`, `中等`, `高端`

**避免强调的身体部位 (avoid_body_parts)** - 新增可选字段:
- ✅ 有效值: `肩`, `腰`, `臀`, `大腿`, `小腿`, `手臂`, `胸部`

## 测试步骤

### 1. 重启 Flutter Web

在 Flutter 终端按 `R` 键进行热重启，或重新运行：
```bash
flutter run -d chrome
```

### 2. 填写用户画像

1. 点击主页"用户画像"卡片
2. 填写信息：
   - 身高: `175` cm
   - 体型: `偏瘦` 或 `标准` → 选择 `矩形`
   - 肤色: `冷白` 或 `黄皮`
   - 预算范围: `中等`
   - 风格偏好: 至少选择一个（如 `休闲`, `简约`）
   - 避免强调的身体部位: 可选（如 `肩`, `腰`）
3. 点击"保存"

### 3. 验证成功

- ✅ 看到"保存成功！"提示
- ✅ 自动返回主页
- ✅ 可以再次进入查看已保存的画像

## 完整的有效值列表

### 体型 (body_type)
```
偏瘦, 微胖, 梨形, 倒三角, 沙漏, 矩形
```

### 肤色 (skin_tone)
```
冷白, 黄皮, 小麦, 深色
```

### 风格偏好 (style_preference)
```
通勤, 学院, 甜酷, 简约, 街头, 复古, 休闲, 正式, 运动, 度假
```

### 预算范围 (budget_range)
```
经济, 中等, 高端
```

### 避免强调的身体部位 (avoid_body_parts)
```
肩, 腰, 臀, 大腿, 小腿, 手臂, 胸部
```

## API 请求示例

### 创建用户画像

```bash
POST /api/v1/profile
Authorization: Bearer <token>
Content-Type: application/json

{
  "height": 175,
  "body_type": "矩形",
  "skin_tone": "黄皮",
  "style_preference": ["休闲", "简约"],
  "budget_range": "中等",
  "avoid_body_parts": ["肩"]
}
```

### 更新用户画像

```bash
PUT /api/v1/profile
Authorization: Bearer <token>
Content-Type: application/json

{
  "height": 180,
  "body_type": "倒三角",
  "skin_tone": "小麦",
  "style_preference": ["运动", "街头"],
  "budget_range": "高端",
  "avoid_body_parts": []
}
```

## 常见错误

### 错误 1: 422 - 体型值无效

```json
{
  "detail": "Invalid body_type. Must be one of: 偏瘦, 微胖, 梨形, 倒三角, 沙漏, 矩形"
}
```

**解决**: 使用下拉菜单选择，不要手动输入

### 错误 2: 422 - 风格偏好为空

```json
{
  "detail": "style_preference must have at least 1 item"
}
```

**解决**: 至少选择一个风格偏好

### 错误 3: 422 - 缺少必填字段

```json
{
  "detail": "field required"
}
```

**解决**: 确保填写所有必填字段（身高、体型、肤色、风格偏好、预算范围）

## 修改的文件

- `mobile/lib/features/profile/screens/profile_form_screen.dart`

## 主要改动

1. 移除了 `weight`, `gender`, `color_preferences` 字段
2. 添加了 `budget_range` 必填字段
3. 添加了 `avoid_body_parts` 可选字段
4. 更新了所有枚举值以匹配后端要求
5. 字段名从 `style_preferences` 改为 `style_preference`
6. 添加了风格偏好至少选择一个的验证
7. 添加了说明卡片提示用户

## 下一步

修复完成后，可以继续测试其他功能：
1. ✅ 用户画像创建/编辑
2. ⏭️ 衣橱管理
3. ⏭️ 相似度分析
4. ⏭️ 搭配推荐
5. ⏭️ 适合度评分
