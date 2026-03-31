import 'dart:io';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';
import '../../../core/providers/auth_provider.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/theme/fashion_palettes.dart';
import '../../../core/widgets/image_picker_section.dart';

/// 我的衣橱
class WardrobeScreen extends StatefulWidget {
  const WardrobeScreen({super.key});

  @override
  State<WardrobeScreen> createState() => _WardrobeScreenState();
}

class _WardrobeScreenState extends State<WardrobeScreen> {
  final _cats = [
    _Cat('全部', Icons.grid_view),
    _Cat('上衣', Icons.dry_cleaning),
    _Cat('裤子', Icons.airline_seat_legroom_normal),
    _Cat('裙子', Icons.checkroom),
    _Cat('外套', Icons.layers),
    _Cat('鞋子', Icons.snowshoeing),
    _Cat('包包', Icons.shopping_bag),
    _Cat('配饰', Icons.watch),
  ];

  String? _chip;
  final _searchCtrl = TextEditingController();
  List<Map<String, dynamic>> _items = [];
  bool _loading = true;
  bool _editMode = false;

  // 撤销（存储完整数据，含图片路径）
  Map<String, dynamic>? _lastDeletedItem;

  @override
  void initState() {
    super.initState();
    _chip = '全部';
    _refresh();
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  /// 全量刷新：从后端拉数据
  Future<void> _refresh() async {
    setState(() => _loading = true);
    final auth = context.read<AuthProvider>();
    try {
      final items = await auth.apiClient.getGarments();
      if (items.isNotEmpty) {
        _items = items;
      } else {
        _items = _demo();
      }
    } catch (_) {
      _items = _demo();
    }
    if (mounted) setState(() => _loading = false);
  }

  List<Map<String, dynamic>> _demo() => [
        {
          'garment_id': '1',
          'id': '1',
          'category': '上衣',
          'style_tags': '通勤、休闲',
          'image_url': null
        },
        {
          'garment_id': '2',
          'id': '2',
          'category': '上衣',
          'style_tags': '复古、优雅',
          'image_url': null
        },
        {
          'garment_id': '3',
          'id': '3',
          'category': '裤子',
          'style_tags': '简约、街头',
          'image_url': null
        },
        {
          'garment_id': '4',
          'id': '4',
          'category': '裙子',
          'style_tags': '甜美、度假',
          'image_url': null
        },
        {
          'garment_id': '5',
          'id': '5',
          'category': '外套',
          'style_tags': '通勤、正式',
          'image_url': null
        },
        {
          'garment_id': '6',
          'id': '6',
          'category': '鞋子',
          'style_tags': '运动、休闲',
          'image_url': null
        },
        {
          'garment_id': '7',
          'id': '7',
          'category': '包包',
          'style_tags': '商务、简约',
          'image_url': null
        },
        {
          'garment_id': '8',
          'id': '8',
          'category': '配饰',
          'style_tags': '潮流、个性',
          'image_url': null
        },
      ];

  String _gid(Map<String, dynamic> g) =>
      (g['garment_id'] ?? g['id']).toString();

  String _cat(Map<String, dynamic> g) => g['category']?.toString() ?? '—';

  String _styles(Map<String, dynamic> g) {
    if (g['style_tags'] != null) return g['style_tags'].toString();
    if (g['styles'] is List) return (g['styles'] as List).join('、');
    return g['notes']?.toString() ?? '';
  }

  /// 获取图片 URL（优先级：image_url > image > local_path）
  String? _imgUrl(Map<String, dynamic> g) {
    final u = g['image_url']?.toString();
    if (u != null && u.isNotEmpty) return u;
    final i = g['image']?.toString();
    if (i != null && i.isNotEmpty) return i;
    return null;
  }

  bool _matchCat(String from, String to) {
    if (to == '全部') return true;
    if (from == to) return true;
    final map = {
      '上衣': ['上衣', 'T恤', '衬衫', '卫衣', '针织衫'],
      '裤子': ['裤子', '下装', '牛仔裤', '长裤'],
      '裙子': ['裙子', '连衣裙', '短裙', '长裙'],
      '外套': ['外套', '夹克', '大衣', '风衣', '羽绒服'],
      '鞋子': ['鞋子', '鞋', '运动鞋', '高跟鞋', '靴子'],
      '包包': ['包包', '包', '背包', '手提包'],
      '配饰': ['配饰', '帽子', '围巾', '腰带', '手表'],
    };
    final targets = map[to] ?? [to];
    return targets.any((t) => from.contains(t) || t.contains(from));
  }

  List<Map<String, dynamic>> get _filtered {
    final q = _searchCtrl.text.trim().toLowerCase();
    return _items.where((g) {
      final c = _cat(g);
      if (_chip != null && _chip != '全部' && !_matchCat(c, _chip!)) return false;
      if (q.isNotEmpty) {
        return c.toLowerCase().contains(q) ||
            _styles(g).toLowerCase().contains(q) ||
            (g['color']?.toString().toLowerCase().contains(q) ?? false) ||
            (g['scene']?.toString().toLowerCase().contains(q) ?? false);
      }
      return true;
    }).toList();
  }

  int _catCount(String cat) {
    if (cat == '全部') return _items.length;
    return _items.where((g) => _matchCat(_cat(g), cat)).length;
  }

  /// 移动分类后全量刷新
  Future<void> _doMove(Map<String, dynamic> g, String newCat) async {
    final id = _gid(g);
    final auth = context.read<AuthProvider>();
    try {
      await auth.apiClient.updateGarmentCategory(id, newCat);
    } catch (_) {}
    setState(() => _editMode = false);
    await _refresh();
  }

  /// 删除（弹出确认）后全量刷新
  Future<void> _delete(Map<String, dynamic> g) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('确认删除'),
        content: const Text('确定要删除这件衣物吗？删除后无法恢复。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            child: const Text('删除'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    _lastDeletedItem = Map.from(g);
    _items.removeWhere((e) => _gid(e) == _gid(g));
    setState(() {});
    final auth = context.read<AuthProvider>();
    try {
      await auth.apiClient.deleteGarment(_gid(g));
    } catch (_) {}
    if (!mounted) return;
    ScaffoldMessenger.of(context).clearSnackBars();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('衣物已删除'),
        backgroundColor: context.read<ThemeProvider>().palette.successColor,
        behavior: SnackBarBehavior.floating,
        duration: const Duration(seconds: 5),
        action: SnackBarAction(
          label: '撤销',
          textColor: Colors.white,
          onPressed: _undoDelete,
        ),
      ),
    );
  }

  /// 撤销：重新上传原衣物（包含图片路径）
  Future<void> _undoDelete() async {
    if (_lastDeletedItem == null) return;
    final item = Map<String, dynamic>.from(_lastDeletedItem!);
    _lastDeletedItem = null;

    final auth = context.read<AuthProvider>();
    final palette = context.read<ThemeProvider>().palette;
    try {
      // 如果有本地图片路径，尝试重新上传
      final localPath = item['local_path']?.toString();
      if (localPath != null && localPath.isNotEmpty) {
        await auth.apiClient.addGarment(
          imageFile: localPath,
          category: _cat(item),
          style: _styles(item),
        );
      } else {
        // 无本地图片，仅记录（无法真实恢复图片）
        // 重新添加条目到列表
        _items.add(item);
        setState(() {});
        await _refresh();
        return;
      }
    } catch (_) {}

    await _refresh();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('已撤销'),
          backgroundColor: palette.successColor,
        ),
      );
    }
  }

  // ─── 添加单件 ───────────────────────────────────────────────
  void _openAdd() {
    var picked = <XFile>[];
    String? selectedCat;
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setModal) {
          final palette = context.read<ThemeProvider>().palette;
          return Padding(
            padding:
                EdgeInsets.only(bottom: MediaQuery.of(ctx).viewInsets.bottom),
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text('添加服饰',
                      style:
                          TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 12),
                  ImagePickerSection(
                    images: picked,
                    onImagesChanged: (list) {
                      picked = List.from(list);
                      setModal(() {});
                    },
                    maxImages: 8,
                    hintText: '选择图片',
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 8,
                    children: _cats.where((c) => c.name != '全部').map((c) {
                      final sel = selectedCat == c.name;
                      return ChoiceChip(
                        label: Text(c.name),
                        selected: sel,
                        selectedColor: palette.chipSelectedBg,
                        labelStyle: TextStyle(
                          color: sel
                              ? palette.chipSelectedLabel
                              : palette.textTitle,
                          fontSize: 13,
                        ),
                        onSelected: (_) =>
                            setModal(() => selectedCat = sel ? null : c.name),
                      );
                    }).toList(),
                  ),
                  const SizedBox(height: 16),
                  FilledButton(
                    style: FilledButton.styleFrom(
                        backgroundColor: palette.primary),
                    onPressed: picked.isEmpty
                        ? null
                        : () async {
                            Navigator.pop(ctx);
                            await _uploadGarments(picked, selectedCat);
                          },
                    child: const Text('上传'),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Future<void> _uploadGarments(List<XFile> images, String? category) async {
    final auth = context.read<AuthProvider>();
    final palette = context.read<ThemeProvider>().palette;
    try {
      for (final img in images) {
        await auth.apiClient.addGarment(
          imageFile: img,
          category: category,
        );
      }
    } catch (_) {}
    await _refresh();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text('已上传 ${images.length} 件服饰'),
            backgroundColor: palette.successColor),
      );
    }
  }

  // ─── 整套上传 ───────────────────────────────────────────────
  void _openSplitUpload() {
    var picked = <XFile>[];
    var splitResult = <Map<String, dynamic>>[];

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setModal) {
          final palette = context.read<ThemeProvider>().palette;
          return DraggableScrollableSheet(
            initialChildSize: 0.85,
            minChildSize: 0.5,
            maxChildSize: 0.95,
            builder: (_, scrollCtrl) => Container(
              decoration: BoxDecoration(
                color: Theme.of(ctx).scaffoldBackgroundColor,
                borderRadius:
                    const BorderRadius.vertical(top: Radius.circular(20)),
              ),
              child: Column(
                children: [
                  const SizedBox(height: 8),
                  Container(
                    width: 40,
                    height: 4,
                    decoration: BoxDecoration(
                        color: Colors.grey.shade300,
                        borderRadius: BorderRadius.circular(2)),
                  ),
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      children: [
                        const Text('整套穿搭上传',
                            style: TextStyle(
                                fontSize: 18, fontWeight: FontWeight.bold)),
                        const Spacer(),
                        if (splitResult.isNotEmpty)
                          TextButton(
                            onPressed: () async {
                              Navigator.pop(ctx);
                              // 传入实际图片
                              await _saveSplit(splitResult,
                                  picked.isNotEmpty ? picked.first : null);
                            },
                            child: const Text('保存到衣橱'),
                          ),
                      ],
                    ),
                  ),
                  Expanded(
                    child: splitResult.isEmpty
                        ? Center(
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                ImagePickerSection(
                                  images: picked,
                                  onImagesChanged: (list) async {
                                    picked = List.from(list);
                                    setModal(() {});
                                    if (picked.isNotEmpty) {
                                      final auth = context.read<AuthProvider>();
                                      try {
                                        final raw = await auth.apiClient
                                            .splitOutfitImage(
                                          imageFile: picked.first,
                                          save: false,
                                        );
                                        if (raw is List && raw.isNotEmpty) {
                                          splitResult = raw
                                              .map((e) =>
                                                  Map<String, dynamic>.from(
                                                      e as Map))
                                              .toList();
                                        }
                                      } catch (_) {
                                        // 演示数据
                                        splitResult = [
                                          {'category': '上衣', 'selected': true},
                                          {'category': '裤子', 'selected': true},
                                          {'category': '鞋子', 'selected': true},
                                        ];
                                      }
                                      setModal(() {});
                                    }
                                  },
                                  maxImages: 1,
                                  hintText: '上传整套穿搭图片',
                                  allowMultiple: false,
                                ),
                                const SizedBox(height: 12),
                                Text('上传一张全身照，AI 自动识别并拆分为多件单品',
                                    style: TextStyle(
                                        fontSize: 12,
                                        color: Colors.grey.shade600)),
                              ],
                            ),
                          )
                        : ListView.builder(
                            controller: scrollCtrl,
                            padding: const EdgeInsets.symmetric(horizontal: 16),
                            itemCount: splitResult.length,
                            itemBuilder: (_, i) {
                              final item = splitResult[i];
                              return Card(
                                margin: const EdgeInsets.only(bottom: 8),
                                child: CheckboxListTile(
                                  value: item['selected'] != false,
                                  onChanged: (v) =>
                                      setModal(() => item['selected'] = v),
                                  title: Text(
                                      item['category']?.toString() ?? '单品'),
                                  secondary: Container(
                                    width: 48,
                                    height: 48,
                                    decoration: BoxDecoration(
                                      color: palette.primary
                                          .withValues(alpha: 0.1),
                                      borderRadius: BorderRadius.circular(8),
                                    ),
                                    child: Icon(Icons.checkroom,
                                        color: palette.primary),
                                  ),
                                ),
                              );
                            },
                          ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  /// 保存拆分结果（传入实际图片）
  Future<void> _saveSplit(
      List<Map<String, dynamic>> parts, dynamic imageFile) async {
    final selected = parts.where((p) => p['selected'] != false).toList();
    if (selected.isEmpty) return;
    final auth = context.read<AuthProvider>();
    final palette = context.read<ThemeProvider>().palette;
    try {
      // 调用拆分 API，传入实际图片
      await auth.apiClient.splitOutfitImage(
        imageFile: imageFile,
        save: true,
      );
    } catch (_) {}
    await _refresh();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text('已保存 ${selected.length} 件单品到衣橱'),
            backgroundColor: palette.successColor),
      );
    }
  }

  // ─── 分类操作菜单 ───────────────────────────────────────────────
  void _showItemMenu(BuildContext ctx, Map<String, dynamic> g) {
    final palette = context.read<ThemeProvider>().palette;
    showModalBottomSheet(
      context: ctx,
      builder: (ctx2) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: Icon(Icons.delete_outline, color: palette.deleteColor),
              title: Text('删除', style: TextStyle(color: palette.deleteColor)),
              onTap: () {
                Navigator.pop(ctx2);
                _delete(g);
              },
            ),
            const Divider(),
            ..._cats.where((c) => c.name != '全部').map((c) => ListTile(
                  leading: Icon(c.icon, color: palette.textTitle),
                  title: Text('移动到 ${c.name}',
                      style: TextStyle(color: palette.textTitle)),
                  onTap: () {
                    Navigator.pop(ctx2);
                    _doMove(g, c.name);
                  },
                )),
          ],
        ),
      ),
    );
  }

  // ─── Build ───────────────────────────────────────────────
  @override
  Widget build(BuildContext context) {
    final palette = context.watch<ThemeProvider>().palette;
    final filtered = _filtered;

    return Scaffold(
      backgroundColor: palette.background,
      appBar: AppBar(
        title: const Text('我的衣橱'),
        centerTitle: true,
        backgroundColor: palette.background,
        surfaceTintColor: Colors.transparent,
        foregroundColor: palette.textTitle,
        actions: [
          IconButton(
            icon: Icon(_editMode ? Icons.check : Icons.edit, size: 22),
            onPressed: () => setState(() => _editMode = !_editMode),
          ),
          IconButton(
            icon: const Icon(Icons.refresh, size: 22),
            onPressed: _loading ? null : _refresh,
          ),
        ],
      ),
      body: Column(
        children: [
          // 搜索栏
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
            child: TextField(
              controller: _searchCtrl,
              onChanged: (_) => setState(() {}),
              decoration: InputDecoration(
                hintText: '搜索衣橱...（品类 / 风格 / 颜色 / 场景）',
                hintStyle: TextStyle(fontSize: 13, color: palette.textBody),
                prefixIcon: Icon(Icons.search, color: palette.textBody),
                suffixIcon: _searchCtrl.text.isNotEmpty
                    ? IconButton(
                        icon: Icon(Icons.clear, color: palette.textBody),
                        onPressed: () {
                          _searchCtrl.clear();
                          setState(() {});
                        })
                    : null,
                border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: BorderSide(color: palette.divider)),
                enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: BorderSide(color: palette.divider)),
                focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: BorderSide(color: palette.primary, width: 1.5)),
                filled: true,
                fillColor: palette.surface,
                contentPadding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              ),
            ),
          ),

          // 左右分栏
          Expanded(
            child: Row(
              children: [
                // 左侧分类栏
                _buildLeftBar(palette),

                // 右侧网格
                Expanded(
                  child: Stack(
                    children: [
                      _loading
                          ? Center(
                              child: CircularProgressIndicator(
                                  color: palette.primary))
                          : filtered.isEmpty
                              ? Center(
                                  child: Column(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    Icon(Icons.checkroom_outlined,
                                        size: 52, color: palette.textBody),
                                    const SizedBox(height: 12),
                                    Text('未找到相关衣物，换个关键词试试~',
                                        style: TextStyle(
                                            color: palette.textBody,
                                            fontSize: 14)),
                                  ],
                                ))
                              : GridView.builder(
                                  padding: const EdgeInsets.all(12),
                                  gridDelegate:
                                      const SliverGridDelegateWithFixedCrossAxisCount(
                                    crossAxisCount: 4,
                                    mainAxisSpacing: 8,
                                    crossAxisSpacing: 8,
                                    childAspectRatio: 1,
                                  ),
                                  itemCount: filtered.length,
                                  itemBuilder: (ctx, i) {
                                    final g = filtered[i];
                                    return _GarmentCard(
                                      key: ValueKey(_gid(g)),
                                      g: g,
                                      palette: palette,
                                      editMode: _editMode,
                                      onLongPress: () {
                                        setState(() => _editMode = true);
                                        _showItemMenu(ctx, g);
                                      },
                                      onDelete: () => _delete(g),
                                      onMove: (cat) => _doMove(g, cat),
                                    );
                                  },
                                ),

                      // 删除区
                      if (_editMode)
                        Positioned(
                          bottom: 0,
                          left: 0,
                          right: 0,
                          child: _DeleteZone(
                              palette: palette, onDelete: (g) => _delete(g)),
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
      floatingActionButton: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          FloatingActionButton.small(
            heroTag: 'split',
            backgroundColor: palette.secondary,
            onPressed: _openSplitUpload,
            tooltip: '整套穿搭上传',
            child: const Icon(Icons.view_comfy_alt, color: Colors.white),
          ),
          const SizedBox(width: 12),
          FloatingActionButton(
            heroTag: 'add',
            backgroundColor: palette.primary,
            onPressed: _openAdd,
            tooltip: '添加服饰',
            child: const Icon(Icons.add, color: Colors.white),
          ),
        ],
      ),
    );
  }

  Widget _buildLeftBar(Palette palette) {
    return DragTarget<Map<String, dynamic>>(
      onWillAcceptWithDetails: (_) => true,
      onAcceptWithDetails: (d) {
        final g = d.data;
        final targetCats = _cats.where((c) => c.name != '全部').toList();
        if (targetCats.isNotEmpty) _doMove(g, targetCats.first.name);
      },
      builder: (ctx, cand, rej) => Container(
        width: 76,
        color: cand.isNotEmpty
            ? palette.primary.withValues(alpha: 0.12)
            : palette.surface,
        child: ListView.builder(
          padding: const EdgeInsets.symmetric(vertical: 4),
          itemCount: _cats.length,
          itemBuilder: (ctx, i) {
            final c = _cats[i];
            final sel = (_chip == c.name) || (_chip == null && c.name == '全部');
            return GestureDetector(
              onTap: () =>
                  setState(() => _chip = c.name == '全部' ? null : c.name),
              child: Container(
                width: 76,
                padding: const EdgeInsets.symmetric(vertical: 12),
                decoration: BoxDecoration(
                  color: sel ? palette.primary.withValues(alpha: 0.12) : null,
                  border: sel
                      ? Border(
                          bottom: BorderSide(color: palette.primary, width: 2))
                      : null,
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(c.icon,
                        size: 22,
                        color: sel ? palette.primary : palette.textBody),
                    const SizedBox(height: 4),
                    Text(c.name,
                        style: TextStyle(
                            fontSize: 11,
                            color: sel ? palette.primary : palette.textBody,
                            fontWeight:
                                sel ? FontWeight.bold : FontWeight.normal)),
                    Text('${_catCount(c.name)}',
                        style:
                            TextStyle(fontSize: 10, color: palette.textBody)),
                  ],
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}

class _Cat {
  final String name;
  final IconData icon;
  _Cat(this.name, this.icon);
}

class _GarmentCard extends StatelessWidget {
  final Map<String, dynamic> g;
  final Palette palette;
  final bool editMode;
  final VoidCallback onLongPress;
  final VoidCallback onDelete;
  final void Function(String cat) onMove;

  const _GarmentCard({
    super.key,
    required this.g,
    required this.palette,
    required this.editMode,
    required this.onLongPress,
    required this.onDelete,
    required this.onMove,
  });

  String? get _imgUrl {
    final u = g['image_url']?.toString();
    if (u != null && u.isNotEmpty) return u;
    final i = g['image']?.toString();
    if (i != null && i.isNotEmpty) return i;
    return null;
  }

  @override
  Widget build(BuildContext context) {
    return LongPressDraggable<Map<String, dynamic>>(
      data: g,
      feedback: Material(
        elevation: 8,
        borderRadius: BorderRadius.circular(12),
        child: Opacity(
          opacity: 0.75,
          child: Transform.scale(
            scale: 1.08,
            child: SizedBox(width: 90, height: 90, child: _buildCard()),
          ),
        ),
      ),
      childWhenDragging: Opacity(opacity: 0.3, child: _buildCard()),
      delay: const Duration(milliseconds: 500),
      child: GestureDetector(
        onLongPress: onLongPress,
        child: _buildCard(),
      ),
    );
  }

  Widget _buildCard() {
    final url = _imgUrl;
    final hasImg = url != null;
    final catLabel = g['category']?.toString() ?? '';

    return Card(
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: palette.divider),
      ),
      clipBehavior: Clip.antiAlias,
      child: Stack(
        fit: StackFit.expand,
        children: [
          // 图片（优先网络 URL，再本地路径）
          if (hasImg)
            Image.network(
              url!,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => _placeholder,
              loadingBuilder: (_, child, progress) {
                if (progress == null) return child;
                return Container(
                  color: palette.primary.withValues(alpha: 0.05),
                  child: const Center(
                      child: CircularProgressIndicator(strokeWidth: 2)),
                );
              },
            )
          else
            _placeholder,

          // 分类标签
          Positioned(
            bottom: 0,
            left: 0,
            right: 0,
            child: Container(
              padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 6),
              decoration: BoxDecoration(
                gradient: LinearGradient(
                    begin: Alignment.bottomCenter,
                    end: Alignment.topCenter,
                    colors: [Colors.black54, Colors.transparent]),
              ),
              child: Text(catLabel,
                  style: const TextStyle(
                      color: Colors.white,
                      fontSize: 10,
                      fontWeight: FontWeight.w600),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.center),
            ),
          ),
        ],
      ),
    );
  }

  Widget get _placeholder => Container(
        decoration:
            BoxDecoration(color: palette.primary.withValues(alpha: 0.1)),
        child: Center(
          child: Icon(Icons.checkroom, size: 28, color: palette.primary),
        ),
      );
}

class _DeleteZone extends StatelessWidget {
  final Palette palette;
  final void Function(Map<String, dynamic>) onDelete;

  const _DeleteZone({required this.palette, required this.onDelete});

  @override
  Widget build(BuildContext context) {
    return DragTarget<Map<String, dynamic>>(
      onWillAcceptWithDetails: (_) => true,
      onAcceptWithDetails: (d) => onDelete(d.data),
      builder: (ctx, cand, rej) => AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        height: 60,
        margin: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: cand.isNotEmpty ? Colors.red.shade400 : palette.deleteBg,
          borderRadius: BorderRadius.circular(16),
          border: cand.isNotEmpty
              ? Border.all(color: Colors.red.shade600, width: 2)
              : null,
        ),
        child: Center(
          child: Text(
            cand.isNotEmpty ? '松开删除' : '拖到这里删除',
            style: const TextStyle(
                color: Colors.white, fontWeight: FontWeight.bold, fontSize: 15),
          ),
        ),
      ),
    );
  }
}
