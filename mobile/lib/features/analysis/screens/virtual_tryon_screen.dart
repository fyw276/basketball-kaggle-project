import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';
import '../../../core/providers/auth_provider.dart';
import '../../../core/services/feature_local_store.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/theme/fashion_palettes.dart';
import '../../../core/utils/app_snackbar.dart';
import '../../../core/utils/media_url.dart';
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
  // 人物多视角：正面必填，侧面/背面可选
  XFile? _personFront;
  XFile? _personSide;
  XFile? _personBack;
  bool _loading = false;
  bool _usedFallback = false;
  // 伪 3D 结果：正面、侧面、背面
  List<String> _results = [];
  int _currentIndex = 0;
  final _pageCtrl = PageController();
  final _aspectRatioCache = <String, double>{};

  static const _cacheKey = 'virtual_tryon';

  @override
  void initState() {
    super.initState();
    FeatureLocalStore.loadJson(_cacheKey).then((m) {
      if (m == null || !mounted) return;
      final list = m['results'];
      if (list is List && list.isNotEmpty) {
        setState(() {
          _results = list.map((e) => e.toString()).toList();
        });
      }
    });
  }

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
    if (img != null) setState(() => _personFront = img);
  }

  Future<void> _pickPersonSide() async {
    final picker = ImagePicker();
    final img = await picker.pickImage(source: ImageSource.gallery);
    if (img != null) setState(() => _personSide = img);
  }

  Future<void> _pickPersonBack() async {
    final picker = ImagePicker();
    final img = await picker.pickImage(source: ImageSource.gallery);
    if (img != null) setState(() => _personBack = img);
  }

  Future<void> _generate() async {
    if (_garmentImage == null || _personFront == null) return;
    // 新生成时清空旧结果与本地缓存，避免“看起来没对应/还是旧图”的错觉
    FeatureLocalStore.saveJson(_cacheKey, {'results': []});
    setState(() {
      _loading = true;
      _results = [];
      _usedFallback = false;
    });

    final auth = context.read<AuthProvider>();
    final base = auth.apiClient.baseUrl;
    try {
      // 3 次请求：front / side / back（若用户提供对应人物照则绑定，否则复用正面照）
      final views = <({String view, String label, XFile? person})>[
        (view: 'front view', label: '正面', person: _personFront),
        (view: 'side view', label: '侧面', person: _personSide ?? _personFront),
        (view: 'back view', label: '背面', person: _personBack ?? _personFront),
      ];

      final urls = <String>[];
      for (final v in views) {
        final raw = await auth.apiClient.virtualTryon(
          garmentImage: _garmentImage,
          personImage: v.person,
          prompt: v.view,
        );
        final map = Map<String, dynamic>.from(raw as Map<dynamic, dynamic>);
        if (map['error'] != null) {
          if (mounted) {
            showAppSnackBar(
              context,
              '试衣服务暂不可用：${userFacingApiError(map['error'])}',
            );
          }
          setState(() {
            _loading = false;
          });
          return;
        }

        final status = map['status']?.toString();
        if (status == 'fallback') {
          _usedFallback = true;
        }

        final resultUrl = map['result_image_url']?.toString();
        final resolved = resolveGarmentImageUrl(resultUrl, base);
        urls.add(resolved ?? '');
      }

      _results = urls;
    } catch (e) {
      if (mounted) {
        showAppSnackBar(context, '请求失败：${userFacingApiError(e)}');
      }
    }

    if (!mounted) return;
    setState(() {
      _loading = false;
      _currentIndex = 0;
    });
    if (_usedFallback && mounted) {
      showAppSnackBar(
        context,
        '当前为“简化合成模式”（模型未加载成功），效果会像叠图。请先下载/配置 try-on 模型后重试。',
      );
    }
    if (_results.isNotEmpty) {
      FeatureLocalStore.saveJson(_cacheKey, {'results': _results});
    }
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
                    onClear: () => setState(() => _garmentImage = null),
                    palette: palette,
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: _PickBox(
                    label: '正面照（必填）',
                    image: _personFront,
                    onTap: _pickPerson,
                    onClear: () => setState(() => _personFront = null),
                    palette: palette,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: _PickBox(
                    label: '侧面照（可选）',
                    image: _personSide,
                    onTap: _pickPersonSide,
                    onClear: () => setState(() => _personSide = null),
                    palette: palette,
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: _PickBox(
                    label: '背面照（可选）',
                    image: _personBack,
                    onTap: _pickPersonBack,
                    onClear: () => setState(() => _personBack = null),
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
                    (_garmentImage != null && _personFront != null && !_loading)
                        ? _generate
                        : null,
                style: ElevatedButton.styleFrom(
                  backgroundColor: palette.primary,
                  foregroundColor: Colors.white,
                  disabledBackgroundColor: palette.divider,
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(26)),
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
              _TryOnCarousel(
                urls: _results,
                palette: palette,
                pageController: _pageCtrl,
                currentIndex: _currentIndex,
                onIndexChanged: (i) => setState(() => _currentIndex = i),
                aspectRatioCache: _aspectRatioCache,
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

  // (placeholder moved into _TryOnCarousel for better layout control)
}

class _PickBox extends StatelessWidget {
  final String label;
  final XFile? image;
  final VoidCallback onTap;
  final VoidCallback? onClear;
  final Palette palette;

  const _PickBox({
    required this.label,
    required this.image,
    required this.onTap,
    required this.onClear,
    required this.palette,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Stack(
        children: [
          Container(
            height: 120,
            decoration: BoxDecoration(
              color: palette.surface,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: palette.divider),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.04),
                  blurRadius: 14,
                  offset: const Offset(0, 6),
                ),
              ],
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
                          size: 32, color: palette.textBody),
                      const SizedBox(height: 8),
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 8),
                        child: Text(
                          label,
                          textAlign: TextAlign.center,
                          style: TextStyle(
                              color: palette.textBody,
                              fontSize: 12,
                              height: 1.2),
                        ),
                      ),
                    ],
                  ),
          ),
          if (image != null && onClear != null)
            Positioned(
              top: 6,
              right: 6,
              child: GestureDetector(
                onTap: onClear,
                child: Container(
                  padding: const EdgeInsets.all(6),
                  decoration: BoxDecoration(
                    color: Colors.black.withValues(alpha: 0.55),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(Icons.close, size: 16, color: Colors.white),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _TryOnCarousel extends StatelessWidget {
  final List<String> urls;
  final Palette palette;
  final PageController pageController;
  final int currentIndex;
  final ValueChanged<int> onIndexChanged;
  final Map<String, double> aspectRatioCache;

  const _TryOnCarousel({
    required this.urls,
    required this.palette,
    required this.pageController,
    required this.currentIndex,
    required this.onIndexChanged,
    required this.aspectRatioCache,
  });

  static const _labels = ['正面', '侧面', '背面'];

  @override
  Widget build(BuildContext context) {
    final angleLabel = currentIndex < _labels.length
        ? _labels[currentIndex]
        : '视角 ${currentIndex + 1}';
    final url = currentIndex < urls.length ? urls[currentIndex] : '';
    final ratio = (url.isNotEmpty ? aspectRatioCache[url] : null) ?? (3 / 4);
    final placeholder = _placeholder(angleLabel);

    return GestureDetector(
      onTap: () {
        if (urls.isEmpty) return;
        Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => _TryOnFullscreenGallery(
              urls: urls,
              initialIndex: currentIndex,
              palette: palette,
              aspectRatioCache: aspectRatioCache,
            ),
          ),
        );
      },
      child: Center(
        child: AspectRatio(
          aspectRatio: ratio,
          child: Card(
            elevation: 0,
            margin: EdgeInsets.zero,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(20),
              side: BorderSide(color: palette.divider),
            ),
            child: Stack(
              fit: StackFit.expand,
              children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(20),
                  child: _TryOnNetworkImage(
                    url: url,
                    fit: BoxFit.contain,
                    palette: palette,
                    onAspectRatio: (r) {
                      if (url.isEmpty) return;
                      aspectRatioCache[url] = r;
                    },
                    placeholder: placeholder,
                  ),
                ),
                Positioned(
                  bottom: 12,
                  right: 12,
                  child: _AngleChip(label: angleLabel, color: palette.primary),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _placeholder(String label) {
    return ColoredBox(
      color: palette.surface,
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.threed_rotation,
                size: 64, color: palette.primary.withValues(alpha: 0.35)),
            const SizedBox(height: 10),
            Text(label,
                style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w800,
                    color: palette.textTitle)),
            const SizedBox(height: 2),
            Text('点击生成多角度试衣图',
                style: TextStyle(fontSize: 12, color: palette.textBody)),
          ],
        ),
      ),
    );
  }
}

class _AngleChip extends StatelessWidget {
  final String label;
  final Color color;

  const _AngleChip({required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(999),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.14),
            blurRadius: 10,
            offset: const Offset(0, 4),
          )
        ],
      ),
      child: Text(
        label,
        style: const TextStyle(
            color: Colors.white, fontWeight: FontWeight.w800, fontSize: 12),
      ),
    );
  }
}

