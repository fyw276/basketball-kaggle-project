# 前端完整修复指南

## 问题根源

前端代码基于假设的 API 设计，但后端实际 API 结构不同。主要问题：

1. **衣橱管理**: 需要先调用识别 API，再用识别结果添加服饰
2. **分析功能**: 返回的数据结构字段名不匹配

## 快速修复方案

由于前端和后端 API 设计差异较大，建议采用以下方案之一：

### 方案 A: 修改后端 API（推荐）

在后端添加简化的 API 端点，自动处理图像识别：

```python
# backend/app/api/wardrobe.py

@router.post("/garments/upload", response_model=GarmentResponse)
async def upload_garment(
    file: UploadFile = File(...),
    notes: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload garment image with automatic recognition

    This endpoint:
    1. Recognizes the image
    2. Saves the image
    3. Creates the garment record
    """
    # Read image
    image_bytes = await file.read()

    # Recognize image
    recognizer = ImageRecognizer()
    result = recognizer.recognize(image_bytes)

    # Save image
    storage = get_storage_service()
    image_path, image_url = await storage.save_image(file, str(current_user.user_id))

    # Create garment
    garment_in = GarmentCreate(
        category=result.category,
        main_color=result.main_color,
        secondary_colors=result.secondary_colors,
        style_tags=result.style_tags,
        fit_type=result.fit_type,
        image_path=image_path,
        image_url=image_url,
        feature_vector=result.feature_vector,
        notes=notes,
    )

    garment = create_garment(db, current_user.user_id, garment_in)
    return garment
```

### 方案 B: 修改前端代码（当前方案）

修改前端以匹配现有后端 API。

## 详细修复步骤

### 1. 更新 API Client

添加识别 API 调用方法：

```dart
// mobile/lib/core/services/api_client.dart

// 添加识别 API
Future<Map<String, dynamic>> recognizeImage(String imagePath) async {
  final formData = FormData.fromMap({
    'file': await MultipartFile.fromFile(imagePath),
  });
  final response = await _dio.post('/recognition/analyze', data: formData);
  return response.data;
}
```

### 2. 修复衣橱管理

```dart
// mobile/lib/features/wardrobe/screens/wardrobe_screen.dart

Future<void> _addGarment() async {
  try {
    final XFile? image = await _imagePicker.pickImage(
      source: ImageSource.gallery,
      maxWidth: 1024,
      maxHeight: 1024,
    );

    if (image == null) return;

    setState(() => _isLoading = true);

    // 步骤 1: 识别图片
    final recognition = await _apiClient.recognizeImage(image.path);

    // 步骤 2: 准备表单数据
    final formData = FormData.fromMap({
      'file': await MultipartFile.fromFile(image.path),
      'category': recognition['category'],
      'main_color_name': recognition['main_color']['name'],
      'main_color_rgb': '${recognition['main_color']['rgb'][0]},${recognition['main_color']['rgb'][1]},${recognition['main_color']['rgb'][2]}',
      'main_color_hsv': '${recognition['main_color']['hsv'][0]},${recognition['main_color']['hsv'][1]},${recognition['main_color']['hsv'][2]}',
      'main_color_hex': recognition['main_color']['hex_code'],
      'style_tags': (recognition['style_tags'] as List).join(','),
      'fit_type': recognition['fit_type'],
    });

    // 步骤 3: 添加服饰
    await _apiClient.dio.post('/wardrobe/garments', data: formData);

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('添加成功！'),
          backgroundColor: Colors.green,
        ),
      );
      _loadGarments();
    }
  } catch (e) {
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('添加失败: $e'),
          backgroundColor: Colors.red,
        ),
      );
      setState(() => _isLoading = false);
    }
  }
}
```

### 3. 修复获取服饰列表

```dart
Future<void> _loadGarments() async {
  setState(() => _isLoading = true);

  try {
    final response = await _apiClient.dio.get(
      '/wardrobe/garments',
      queryParameters: {
        'page': 1,
        'page_size': 100,
        if (_selectedCategory != null && _selectedCategory != '全部')
          'category': _selectedCategory,
      },
    );

    if (mounted) {
      setState(() => _garments = response.data['items']);
    }
  } catch (e) {
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('加载失败: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  } finally {
    if (mounted) {
      setState(() => _isLoading = false);
    }
  }
}
```

### 4. 修复相似度分析

