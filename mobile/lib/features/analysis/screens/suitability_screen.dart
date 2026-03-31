import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'dart:typed_data';
import 'package:provider/provider.dart';
import '../../../core/services/api_client.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/theme/style_tokens.dart';
import '../../../core/theme/theme_model.dart';
import '../../../core/widgets/themed_page.dart';

class SuitabilityScreen extends StatefulWidget {
  const SuitabilityScreen({super.key});

  @override
  State<SuitabilityScreen> createState() => _SuitabilityScreenState();
}

class _SuitabilityScreenState extends State<SuitabilityScreen> {
  final _apiClient = ApiClient();
  final _imagePicker = ImagePicker();

  XFile? _selectedImage;
  bool _isAnalyzing = false;
  Map<String, dynamic>? _analysisResult;

  Future<void> _pickImage() async {
    try {
      final XFile? image = await _imagePicker.pickImage(
        source: ImageSource.gallery,
        maxWidth: 1024,
        maxHeight: 1024,
      );

      if (image == null) return;

      setState(() {
        _selectedImage = image;
        _analysisResult = null;
      });
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('选择图片失败: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  Future<void> _analyzeSuitability() async {
    if (_selectedImage == null) return;

    setState(() => _isAnalyzing = true);

    try {
      final result =
          await _apiClient.analyzeSuitabilityFromXFile(_selectedImage!);

      if (mounted) {
        setState(() => _analysisResult = result);
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

  @override
  Widget build(BuildContext context) {
    final tokens = StyleTokens.fromStyle(context.watch<ThemeProvider>().style);

    return ThemedPage(
      appBar: AppBar(
          title:
              Text('适合度评分', style: tokens.titleStyle.copyWith(fontSize: 18))),
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // 说明文字
            Container(
              padding: const EdgeInsets.all(16.0),
              decoration: BoxDecoration(
                color: tokens.surface
                    .withOpacity(tokens.style == UserGender.male ? 0.78 : 0.70),
                borderRadius: BorderRadius.circular(tokens.cardRadius),
                border: Border.all(color: tokens.border.withOpacity(0.85)),
                boxShadow: tokens.cardShadow(),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.info_outline, color: tokens.accent),
                      const SizedBox(width: 8),
                      Text('功能说明',
                          style: tokens.titleStyle.copyWith(fontSize: 16)),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '上传一张服饰图片，系统会根据您的个人画像（体型、肤色、风格偏好等），评估这件服饰是否适合您。',
                    style: tokens.bodyStyle,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),

            // 选择图片按钮
            OutlinedButton.icon(
              onPressed: _pickImage,
              icon: const Icon(Icons.image),
              label: const Text('选择服饰图片'),
              style: OutlinedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 16),
              ),
            ),
            const SizedBox(height: 16),

            // 显示选中的图片
            if (_selectedImage != null) ...[
              Card(
                clipBehavior: Clip.antiAlias,
                child: FutureBuilder<Uint8List>(
                  future: _selectedImage!.readAsBytes(),
                  builder: (context, snapshot) {
                    if (snapshot.hasData) {
                      return Image.memory(
                        snapshot.data!,
                        height: 300,
                        fit: BoxFit.cover,
                      );
                    }
                    return const SizedBox(
                      height: 300,
                      child: Center(child: CircularProgressIndicator()),
                    );
                  },
                ),
              ),
              const SizedBox(height: 16),

              // 分析按钮
              ElevatedButton(
                onPressed: _isAnalyzing ? null : _analyzeSuitability,
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                ),
                child: _isAnalyzing
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text(
                        '开始评分',
                        style: TextStyle(fontSize: 16),
                      ),
              ),
            ],

            // 分析结果
            if (_analysisResult != null) ...[
              const SizedBox(height: 24),

              // 总体评分
              Card(
                color: _getScoreBackgroundColor(
                    (_analysisResult!['suitability_score'] ?? 0) / 100.0),
                child: Padding(
                  padding: const EdgeInsets.all(24.0),
                  child: Column(
                    children: [
                      const Text(
                        '适合度评分',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                        ),
                      ),
                      const SizedBox(height: 16),
                      Text(
                        (_analysisResult!['suitability_score'] ?? 0).toString(),
                        style: const TextStyle(
                          fontSize: 64,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                        ),
                      ),
                      const Text(
                        '分',
                        style: TextStyle(
                          fontSize: 24,
                          color: Colors.white,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        _getScoreLabel(
                            (_analysisResult!['suitability_score'] ?? 0) /
                                100.0),
                        style: const TextStyle(
                          fontSize: 16,
                          color: Colors.white,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // 服饰信息
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        '服饰信息',
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 12),
                      _buildInfoRow(
                          '品类', _analysisResult!['garment']?['category']),
                      _buildInfoRow(
                          '颜色', _analysisResult!['garment']?['color']),
                      _buildInfoRow(
                          '风格', _analysisResult!['garment']?['style']),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // 详细评分
              const Text(
                '详细评分',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 8),

              _buildScoreItem(
                '风格匹配',
                (_analysisResult!['style_score'] ?? 0) / 100.0,
                Icons.style,
              ),
              _buildScoreItem(
                '颜色匹配',
                (_analysisResult!['color_score'] ?? 0) / 100.0,
                Icons.palette,
              ),
              _buildScoreItem(
                '体型适配',
                (_analysisResult!['fit_score'] ?? 0) / 100.0,
                Icons.accessibility,
              ),

              const SizedBox(height: 16),

              // 建议
              if (_analysisResult!['suggestions'] != null &&
                  (_analysisResult!['suggestions'] as List).isNotEmpty) ...[
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16.0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Icon(Icons.lightbulb_outline,
                                color: Colors.amber[700]),
                            const SizedBox(width: 8),
                            const Text(
                              '穿搭建议',
                              style: TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        ...(_analysisResult!['suggestions'] as List)
                            .map((suggestion) {
                          return Padding(
                            padding: const EdgeInsets.only(bottom: 8),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text('• ',
                                    style: TextStyle(fontSize: 16)),
                                Expanded(
                                  child: Text(
                                    suggestion.toString(),
                                    style: const TextStyle(fontSize: 14),
                                  ),
                                ),
                              ],
                            ),
                          );
                        }).toList(),
                      ],
                    ),
                  ),
                ),
              ],
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildInfoRow(String label, dynamic value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          SizedBox(
            width: 60,
            child: Text(
              '$label:',
              style: TextStyle(
                color: Colors.grey[600],
                fontSize: 14,
              ),
            ),
          ),
          Text(
            value?.toString() ?? '未知',
            style: const TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildScoreItem(String label, double? score, IconData icon) {
    final scoreValue = score ?? 0.0;
    final percentage = (scoreValue * 100).toInt();

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 20, color: Colors.blue[700]),
                const SizedBox(width: 8),
                Text(
                  label,
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const Spacer(),
                Text(
                  '$percentage分',
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.bold,
                    color: _getScoreColor(scoreValue),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            LinearProgressIndicator(
              value: scoreValue,
              backgroundColor: Colors.grey[300],
              valueColor: AlwaysStoppedAnimation<Color>(
                _getScoreColor(scoreValue),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Color _getScoreColor(double score) {
    if (score >= 0.8) return Colors.green;
    if (score >= 0.6) return Colors.orange;
    return Colors.red;
  }

  Color _getScoreBackgroundColor(double? score) {
    if (score == null) return Colors.grey;
    if (score >= 0.8) return Colors.green;
    if (score >= 0.6) return Colors.orange;
    return Colors.red;
  }

  String _getScoreLabel(double? score) {
    if (score == null) return '未知';
    if (score >= 0.9) return '非常适合';
    if (score >= 0.8) return '很适合';
    if (score >= 0.7) return '比较适合';
    if (score >= 0.6) return '一般';
    return '不太适合';
  }
}