class _TryOnNetworkImage extends StatefulWidget {
  final String url;
  final BoxFit fit;
  final Palette palette;
  final Widget placeholder;
  final ValueChanged<double> onAspectRatio;

  const _TryOnNetworkImage({
    required this.url,
    required this.fit,
    required this.palette,
    required this.placeholder,
    required this.onAspectRatio,
  });

  @override
  State<_TryOnNetworkImage> createState() => _TryOnNetworkImageState();
}

class _TryOnNetworkImageState extends State<_TryOnNetworkImage> {
  ImageStream? _stream;
  ImageStreamListener? _listener;

  @override
  void initState() {
    super.initState();
    _resolve();
  }

  @override
  void didUpdateWidget(covariant _TryOnNetworkImage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.url != widget.url) _resolve();
  }

  void _resolve() {
    _detach();
    if (widget.url.isEmpty) return;
    final provider = NetworkImage(widget.url);
    final stream = provider.resolve(const ImageConfiguration());
    _stream = stream;
    _listener = ImageStreamListener((info, _) {
      final w = info.image.width.toDouble();
      final h = info.image.height.toDouble();
      if (w > 0 && h > 0) widget.onAspectRatio(w / h);
    });
    stream.addListener(_listener!);
  }

  void _detach() {
    if (_stream != null && _listener != null) {
      _stream!.removeListener(_listener!);
    }
    _stream = null;
    _listener = null;
  }

  @override
  void dispose() {
    _detach();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.url.isEmpty) return widget.placeholder;
    return ColoredBox(
      color: widget.palette.surface,
      child: Image.network(
        widget.url,
        fit: widget.fit,
        alignment: Alignment.center,
        errorBuilder: (_, __, ___) => widget.placeholder,
        loadingBuilder: (ctx, child, progress) {
          if (progress == null) return child;
          return Center(
            child: SizedBox(
              width: 22,
              height: 22,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: widget.palette.primary,
                value: progress.expectedTotalBytes == null
                    ? null
                    : progress.cumulativeBytesLoaded /
                        (progress.expectedTotalBytes ?? 1),
              ),
            ),
          );
        },
      ),
    );
  }
}

