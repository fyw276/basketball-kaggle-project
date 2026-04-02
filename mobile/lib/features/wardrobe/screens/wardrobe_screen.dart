import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../../core/providers/auth_provider.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/theme/fashion_palettes.dart';
import '../../../core/utils/app_snackbar.dart';
import '../../../core/utils/media_url.dart';
import '../../../core/widgets/image_picker_section.dart';
import '../../../core/widgets/platform_image.dart';

/// 衣橱：左栏分类 + 右栏 4 列网格；长按 0.5s 拖动改分类 / 底部删除；数据以服务端为准。
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

  String _chip = '全部';
  final _searchCtrl = TextEditingController();
  List<Map<String, dynamic>> _items = [];
  bool _loading = true;
  bool _editMode = false;

  Map<String, dynamic>? _lastDeletedItem;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _refresh() async {
    setState(() => _loading = true);
    final auth = context.read<AuthProvider>();
    try {
      _items = await auth.apiClient.getGarments();
    } catch (_) {
      _items = [];
    }
    if (mounted) setState(() => _loading = false);
  }

  String _gid(Map<String, dynamic> g) =>
      (g['item_id'] ?? g['garment_id'] ?? g['id'] ?? '').toString();

  String _cat(Map<String, dynamic> g) => g['category']?.toString() ?? '—';

  String _styles(Map<String, dynamic> g) {
    if (g['style_tags'] != null) return g['style_tags'].toString();
    if (g['styles'] is List) return (g['styles'] as List).join('、');
    return g['notes']?.toString() ?? '';
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
      if (_chip != '全部' && !_matchCat(c, _chip)) return false;
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

  Future<void> _doMove(Map<String, dynamic> g, String newCat) async {
    final id = _gid(g);
    if (id.isEmpty) return;
    final auth = context.read<AuthProvider>();
    try {
      await auth.apiClient.updateGarmentCategory(id, newCat);
    } catch (_) {}
    setState(() => _editMode = false);
    await _refresh();
  }

  Future<void> _delete(Map<String, dynamic> g) async {
    final auth = context.read<AuthProvider>();
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

    _lastDeletedItem = Map<String, dynamic>.from(g);
    final id = _gid(g);
    try {
      await auth.apiClient.deleteGarment(id);
    } catch (_) {
      _lastDeletedItem = null;
      if (mounted) {
        showAppSnackBar(context, '删除失败，请重试');
      }
      return;
    }
    await _refresh();
    if (!mounted) return;
    ScaffoldMessenger.of(context).clearSnackBars();
    showAppSnackBar(
      context,
      '衣物已删除',
      backgroundColor: context.read<ThemeProvider>().palette.successColor,
      action: SnackBarAction(
        label: '撤销',
        textColor: Colors.white,
        onPressed: _undoDelete,
      ),
    );
  }

  Future<void> _undoDelete() async {
    if (_lastDeletedItem == null) return;
    final item = Map<String, dynamic>.from(_lastDeletedItem!);
    _lastDeletedItem = null;
    final auth = context.read<AuthProvider>();
    final palette = context.read<ThemeProvider>().palette;
    try {
      final localPath = item['local_path']?.toString();
      if (localPath != null && localPath.isNotEmpty) {
        await auth.apiClient.addGarment(
          imageFile: localPath,
          category: _cat(item),
          style: _styles(item),
        );
      }
      await _refresh();
    } catch (_) {}
    if (mounted) {
      showAppSnackBar(context, '已尝试撤销', backgroundColor: palette.successColor);
    }
  }

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
    if (images.isEmpty) return;
    final progress = ValueNotifier<int>(0);
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (dialogCtx) {
        final palette = context.read<ThemeProvider>().palette;
        return ValueListenableBuilder<int>(
          valueListenable: progress,
          builder: (context, idx, _) {
            return PopScope(
              canPop: false,
              child: AlertDialog(
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(20)),
                content: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    SizedBox(
                      width: 40,
                      height: 40,
                      child: CircularProgressIndicator(
                        strokeWidth: 3,
                        color: palette.primary,
                      ),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      '正在上传第 ${idx + 1} / ${images.length} 张',
                      style: TextStyle(color: palette.textTitle, fontSize: 15),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 12),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(6),
                      child: LinearProgressIndicator(
                        value: (idx + 1) / images.length,
                        minHeight: 6,
                        backgroundColor:
                            palette.primary.withValues(alpha: 0.15),
                        color: palette.primary,
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );

    final auth = context.read<AuthProvider>();
    final palette = context.read<ThemeProvider>().palette;
    var ok = 0;
    var lastErr = '';
    try {
      for (var i = 0; i < images.length; i++) {
        progress.value = i;
        final r = await auth.apiClient.addGarment(
          imageFile: images[i],
          category: category,
        );
        if (r.containsKey('error')) {
          lastErr = r['error'].toString();
        } else {
          ok++;
        }
      }
    } finally {
      if (mounted) Navigator.of(context, rootNavigator: true).pop();
      progress.dispose();
    }

    await _refresh();
    if (!mounted) return;
    if (ok > 0) {
      showAppSnackBar(
        context,
        '成功上传 $ok 件${lastErr.isNotEmpty ? '（部分失败）' : ''}',
        backgroundColor: palette.successColor,
      );
    }
    if (lastErr.isNotEmpty && ok < images.length) {
      showAppSnackBar(context, '上传失败：${userFacingApiError(lastErr)}');
    }
  }

  void _openSplitUpload() {
    var picked = <XFile>[];
    var splitResult = <Map<String, dynamic>>[];
    var splitBusy = false;

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
                    const BorderRadius.vertical(top: Radius.circular(22)),
              ),
              child: Column(
                children: [
                  const SizedBox(height: 8),
                  Container(
                    width: 40,
                    height: 4,
                    decoration: BoxDecoration(
                      color: Colors.grey.shade300,
                      borderRadius: BorderRadius.circular(2),
                    ),
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
                              await _saveSplit(splitResult,
                                  picked.isNotEmpty ? picked.first : null);
                            },
                            child: const Text('保存到衣橱'),
                          ),
                      ],
                    ),
                  ),
                  Expanded(
                    child: splitBusy
                        ? Center(
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                SizedBox(
                                  width: 44,
                                  height: 44,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 3,
                                    color: palette.primary,
                                  ),
                                ),
                                const SizedBox(height: 16),
                                Text(
                                  '正在拆分整套图…',
                                  style: TextStyle(
                                    fontSize: 15,
                                    fontWeight: FontWeight.w600,
                                    color: palette.textTitle,
                                  ),
                                ),
                                const SizedBox(height: 8),
                                Padding(
                                  padding: const EdgeInsets.symmetric(
                                      horizontal: 32),
                                  child: Text(
                                    '首次拆分需上传并识别，请稍候',
                                    textAlign: TextAlign.center,
                                    style: TextStyle(
                                        fontSize: 13, color: palette.textBody),
                                  ),
                                ),
                              ],
                            ),
                          )
                        : splitResult.isEmpty
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
                                          splitBusy = true;
                                          setModal(() {});
                                          final auth =
                                              context.read<AuthProvider>();
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
                                            } else if (raw is Map) {
                                              if (raw['error'] != null) {
                                                if (ctx.mounted) {
                                                  showAppSnackBar(
                                                    ctx,
                                                    '拆分失败：${userFacingApiError(raw['error'])}',
                                                  );
                                                }
                                              } else if (raw['items'] is List &&
                                                  (raw['items'] as List)
                                                      .isNotEmpty) {
                                                splitResult = (raw['items']
                                                        as List)
                                                    .map((e) => Map<String,
                                                        dynamic>.from(e as Map))
                                                    .toList();
                                              }
                                            }
                                          } catch (e) {
                                            if (ctx.mounted) {
                                              showAppSnackBar(
                                                ctx,
                                                '拆分失败：${userFacingApiError(e)}',
                                              );
                                            }
                                          } finally {
                                            splitBusy = false;
                                          }
                                          setModal(() {});
                                        }
                                      },
                                      maxImages: 1,
                                      hintText: '上传整套穿搭图片',
                                      allowMultiple: false,
                                    ),
                                    const SizedBox(height: 12),
                                    Text(
                                      '上传一张全身照，AI 自动识别并拆分为多件单品',
                                      style: TextStyle(
                                          fontSize: 12,
                                          color: Colors.grey.shade600),
                                    ),
                                  ],
                                ),
                              )
                            : ListView.builder(
                                controller: scrollCtrl,
                                padding:
                                    const EdgeInsets.symmetric(horizontal: 16),
                                itemCount: splitResult.length,
                                itemBuilder: (_, i) {
                                  final item = splitResult[i];
                                  final auth = context.read<AuthProvider>();
                                  final thumb = resolveGarmentImageUrl(
                                    item['image_url']?.toString(),
                                    auth.apiClient.baseUrl,
                                  );
                                  return Card(
                                    margin: const EdgeInsets.only(bottom: 8),
                                    shape: RoundedRectangleBorder(
                                        borderRadius:
                                            BorderRadius.circular(18)),
                                    child: CheckboxListTile(
                                      value: item['selected'] != false,
                                      onChanged: (v) =>
                                          setModal(() => item['selected'] = v),
                                      title: Text(
                                          item['category']?.toString() ?? '单品'),
                                      secondary: ClipRRect(
                                        borderRadius: BorderRadius.circular(12),
                                        child: SizedBox(
                                          width: 48,
                                          height: 48,
                                          child: thumb != null
                                              ? PlatformImage(
                                                  networkUrl: thumb,
                                                  width: 48,
                                                  height: 48,
                                                  fit: BoxFit.cover,
                                                  placeholder: Icon(
                                                    Icons.checkroom,
                                                    color: palette.primary,
                                                  ),
                                                )
                                              : ColoredBox(
                                                  color: palette.primary
                                                      .withValues(alpha: 0.1),
                                                  child: Icon(
                                                    Icons.checkroom,
                                                    color: palette.primary,
                                                  ),
                                                ),
                                        ),
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

  Future<void> _saveSplit(
      List<Map<String, dynamic>> parts, dynamic imageFile) async {
    final selected = parts.where((p) => p['selected'] != false).toList();
    if (selected.isEmpty || imageFile == null) return;
    final indexes = <int>[];
    for (var i = 0; i < parts.length; i++) {
      if (parts[i]['selected'] != false) indexes.add(i);
    }
    final auth = context.read<AuthProvider>();
    final palette = context.read<ThemeProvider>().palette;

    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (dialogCtx) {
        return PopScope(
          canPop: false,
          child: AlertDialog(
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
            content: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                  width: 40,
                  height: 40,
                  child: CircularProgressIndicator(
                    strokeWidth: 3,
                    color: palette.primary,
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Text(
                    '正在拆分并保存到衣橱…\n'
                    '将对每件勾选单品做识别与入库，耗时取决于设备与后端，请耐心等待（最长约 3 分钟）。',
                    style: TextStyle(
                        color: palette.textTitle, height: 1.4, fontSize: 14),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );

    try {
      final raw = await auth.apiClient.splitOutfitImage(
        imageFile: imageFile,
        save: true,
        selectedIndexes: indexes,
      );
      if (raw is Map && raw['error'] != null) {
        if (mounted) {
          showAppSnackBar(context, '保存失败：${userFacingApiError(raw['error'])}');
        }
        return;
      }
      var savedCount = 0;
      if (raw is Map) {
        final items = raw['items'];
        if (items is List) {
          for (final e in items) {
            if (e is Map) {
              final gid = e['garment_id'];
              if (gid != null && gid.toString().isNotEmpty) savedCount++;
            }
          }
        }
      }
      await _refresh();
      if (!mounted) return;
      if (savedCount > 0) {
        showAppSnackBar(
          context,
          '已将 $savedCount 件拆分单品保存到衣橱',
          backgroundColor: palette.successColor,
        );
      } else {
        showAppSnackBar(
          context,
          '未能写入衣橱（服务端未返回 garment_id）。请热重载/更新应用后重试；若仍失败请查看后端日志。',
        );
      }
    } catch (e) {
      if (mounted) {
        showAppSnackBar(context, '保存失败：${userFacingApiError(e)}');
      }
      return;
    } finally {
      if (mounted) {
        Navigator.of(context, rootNavigator: true).pop();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final palette = context.watch<ThemeProvider>().palette;
    final filtered = _filtered;
    final auth = context.watch<AuthProvider>();

    return Scaffold(
      backgroundColor: palette.background,
      appBar: AppBar(
        title: const Text('我的衣橱'),
        centerTitle: true,
        backgroundColor: palette.background,
        surfaceTintColor: Colors.transparent,
        foregroundColor: palette.textTitle,
        actions: [
          if (_editMode)
            TextButton(
              onPressed: () => setState(() => _editMode = false),
              child: Text('完成',
                  style: TextStyle(
                      color: palette.primary, fontWeight: FontWeight.w700)),
            ),
          IconButton(
            icon: const Icon(Icons.refresh, size: 22),
            onPressed: _loading ? null : _refresh,
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
            child: TextField(
              controller: _searchCtrl,
              onChanged: (_) => setState(() {}),
              decoration: InputDecoration(
                hintText: '搜索品类、风格、颜色、场景',
                hintStyle: TextStyle(fontSize: 13, color: palette.textBody),
                prefixIcon: Icon(Icons.search, color: palette.textBody),
                suffixIcon: _searchCtrl.text.isNotEmpty
                    ? IconButton(
                        icon: Icon(Icons.clear, color: palette.textBody),
                        onPressed: () {
                          _searchCtrl.clear();
                          setState(() {});
                        },
                      )
                    : null,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(20),
                  borderSide: BorderSide(color: palette.divider),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(20),
                  borderSide: BorderSide(color: palette.divider),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(20),
                  borderSide: BorderSide(color: palette.primary, width: 1.5),
                ),
                filled: true,
                fillColor: palette.surface,
                contentPadding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              ),
            ),
          ),
          Expanded(
            child: Row(
              children: [
                _buildLeftBar(palette),
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
                                      Text(
                                        _items.isEmpty
                                            ? '衣橱还是空的，点击右下角添加或整套上传'
                                            : '未找到相关衣物，换个关键词试试',
                                        textAlign: TextAlign.center,
                                        style: TextStyle(
                                            color: palette.textBody,
                                            fontSize: 14),
                                      ),
                                    ],
                                  ),
                                )
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
                                    final id = _gid(g);
                                    return _GarmentCard(
                                      key: ValueKey('wardrobe_$id'),
                                      g: g,
                                      palette: palette,
                                      apiBase: auth.apiClient.baseUrl,
                                      editMode: _editMode,
                                      onDragStarted: () =>
                                          setState(() => _editMode = true),
                                      onDragEnd: () =>
                                          setState(() => _editMode = false),
                                      onDelete: _delete,
                                    );
                                  },
                                ),
                      if (_editMode)
                        Positioned(
                          bottom: 0,
                          left: 0,
                          right: 0,
                          child: _DeleteZone(
                            palette: palette,
                            onDelete: _delete,
                          ),
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
    return Container(
      width: 88,
      color: palette.surface,
      child: ListView.builder(
        padding: const EdgeInsets.symmetric(vertical: 4),
        itemCount: _cats.length,
        itemBuilder: (ctx, i) {
          final c = _cats[i];
          final sel = _chip == c.name;
          if (c.name == '全部') {
            return GestureDetector(
              onTap: () => setState(() => _chip = '全部'),
              child: _catCell(c, sel, palette, null),
            );
          }
          return DragTarget<Map<String, dynamic>>(
            onWillAcceptWithDetails: (_) => true,
            onAcceptWithDetails: (d) => _doMove(d.data, c.name),
            builder: (ctx, cand, _) {
              final highlight = cand.isNotEmpty;
              return GestureDetector(
                onTap: () => setState(() => _chip = c.name),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  decoration: BoxDecoration(
                    color: highlight
                        ? palette.primary.withValues(alpha: 0.2)
                        : sel
                            ? palette.primary.withValues(alpha: 0.12)
                            : null,
                    border: Border(
                      bottom: BorderSide(color: palette.divider),
                    ),
                  ),
                  child: _catCell(c, sel, palette, highlight),
                ),
              );
            },
          );
        },
      ),
    );
  }

  Widget _catCell(_Cat c, bool sel, Palette palette, bool? dragHighlight) {
    return Container(
      width: 88,
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            c.icon,
            size: 22,
            color: dragHighlight == true
                ? palette.primary
                : (sel ? palette.primary : palette.textBody),
          ),
          const SizedBox(height: 4),
          Text(
            c.name,
            style: TextStyle(
              fontSize: 11,
              color: sel ? palette.primary : palette.textBody,
              fontWeight: sel ? FontWeight.bold : FontWeight.normal,
            ),
          ),
          Text(
            '${_catCount(c.name)}',
            style: TextStyle(fontSize: 10, color: palette.textBody),
          ),
        ],
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
  final String apiBase;
  final bool editMode;
  final VoidCallback onDragStarted;
  final VoidCallback onDragEnd;
  final Future<void> Function(Map<String, dynamic>) onDelete;

  const _GarmentCard({
    super.key,
    required this.g,
    required this.palette,
    required this.apiBase,
    required this.editMode,
    required this.onDragStarted,
    required this.onDragEnd,
    required this.onDelete,
  });

  String? _resolvedUrl() {
    final raw = g['image_url']?.toString() ?? g['image']?.toString();
    return resolveGarmentImageUrl(raw, apiBase);
  }

  @override
  Widget build(BuildContext context) {
    final url = _resolvedUrl();

    Widget cardFace = ClipRRect(
      borderRadius: BorderRadius.circular(18),
      child: url != null && url.isNotEmpty
          ? Image.network(
              url,
              fit: BoxFit.cover,
              width: double.infinity,
              height: double.infinity,
              errorBuilder: (_, __, ___) => _placeholder(),
              loadingBuilder: (_, child, prog) {
                if (prog == null) return child;
                return Container(
                  color: palette.primary.withValues(alpha: 0.06),
                  child: Center(
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: palette.primary),
                  ),
                );
              },
            )
          : _placeholder(),
    );

    if (editMode) {
      cardFace = Opacity(
        opacity: 0.88,
        child: Transform.scale(scale: 0.96, child: cardFace),
      );
    }

    return LongPressDraggable<Map<String, dynamic>>(
      data: g,
      delay: const Duration(milliseconds: 500),
      onDragStarted: onDragStarted,
      onDragEnd: (_) => onDragEnd(),
      onDraggableCanceled: (_, __) => onDragEnd(),
      feedback: Material(
        elevation: 10,
        borderRadius: BorderRadius.circular(18),
        child: Opacity(
          opacity: 0.85,
          child: SizedBox(
            width: 88,
            height: 88,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(18),
              child: url != null && url.isNotEmpty
                  ? Image.network(url, fit: BoxFit.cover)
                  : _placeholder(),
            ),
          ),
        ),
      ),
      childWhenDragging: Opacity(opacity: 0.35, child: cardFace),
      child: Card(
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(18),
          side: BorderSide(color: palette.divider),
        ),
        clipBehavior: Clip.antiAlias,
        child: cardFace,
      ),
    );
  }

  Widget _placeholder() => Container(
        color: palette.primary.withValues(alpha: 0.08),
        child: Icon(Icons.checkroom, size: 32, color: palette.primary),
      );
}

class _DeleteZone extends StatelessWidget {
  final Palette palette;
  final Future<void> Function(Map<String, dynamic>) onDelete;

  const _DeleteZone({required this.palette, required this.onDelete});

  @override
  Widget build(BuildContext context) {
    return DragTarget<Map<String, dynamic>>(
      onWillAcceptWithDetails: (_) => true,
      onAcceptWithDetails: (d) => onDelete(d.data),
      builder: (ctx, cand, _) => AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        height: 64,
        margin: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: cand.isNotEmpty ? Colors.red.shade400 : palette.deleteBg,
          borderRadius: BorderRadius.circular(22),
          border: cand.isNotEmpty
              ? Border.all(color: Colors.red.shade700, width: 2)
              : null,
          boxShadow: palette.cardShadows,
        ),
        child: Center(
          child: Text(
            cand.isNotEmpty ? '松开确认删除' : '拖到此处删除',
            style: const TextStyle(
                color: Colors.white, fontWeight: FontWeight.bold, fontSize: 15),
          ),
        ),
      ),
    );
  }
}
