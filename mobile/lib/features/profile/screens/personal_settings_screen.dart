import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../core/providers/auth_provider.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/utils/app_snackbar.dart';
import '../../../core/theme/fashion_palettes.dart';

/// 个人设置页
/// - 删除性别选项，仅保留「性别表达指数」滑块
/// - 保留：性别表达指数、身高、体型、肤色、风格偏好、预算范围、修饰部位
/// - 说明：用于穿搭推荐参考，与上方风格指数独立调整
class PersonalSettingsScreen extends StatefulWidget {
  const PersonalSettingsScreen({super.key});

  @override
  State<PersonalSettingsScreen> createState() => _PersonalSettingsScreenState();
}

class _PersonalSettingsScreenState extends State<PersonalSettingsScreen> {
  bool _loading = true;
  bool _saving = false;

  double _height = 170;
  String? _bodyType;
  String? _skinTone;
  String? _budget;
  final List<String> _styles = [];
  final List<String> _concealParts = [];

  final _bodyTypes = ['偏瘦', '微胖', '梨形', '倒三角', '沙漏', '矩形'];
  final _skins = ['冷白', '黄皮', '小麦', '深色'];
  final _budgets = ['经济实惠', '中等消费', '高端品质'];
  final _styleAll = [
    '通勤',
    '学院',
    '甜酷',
    '简约',
    '街头',
    '复古',
    '休闲',
    '正式',
    '运动',
    '度假',
  ];
  final _parts = ['肩', '腰', '臀', '大腿', '小腿', '手臂', '胸部'];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final client = context.read<AuthProvider>().apiClient;
    try {
      final p = await client.getProfile();
      if (p is Map && !p.containsKey('error')) {
        // 性别表达指数 → 同步全局主题
        if (p['gender_expression'] != null) {
          context.read<ThemeProvider>().setGenderExpression(
                (p['gender_expression'] as num).toDouble(),
              );
        }
        if (p['height'] != null)
          _height = (p['height'] as num).toDouble().clamp(140, 200);
        _bodyType = p['body_type']?.toString();
        _skinTone = p['skin_tone']?.toString();
        _budget = p['budget_range']?.toString();
        _styles.clear();
        if (p['style_preference'] != null) {
          _styles.addAll(List<String>.from(p['style_preference'] as List));
        }
        _concealParts.clear();
        if (p['avoid_body_parts'] != null) {
          _concealParts
              .addAll(List<String>.from(p['avoid_body_parts'] as List));
        }
      }
    } catch (_) {}
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    final auth = context.read<AuthProvider>();
    final theme = context.read<ThemeProvider>();
    final data = <String, dynamic>{
      'height': _height.round(),
      'body_type': _bodyType,
      'skin_tone': _skinTone,
      'budget_range': _budget,
      'style_preference': _styles,
      'avoid_body_parts': _concealParts,
      // 仅保存性别表达指数，不保存性别
      'gender_expression': theme.genderExpression,
    };
    try {
      final cur = await auth.apiClient.getProfile();
      if (cur is Map && cur.containsKey('error')) {
        await auth.apiClient.createProfile(data);
      } else {
        await auth.apiClient.updateProfile(data);
      }
      if (mounted) {
        showAppSnackBar(
          context,
          '已保存',
          backgroundColor: context.read<ThemeProvider>().palette.successColor,
        );
      }
    } catch (e) {
      if (mounted) {
        showAppSnackBar(context, '保存失败：${userFacingApiError(e)}');
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final themeProv = context.watch<ThemeProvider>();
    final palette = themeProv.palette;

    return Scaffold(
      backgroundColor: palette.background,
      appBar: AppBar(
        title: const Text('个人设置'),
        centerTitle: true,
        backgroundColor: palette.background,
        surfaceTintColor: Colors.transparent,
        foregroundColor: palette.textTitle,
        actions: [
          IconButton(
            icon: _saving
                ? SizedBox(
                    width: 22,
                    height: 22,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: palette.primary))
                : Icon(Icons.save_outlined, color: palette.primary),
            onPressed: _saving ? null : _save,
          ),
        ],
      ),
      body: _loading
          ? Center(child: CircularProgressIndicator(color: palette.primary))
          : SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 100),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // 说明
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: palette.primary.withValues(alpha: 0.08),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      '用于穿搭推荐参考，与上方风格指数独立调整',
                      style: TextStyle(fontSize: 13, color: palette.textBody),
                    ),
                  ),
                  const SizedBox(height: 24),

                  // ─── 性别表达指数 ────────────────────────────────
                  _sectionTitle(context, palette, Icons.tune, '性别表达指数'),
                  const SizedBox(height: 8),
                  // 滑块联动全局配色
                  SliderTheme(
                    data: SliderThemeData(
                      activeTrackColor: palette.primary,
                      inactiveTrackColor: palette.divider,
                      thumbColor: palette.primary,
                      overlayColor: palette.primary.withValues(alpha: 0.2),
                      trackHeight: 4,
                    ),
                    child: Slider(
                      value: themeProv.genderExpression,
                      min: 0,
                      max: 1,
                      divisions: 100,
                      onChanged: themeProv.setGenderExpression,
                    ),
                  ),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text('偏男性风格',
                          style:
                              TextStyle(fontSize: 12, color: palette.textBody)),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 10, vertical: 3),
                        decoration: BoxDecoration(
                          color: palette.primary.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Text(
                          FashionPalettes.genderLabel(
                              themeProv.genderExpression),
                          style: TextStyle(
                              fontSize: 12,
                              color: palette.primary,
                              fontWeight: FontWeight.bold),
                        ),
                      ),
                      Text('偏女性风格',
                          style:
                              TextStyle(fontSize: 12, color: palette.textBody)),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    '拖动滑块实时切换全局配色（0 = 偏男性风格，1 = 偏女性风格）',
                    style: TextStyle(
                        fontSize: 11,
                        color: palette.textBody.withValues(alpha: 0.7)),
                  ),
                  const SizedBox(height: 28),

                  // ─── 身高 ────────────────────────────────────────
                  _sectionTitle(context, palette, Icons.height, '身高'),
                  const SizedBox(height: 4),
                  Text('${_height.round()} cm',
                      style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                          color: palette.textTitle)),
                  SliderTheme(
                    data: SliderThemeData(
                      activeTrackColor: palette.primary,
                      inactiveTrackColor: palette.divider,
                      thumbColor: palette.primary,
                      overlayColor: palette.primary.withValues(alpha: 0.2),
                      trackHeight: 4,
                    ),
                    child: Slider(
                      value: _height,
                      min: 140,
                      max: 200,
                      divisions: 60,
                      onChanged: (v) => setState(() => _height = v),
                    ),
                  ),
                  const SizedBox(height: 20),

                  // ─── 体型 ────────────────────────────────────────
                  _sectionTitle(
                      context, palette, Icons.accessibility_new, '体型'),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: _bodyTypes
                        .map((t) => _choiceChip(t, _bodyType,
                            (v) => setState(() => _bodyType = v), palette))
                        .toList(),
                  ),
                  const SizedBox(height: 20),

                  // ─── 肤色 ────────────────────────────────────────
                  _sectionTitle(context, palette, Icons.palette_outlined, '肤色'),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: _skins
                        .map((t) => _choiceChip(t, _skinTone,
                            (v) => setState(() => _skinTone = v), palette))
                        .toList(),
                  ),
                  const SizedBox(height: 20),

                  // ─── 风格偏好 ───────────────────────────────────
                  _sectionTitle(
                      context, palette, Icons.style_outlined, '风格偏好（可多选）'),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: _styleAll.map((t) {
                      final sel = _styles.contains(t);
                      return FilterChip(
                        label: Text(t),
                        selected: sel,
                        selectedColor: palette.chipSelectedBg,
                        checkmarkColor: palette.chipSelectedLabel,
                        labelStyle: TextStyle(
                          color: sel
                              ? palette.chipSelectedLabel
                              : palette.textTitle,
                          fontSize: 13,
                        ),
                        onSelected: (on) => setState(() {
                          if (on)
                            _styles.add(t);
                          else
                            _styles.remove(t);
                        }),
                      );
                    }).toList(),
                  ),
                  const SizedBox(height: 20),

                  // ─── 预算范围 ───────────────────────────────────
                  _sectionTitle(
                      context, palette, Icons.payments_outlined, '预算范围'),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: _budgets
                        .map((t) => _choiceChip(t, _budget,
                            (v) => setState(() => _budget = v), palette))
                        .toList(),
                  ),
                  const SizedBox(height: 20),

                  // ─── 希望修饰的部位 ─────────────────────────────
                  _sectionTitle(
                      context, palette, Icons.edit_outlined, '希望修饰的部位（可选）'),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: _parts.map((t) {
                      final sel = _concealParts.contains(t);
                      return FilterChip(
                        label: Text(t),
                        selected: sel,
                        selectedColor: palette.chipSelectedBg,
                        checkmarkColor: palette.chipSelectedLabel,
                        labelStyle: TextStyle(
                          color: sel
                              ? palette.chipSelectedLabel
                              : palette.textTitle,
                          fontSize: 13,
                        ),
                        onSelected: (on) => setState(() {
                          if (on)
                            _concealParts.add(t);
                          else
                            _concealParts.remove(t);
                        }),
                      );
                    }).toList(),
                  ),
                  const SizedBox(height: 100),
                ],
              ),
            ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _saving ? null : _save,
        backgroundColor: palette.primary,
        foregroundColor: Colors.white,
        elevation: 4,
        icon: _saving
            ? SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(
                    strokeWidth: 2, color: Colors.white))
            : const Icon(Icons.save),
        label: const Text('保存', style: TextStyle(fontWeight: FontWeight.w700)),
      ),
    );
  }

  Widget _sectionTitle(
      BuildContext context, Palette p, IconData icon, String text) {
    return Row(
      children: [
        Icon(icon, size: 18, color: p.primary),
        const SizedBox(width: 8),
        Text(text,
            style: TextStyle(
                fontSize: 15, fontWeight: FontWeight.bold, color: p.textTitle)),
      ],
    );
  }

  Widget _choiceChip(String label, String? selected,
      void Function(String?) onSelect, Palette p) {
    final sel = selected == label;
    return ChoiceChip(
      label: Text(label),
      selected: sel,
      selectedColor: p.chipSelectedBg,
      labelStyle: TextStyle(
        color: sel ? p.chipSelectedLabel : p.textTitle,
        fontSize: 13,
      ),
      side: BorderSide(color: sel ? p.chipSelectedBg : p.divider),
      onSelected: (_) => onSelect(sel ? null : label),
    );
  }
}
