# 📋 有效值快速参考

## 用户画像 (User Profile)

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

### 避免强化部位 (avoid_body_parts)
```
肩, 腰, 臀, 大腿, 小腿, 手臂, 胸部
```

---

## 服饰品类 (Garment Category)

```
上衣, 裤子, 裙子, 外套, 鞋, 包
```

---

## 标准色系 (Standard Colors)

```
红, 橙, 黄, 绿, 蓝, 紫, 黑, 白, 灰, 棕
```

---

## 完整示例

### 创建用户画像

```json
{
  "height": 170,
  "body_type": "矩形",
  "skin_tone": "冷白",
  "style_preference": ["通勤", "简约"],
  "budget_range": "中等",
  "avoid_body_parts": ["肩", "腰"]
}
```

### 更新用户画像

```json
{
  "height": 175,
  "budget_range": "高端",
  "style_preference": ["通勤", "简约", "正式"]
}
```

---

## 常见错误

### ❌ 错误示例

```json
{
  "body_type": "标准",          // ❌ 应该是: 矩形, 偏瘦, 微胖 等
  "skin_tone": "白色",          // ❌ 应该是: 冷白, 黄皮, 小麦, 深色
  "style_preference": ["商务"],  // ❌ 应该是: 通勤, 正式 等
  "budget_range": "低",         // ❌ 应该是: 经济, 中等, 高端
  "avoid_body_parts": ["肩部"]  // ❌ 应该是: 肩 (不含"部"字)
}
```

### ✅ 正确示例

```json
{
  "body_type": "矩形",
  "skin_tone": "冷白",
  "style_preference": ["通勤", "正式"],
  "budget_range": "中等",
  "avoid_body_parts": ["肩", "腰"]
}
```

---

## 验证规则

### 身高 (height)
- 类型: 整数
- 范围: 100-250 cm
- 示例: `170`

### 体型 (body_type)
- 类型: 字符串
- 必填
- 必须是有效值之一

### 肤色 (skin_tone)
- 类型: 字符串
- 必填
- 必须是有效值之一

### 风格偏好 (style_preference)
- 类型: 字符串数组
- 必填
- 至少包含 1 个值
- 每个值必须是有效值之一
- 示例: `["通勤", "简约"]`

### 预算范围 (budget_range)
- 类型: 字符串
- 必填
- 必须是有效值之一

### 避免强化部位 (avoid_body_parts)
- 类型: 字符串数组
- 可选（默认为空数组）
- 每个值必须是有效值之一
- 示例: `["肩", "腰"]` 或 `[]`

---

## 快速测试

### 最小有效 JSON

```json
{
  "height": 170,
  "body_type": "矩形",
  "skin_tone": "冷白",
  "style_preference": ["通勤"],
  "budget_range": "中等"
}
```

### 完整 JSON

```json
{
  "height": 170,
  "body_type": "矩形",
  "skin_tone": "冷白",
  "style_preference": ["通勤", "简约", "正式"],
  "budget_range": "中等",
  "avoid_body_parts": ["肩", "腰", "臀"]
}
```

---

**提示**: 如果遇到 400 Bad Request 错误，检查错误信息中提示的字段，确保使用的是有效值列表中的值。
