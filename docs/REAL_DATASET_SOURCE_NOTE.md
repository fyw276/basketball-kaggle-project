# 真实数据集来源说明

本项目的 20 条购买建议测试数据改为基于公开真实商品数据集整理，文件为：

- `data/purchase_recommendation_test_data.csv`

## 数据来源

商品 id、商品名称、类别、颜色、风格等字段参考公开数据集：

- Hugging Face: `Transformersx/fashion-product-images-small`
- 原始来源说明指向 Kaggle: `Fashion Product Images / Fashion Product Images Small`

该数据集包含真实电商商品图片与商品元数据，常见字段包括：

- `id`
- `gender`
- `masterCategory`
- `subCategory`
- `articleType`
- `baseColour`
- `season`
- `usage`
- `productDisplayName`
- `image`

## 字段可信度说明

CSV 中以下字段来自公开商品数据集或按其字段翻译整理：

- `source_product_id`
- `真实商品名称`
- `类别`
- `颜色`
- `风格`
- `图片名称`

CSV 中以下字段不是原始数据集直接提供，而是为了项目闭环测试按规则派生：

- `适用场景`
- `是否推荐购买`
- `推荐理由`

因此报告中建议表述为：

> 本项目使用公开服装商品数据集中的真实商品图片与元数据作为测试基础，并基于项目定义的推荐规则补充适用场景、购买建议和推荐理由字段，用于验证从商品识别到购买建议生成的完整闭环。

不要表述为“真实用户购买偏好数据”或“真实用户行为数据”，因为当前数据不包含真实用户画像、点击、收藏、购买等行为记录。
