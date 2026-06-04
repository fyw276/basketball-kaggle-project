import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/auth_provider.dart';
import '../utils/media_url.dart';
import 'platform_image.dart';

/// 衣橱选择结果。
class WardrobePickResult {
  final String garmentId;
  final String? imageUrl;
  final String? category;
  final String? mainColorName;

  const WardrobePickResult({
    required this.garmentId,
    this.imageUrl,
    this.category,
    this.mainColorName,
  });
}

/// 从衣橱选择衣物的底部弹窗。
///
/// 用法：
/// ```dart
/// final result = await showWardrobePicker(context, multiSelect: true);
/// ```
Future<List<WardrobePickResult>?> showWardrobePicker(
  BuildContext context, {
  bool multiSelect = false,
}) {
  return showModalBottomSheet<List<WardrobePickResult>>(
    context: context,
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (_) => WardrobePickerSheet(multiSelect: multiSelect),
  );
}

class WardrobePickerSheet extends StatefulWidget {
  final bool multiSelect;

  const WardrobePickerSheet({super.key, this.multiSelect = false});

  @override
  State<WardrobePickerSheet> createState() => _WardrobePickerSheetState();
}

class _WardrobePickerSheetState extends State<WardrobePickerSheet> {
  static const _categories = [
    '全部',
    '上衣',
    '裤子',
    '裙子',
    '外套',
    '鞋',
    '包',
    '连衣裙',
    '汉服',
    '国风',
    '马面裙',
  ];

  String _selectedCat = '全部';
  List<Map<String, dynamic>> _items = [];
  bool _loading = true;
  String? _error;