class _TryOnFullscreenGallery extends StatefulWidget {
  final List<String> urls;
  final int initialIndex;
  final Palette palette;
  final Map<String, double> aspectRatioCache;

  const _TryOnFullscreenGallery({
    required this.urls,
    required this.initialIndex,
    required this.palette,
    required this.aspectRatioCache,
  });

  @override
  State<_TryOnFullscreenGallery> createState() =>
      _TryOnFullscreenGalleryState();
}

class _TryOnFullscreenGalleryState extends State<_TryOnFullscreenGallery> {
  late final PageController _ctrl =
      PageController(initialPage: widget.initialIndex);
  int _index = 0;
  static const _labels = ['正面', '侧面', '背面'];

  @override
  void initState() {
    super.initState();
    _index = widget.initialIndex;
  }

  @override
  Widget build(BuildContext context) {
    final palette = widget.palette;
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: const Text('试衣预览'),
      ),
      body: Stack(
        children: [
          PageView.builder(
            controller: _ctrl,
            itemCount: widget.urls.length,
            onPageChanged: (i) => setState(() => _index = i),
            itemBuilder: (_, i) {
              final url = widget.urls[i];
              return InteractiveViewer(
                minScale: 1,
                maxScale: 4,
                child: Center(
                  child: Image.network(
                    url,
                    fit: BoxFit.contain,
                    errorBuilder: (_, __, ___) => const Center(
                      child:
                          Text('加载失败', style: TextStyle(color: Colors.white70)),
                    ),
                  ),
                ),
              );
            },
          ),
          Positioned(
            bottom: 16,
            right: 16,
            child: _AngleChip(
              label: _index < _labels.length
                  ? _labels[_index]
                  : '视角 ${_index + 1}',
              color: palette.primary,
            ),
          ),
        ],
      ),
    );
  }
}