```dart
// mobile/lib/features/analysis/screens/similarity_screen.dart

Future<void> _analyzeSimilarity() async {
  if (_selectedImage == null) return;

  setState(() => _isAnalyzing = true);

  try {
    final formData = FormData.fromMap({
      'file': await MultipartFile.fromFile(_selectedImage!.path),
    });

    final response = await _apiClient.dio.post(
      '/analysis/similarity',
      data: formData,
    );

    if (mounted) {
      setState(() => _analysisResult = response.data);
    }
  } catch (e) {
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('分析失败: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  } finally {
    if (mounted) {
      setState(() => _isAnalyzing = false);
    }
  }
}

// 显示结果时使用正确的字段名
Widget _buildResults() {
  return Column(
    children: [
      // 目标服饰信息
      _buildInfoRow('品类', _analysisResult!['target_garment']['category']),
      _buildInfoRow('颜色', _analysisResult!['target_garment']['main_color']['name']),

      // 相似服饰列表
      if (_analysisResult!['similar_garments'] != null)
        ...(_analysisResult!['similar_garments'] as List).map((garment) {
          return ListTile(
            title: Text(garment['category']),
            subtitle: Text('相似度: ${(garment['similarity_score'] * 100).toInt()}%'),
            trailing: Text(garment['similarity_level']),
          );
        }).toList(),

      // 推荐信息
      Text(_analysisResult!['recommendation']),
    ],
  );
}
```

### 5. 修复搭配推荐

```dart
// mobile/lib/features/analysis/screens/outfit_screen.dart

Future<void> _generateOutfits() async {
  if (_selectedImage == null) return;

  setState(() => _isGenerating = true);

  try {
    final formData = FormData.fromMap({
      'file': await MultipartFile.fromFile(_selectedImage!.path),
    });

    final response = await _apiClient.dio.post(
      '/analysis/outfits',
      data: formData,
      queryParameters: {'num_outfits': _numOutfits},
    );

    if (mounted) {
      setState(() => _recommendationResult = response.data);
    }
  } catch (e) {
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('生成失败: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  } finally {
    if (mounted) {
      setState(() => _isGenerating = false);
    }
  }
}

// 显示结果
Widget _buildOutfitCard(int index, dynamic outfit) {
  return Card(
    child: Column(
      children: [
        Text('方案 $index'),
        Text('评分: ${(outfit['overall_score'] * 100).toInt()}'),
        Text('场合: ${outfit['occasion']}'),
        Text('描述: ${outfit['description']}'),

        // 搭配单品
        if (outfit['items'] != null)
          ...(outfit['items'] as List).map((item) {
            return ListTile(
              leading: Image.network(item['image_url']),
              title: Text(item['category']),
            );
          }).toList(),
      ],
    ),
  );
}
```

### 6. 修复适合度评分

```dart
// mobile/lib/features/analysis/screens/suitability_screen.dart

Future<void> _analyzeSuitability() async {
  if (_selectedImage == null) return;

  setState(() => _isAnalyzing = true);

  try {
    final formData = FormData.fromMap({
      'file': await MultipartFile.fromFile(_selectedImage!.path),
    });

    final response = await _apiClient.dio.post(
      '/analysis/suitability',
      data: formData,
    );

    if (mounted) {
      setState(() => _analysisResult = response.data);
    }
  } catch (e) {
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('分析失败: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  } finally {
    if (mounted) {
      setState(() => _isAnalyzing = false);
    }
  }
}

// 显示结果
Widget _buildResults() {
  return Column(
    children: [
      // 总体评分
      Text('${_analysisResult!['suitability_score']}分'),

      // 详细评分
      _buildScoreItem('颜色匹配', _analysisResult!['color_score'] / 100),
      _buildScoreItem('版型适配', _analysisResult!['fit_score'] / 100),
      _buildScoreItem('风格匹配', _analysisResult!['style_score'] / 100),

      // 说明
      Text(_analysisResult!['explanation']['color']),
      Text(_analysisResult!['explanation']['fit']),
      Text(_analysisResult!['explanation']['style']),

      // 建议
      if (_analysisResult!['suggestions'] != null)
        ...(_analysisResult!['suggestions'] as List).map((suggestion) {
          return Text('• $suggestion');
        }).toList(),
    ],
  );
}
```

## 测试清单

### 1. 用户画像
- [ ] 创建画像成功
- [ ] 编辑画像成功
- [ ] 所有字段正确保存

### 2. 衣橱管理
- [ ] 添加服饰成功（自动识别）
- [ ] 查看服饰列表
- [ ] 按品类筛选
- [ ] 删除服饰成功

### 3. 相似度分析
- [ ] 上传图片成功
- [ ] 显示识别信息
- [ ] 显示相似服饰列表
- [ ] 显示推荐信息

### 4. 搭配推荐
- [ ] 上传图片成功
- [ ] 生成搭配方案
- [ ] 显示评分和理由
- [ ] 显示搭配单品

### 5. 适合度评分
- [ ] 上传图片成功
- [ ] 显示总体评分
- [ ] 显示详细评分
- [ ] 显示建议

## 注意事项

1. **图片路径**: Flutter Web 不支持 `dart:io` 的 `File`，需要使用 `XFile`
2. **CORS**: 确保后端 CORS 配置正确
3. **错误处理**: 添加详细的错误提示
4. **加载状态**: 显示加载指示器
5. **数据验证**: 检查 API 返回的数据结构

## 推荐方案

由于修改量较大，建议：

1. **短期方案**: 在后端添加简化的 API 端点（方案 A）
2. **长期方案**: 重构前端以完全匹配后端 API（方案 B）

当前我会实现方案 B，修改前端代码以匹配后端 API。