  /// 多选模式下已选 id 集合。
  final Set<String> _selectedIds = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final auth = context.read<AuthProvider>();
      _items = await auth.apiClient.getGarments(pageSize: 100);
    } catch (e) {
      _error = '加载衣橱失败：$e';
      _items = [];
    }
    if (mounted) setState(() => _loading = false);
  }

  List<Map<String, dynamic>> get _filtered {
    if (_selectedCat == '全部') return _items;
    return _items
        .where((g) => (g['category']?.toString() ?? '') == _selectedCat)
        .toList();
  }

  String _garmentId(Map<String, dynamic> g) =>
      (g['item_id'] ?? g['garment_id'] ?? g['id'] ?? '').toString();

  void _onTapItem(Map<String, dynamic> g) {
    final gid = _garmentId(g);

    if (gid.isEmpty) {
      // 没有 ID，弹提示
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('衣物ID为空，无法选择')),
      );
      return;
    }

    if (widget.multiSelect) {
      setState(() {
        if (_selectedIds.contains(gid)) {
          _selectedIds.remove(gid);
        } else {
          _selectedIds.add(gid);
        }
      });
    } else {
      // 单选：直接返回
      final result = WardrobePickResult(
        garmentId: gid,
        imageUrl: g['image_url']?.toString(),
        category: g['category']?.toString(),
        mainColorName: _mainColorName(g),
      );
      Navigator.pop(context, [result]);
    }
  }

  void _confirmMultiSelect() {
    final results = _items
        .where((g) => _selectedIds.contains(_garmentId(g)))
        .map((g) => WardrobePickResult(
              garmentId: _garmentId(g),
              imageUrl: g['image_url']?.toString(),
              category: g['category']?.toString(),
              mainColorName: _mainColorName(g),
            ))
        .toList();
    Navigator.pop(context, results);
  }

  String? _mainColorName(Map<String, dynamic> g) {
    final mainColor = g['main_color'];
    if (mainColor is Map && mainColor['name'] != null) {
      final name = mainColor['name'].toString().trim();
      if (name.isNotEmpty) return name;
    }
    final color = g['color']?.toString().trim();
    return color != null && color.isNotEmpty ? color : null;
  }

  @override
  Widget build(BuildContext context) {
    final mq = MediaQuery.of(context);
    final screenHeight = mq.size.height;
    // 弹窗高度：屏幕的 70%，但至少 400px
    final sheetHeight = (screenHeight * 0.7).clamp(400.0, screenHeight * 0.85);

    return SizedBox(
      height: sheetHeight,
      child: Column(
        children: [
          // ── 拖拽指示条 ──
          Padding(
            padding: const EdgeInsets.only(top: 10, bottom: 6),
            child: Container(
              width: 36,
              height: 4,
              decoration: BoxDecoration(
                color: Colors.grey.shade400,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),

          // ── 标题栏 ──
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Row(
              children: [
                Text(
                  '从衣橱选择',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                ),
                const Spacer(),
                if (widget.multiSelect && _selectedIds.isNotEmpty)
                  TextButton(
                    onPressed: _confirmMultiSelect,
                    child: Text('确定（${_selectedIds.length}）'),
                  ),
                IconButton(
                  icon: const Icon(Icons.close),
                  onPressed: () => Navigator.pop(context),
                ),
              ],
            ),
          ),

          // ── 分类标签 ──
          SizedBox(
            height: 40,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 16),
              itemCount: _categories.length,
              separatorBuilder: (_, __) => const SizedBox(width: 8),
              itemBuilder: (_, i) {
                final cat = _categories[i];
                final selected = cat == _selectedCat;
                return ChoiceChip(
                  label: Text(cat),
                  selected: selected,
                  onSelected: (_) => setState(() => _selectedCat = cat),
                );
              },
            ),
          ),
          const SizedBox(height: 8),

          // ── 内容区 ──
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _error != null
                    ? Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(_error!,
                                style: const TextStyle(color: Colors.red)),
                            const SizedBox(height: 12),
                            OutlinedButton(
                              onPressed: _load,
                              child: const Text('重试'),
                            ),
                          ],
                        ),
                      )
                    : _filtered.isEmpty
                        ? Center(
                            child: Text(
                              _selectedCat == '全部'
                                  ? '衣橱为空，请先添加衣物'
                                  : '「$_selectedCat」分类暂无衣物',
                              style: TextStyle(color: Colors.grey.shade500),
                            ),
                          )
                        : GridView.builder(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 16, vertical: 4),
                            gridDelegate:
                                const SliverGridDelegateWithFixedCrossAxisCount(
                              crossAxisCount: 3,
                              mainAxisSpacing: 10,
                              crossAxisSpacing: 10,
                              childAspectRatio: 0.75,
                            ),
                            itemCount: _filtered.length,
                            itemBuilder: (_, i) => _buildItem(_filtered[i]),
                          ),
          ),
        ],
      ),
    );
  }

  Widget _buildItem(Map<String, dynamic> garment) {
    final auth = context.read<AuthProvider>();
    final rawUrl = garment['image_url']?.toString();
    final thumbUrl = resolveGarmentImageUrl(rawUrl, auth.apiClient.baseUrl);
    final gid = _garmentId(garment);
    final isSelected = _selectedIds.contains(gid);
    final cat = garment['category']?.toString() ?? '';

    return InkWell(
      onTap: () => _onTapItem(garment),
      borderRadius: BorderRadius.circular(12),
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isSelected
                ? Theme.of(context).colorScheme.primary
                : Colors.grey.shade300,
            width: isSelected ? 2.5 : 1,
          ),
        ),
        clipBehavior: Clip.antiAlias,
        child: Stack(
          fit: StackFit.expand,
          children: [
            // 图片（IgnorePointer 防止 Image.network 吸收点击事件）
            if (thumbUrl != null)
              IgnorePointer(
                child: PlatformImage(
                  networkUrl: thumbUrl,
                  fit: BoxFit.cover,
                  placeholder: Center(
                    child: Icon(Icons.checkroom,
                        color: Colors.grey.shade400, size: 32),
                  ),
                  errorWidget: Center(
                    child: Icon(Icons.broken_image,
                        color: Colors.grey.shade400, size: 32),
                  ),
                ),
              )
            else
              IgnorePointer(
                child: Container(
                  color: Colors.grey.shade100,
                  child: Center(
                    child: Icon(Icons.checkroom,
                        color: Colors.grey.shade400, size: 32),
                  ),
                ),
              ),

            // 分类标签
            if (cat.isNotEmpty)
              Positioned(
                left: 0,
                bottom: 0,
                right: 0,
                child: IgnorePointer(
                  child: Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.bottomCenter,
                        end: Alignment.topCenter,
                        colors: [
                          Colors.black.withValues(alpha: 0.6),
                          Colors.transparent,
                        ],
                      ),
                    ),
                    child: Text(
                      cat,
                      style: const TextStyle(color: Colors.white, fontSize: 11),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ),
              ),

            // 多选勾选标记
            if (widget.multiSelect && isSelected)
              Positioned(
                top: 4,
                right: 4,
                child: Container(
                  padding: const EdgeInsets.all(2),
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.primary,
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(Icons.check, size: 16, color: Colors.white),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
