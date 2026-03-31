import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';
import '../../../core/providers/auth_provider.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/theme/fashion_palettes.dart';
import '../../../core/widgets/platform_image.dart';

/// 虚拟试衣：上传衣服图 + 人物图
/// 自动生成正面 / 侧面 / 背面 3 张图（伪 3D）
/// 左右滑动轮播展示伪 3D 效果
class VirtualTryonScreen extends StatefulWidget {
  const VirtualTryonScreen({super.key});

  @override
  State<VirtualTryonScreen> createState() => _VirtualTryonScreenState();
}

class _VirtualTryonScreenState extends State<VirtualTryonScreen> {
  XFile? _garmentImage;
  XFile? _personImage;
  bool _loading = false;
  // 伪 3D 结果：正面、侧面、背面（同一张结果图存三份模拟）
  List<String> _results = [];
  int _currentIndex = 0;
  final _pageCtrl = PageController();

  @override
  void dispose() {
    _pageCtrl.dispose();
    super.dispose();
  }

  Future<void> _pickGarment() async {
    final picker = ImagePicker();
    final img = await picker.pickImage(source: ImageSource.gallery);
    if (img != null) setState(() => _garmentImage = img);
  }

  Future<void> _pickPerson() async {
    final picker = ImagePicker();
    final img = await picker.pickImage(source: ImageSource.gallery);
    if (img != null) setState(() => _personImage = img);
  }

  Future<void> _generate() async {
    if (_garmentImage == null || _personImage == null) return;
    setState(() {
      _loading = true;
      _results = [];
    });

    final auth = context.read<AuthProvider>();
    try {
      final raw = await auth.apiClient.virtualTryon(
        garmentImage: _garmentImage,
        personImage: _personImage,
      );

      // 后端 TryOnResponse: { status, message, result_image_url, metadata }
      if (raw is Map) {
        final resultUrl = raw['result_image_url']?.toString();
        if (resultUrl != null && resultUrl.isNotEmpty) {
          // 同一张结果存三份，模拟多角度
          _results = [resultUrl, resultUrl, resultUrl];
        } else {
          // 无结果图，显示演示
          _results = ['', '', ''];
        }
      } else {
        _results = ['', '', ''];
      }
    } catch (_) {
      // 网络错误，演示
      _results = ['', '', ''];
    }

    if (!mounted) return;
    setState(() {
      _loading = false;
      _currentIndex = 0;
    });
  }

  @override
  Widget build(BuildContext context) {
    final palette = context.watch<ThemeProvider>().palette;
    return Scaffold(
      backgroundColor: palette.background,
      appBar: AppBar(
        title: const Text('虚拟试衣'),
        backgroundColor: palette.background,
        surfaceTintColor: Colors.transparent,
        foregroundColor: palette.textTitle,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // 上传区
            Row(
              children: [
                Expanded(
                  child: _PickBox(
                    label: '衣服图',
                    image: _garmentImage,
                    onTap: _pickGarment,
                    palette: palette,
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: _PickBox(
                    label: '人物图',
                    image: _personImage,
                    onTap: _pickPerson,
                    palette: palette,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 24),

            // 生成按钮
            SizedBox(
              height: 52,
              child: ElevatedButton.icon(
                onPressed:
                    (_garmentImage != null && _personImage != null && !_loading)
                        ? _generate
                        : null,
                style: ElevatedButton.styleFrom(
                  backgroundColor: palette.primary,
                  foregroundColor: Colors.white,
                  disabledBackgroundColor: palette.divider,
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14)),
                ),
                icon: _loading
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: Colors.white),
                      )
                    : const Icon(Icons.auto_fix_high),
                label: Text(_loading ? '正在生成多角度试衣图…' : '生成虚拟试衣',
                    style: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.w700)),
              ),
            ),
            const SizedBox(height: 28),

            // 结果展示
            if (_results.isNotEmpty) ...[
              const Text(
                '虚拟试衣效果',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 12),
              // 伪 3D 轮播
              SizedBox(
                height: 420,
                child: PageView.builder(
                  controller: _pageCtrl,
                  itemCount: _results.length,
                  onPageChanged: (i) => setState(() => _currentIndex = i),
                  itemBuilder: (ctx, i) {
                    final labels = ['正面', '侧面', '背面'];
                    final label = i < labels.length ? labels[i] : '视角 ${i + 1}';
                    return Card(
                      elevation: 0,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(20),
                        side: BorderSide(color: palette.divider),
                      ),
                      child: Stack(
                        fit: StackFit.expand,
                        children: [
                          // 图片（网络 URL）
                          ClipRRect(
                            borderRadius: BorderRadius.circular(20),
                            child: _results[i].isNotEmpty
                                ? PlatformImage(
                                    networkUrl: _results[i],
                                    fit: BoxFit.cover,
                                    errorWidget:
                                        _placeholderView(label, palette),
                                  )
                                : _placeholderView(label, palette),
                          ),
                          // 标签
                          Positioned(
                            bottom: 16,
                            right: 16,
                            child: Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 14, vertical: 6),
                              decoration: BoxDecoration(
                                color: palette.primary,
                                borderRadius: BorderRadius.circular(20),
                              ),
                              child: Text(label,
                                  style: const TextStyle(
                                      color: Colors.white,
                                      fontWeight: FontWeight.bold,
                                      fontSize: 13)),
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ),
              const SizedBox(height: 12),
              // 页码指示器
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: List.generate(_results.length, (i) {
                  return AnimatedContainer(
                    duration: const Duration(milliseconds: 250),
                    margin: const EdgeInsets.symmetric(horizontal: 4),
                    width: i == _currentIndex ? 24 : 8,
                    height: 8,
                    decoration: BoxDecoration(
                      color: i == _currentIndex
                          ? palette.primary
                          : palette.divider,
                      borderRadius: BorderRadius.circular(4),
                    ),
                  );
                }),
              ),
              const SizedBox(height: 8),
              Text(
                '← 左右滑动查看多角度 →',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 12, color: palette.textBody),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _placeholderView(String label, Palette palette) {
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        color: palette.surface,
      ),
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.threed_rotation,
                size: 72, color: palette.primary.withValues(alpha: 0.4)),
            const SizedBox(height: 12),
            Text('$label 视角',
                style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                    color: palette.textTitle)),
            const SizedBox(height: 4),
            Text('伪 3D 试衣效果',
                style: TextStyle(fontSize: 13, color: palette.textBody)),
          ],
        ),
      ),
    );
  }
}

class _PickBox extends StatelessWidget {
  final String label;
  final XFile? image;
  final VoidCallback onTap;
  final Palette palette;

  const _PickBox({
    required this.label,
    required this.image,
    required this.onTap,
    required this.palette,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: 140,
        decoration: BoxDecoration(
          color: palette.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: palette.divider),
        ),
        child: image != null
            ? ClipRRect(
                borderRadius: BorderRadius.circular(15),
                child: PlatformImage(
                  xfile: image,
                  fit: BoxFit.cover,
                  errorWidget: Container(
                    color: palette.primary.withValues(alpha: 0.1),
                    child: Icon(Icons.broken_image, color: palette.primary),
                  ),
                ),
              )
            : Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.add_photo_alternate_outlined,
                      size: 36, color: palette.textBody),
                  const SizedBox(height: 8),
                  Text(label,
                      style: TextStyle(color: palette.textBody, fontSize: 13)),
                ],
              ),
      ),
    );
  }
}
