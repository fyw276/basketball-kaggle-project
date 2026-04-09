import 'dart:math';

List<Map<String, dynamic>> generateBodyShapeOutfits(
  Map<String, dynamic> profile, {
  required int seed,
}) {
  final rng = Random(seed);

  final height = profile['height'];
  final heightCm = height is num ? height.toInt() : null;
  final bodyType = (profile['body_type'] ?? '').toString().trim();
  final stylesRaw = profile['style_preference'];
  final styles = stylesRaw is List
      ? stylesRaw
          .map((e) => e.toString())
          .where((s) => s.trim().isNotEmpty)
          .toList()
      : <String>[];

  final primaryStyle = styles.isNotEmpty ? styles.first : '简约';

  final fitHint = _fitHintFor(bodyType);
  final silhouetteHint = _silhouetteHint(heightCm, bodyType);

  final templates = _templatesFor(primaryStyle);
  final picked = <Map<String, dynamic>>[];
  for (var i = 0; i < 3; i++) {
    final t = templates[rng.nextInt(templates.length)];
    picked.add({
      'title': t['title'],
      'items': t['items'],
      'fit_explain': _fitExplain(
        bodyType: bodyType,
        fitHint: fitHint,
        silhouetteHint: silhouetteHint,
        primaryStyle: primaryStyle,
      ),
    });
  }

  return picked;
}

String _fitHintFor(String bodyType) {
  switch (bodyType) {
    case '偏瘦':
      return '推荐略宽松或叠穿增加体积感';
    case '倒三角':
      return '上半身简化、下半身增加存在感以平衡肩宽';
    case '梨形':
      return '上半身提亮/增加细节，下半身选垂坠宽松更显利落';
    case '矩形':
      return '用腰线与层次塑造曲线';
    case '沙漏':
      return '突出腰线与合身剪裁，比例优势明显';
    case '微胖':
      return '选垂坠面料与适度宽松，避免过紧';
    default:
      return '以比例与线条为主，优先舒适与整体协调';
  }
}

String _silhouetteHint(int? heightCm, String bodyType) {
  if (heightCm == null) return '';
  if (heightCm >= 180) return '长度建议适中，避免过长拖沓';
  if (heightCm <= 160) return '提高腰线、减少分割更显利落';
  if (bodyType == '微胖') return '纵向线条更显显瘦';
  return '';
}

String _fitExplain({
  required String bodyType,
  required String fitHint,
  required String silhouetteHint,
  required String primaryStyle,
}) {
  final parts = <String>[];
  if (bodyType.isNotEmpty) parts.add('体型：$bodyType');
  parts.add(fitHint);
  if (silhouetteHint.trim().isNotEmpty) parts.add(silhouetteHint);
  if (primaryStyle.trim().isNotEmpty) parts.add('风格：$primaryStyle');
  return parts.join('；');
}

List<Map<String, dynamic>> _templatesFor(String style) {
  final s = style.trim();
  if (s == '通勤') {
    return [
      {
        'title': '通勤利落',
        'items': ['衬衫', '直筒西裤', '乐福鞋', '简约托特包'],
      },
      {
        'title': '通勤温柔',
        'items': ['针织开衫', '半身裙/直筒裙', '低跟鞋', '小耳饰'],
      },
      {
        'title': '通勤休闲',
        'items': ['POLO/针织短袖', '九分裤', '小白鞋', '腕表'],
      },
    ];
  }
  if (s == '街头' || s == '运动') {
    return [
      {
        'title': '街头舒适',
        'items': ['宽松卫衣', '工装裤', '运动鞋', '棒球帽'],
      },
      {
        'title': '运动机能',
        'items': ['轻薄外套', '束脚裤', '跑鞋', '斜挎包'],
      },
      {
        'title': '运动简洁',
        'items': ['运动T恤', '短裤/速干裤', '运动鞋', '运动袜'],
      },
    ];
  }
  if (s == '复古') {
    return [
      {
        'title': '复古学院',
        'items': ['针织背心', '衬衫', '直筒裤', '皮鞋'],
      },
      {
        'title': '复古休闲',
        'items': ['牛仔外套', '纯色T恤', '牛仔裤', '帆布鞋'],
      },
      {
        'title': '复古优雅',
        'items': ['风衣', '高腰下装', '踝靴', '皮质包'],
      },
    ];
  }
  if (s == '学院') {
    return [
      {
        'title': '学院清爽',
        'items': ['白衬衫', '百褶裙/直筒裤', '小白鞋', '帆布包'],
      },
      {
        'title': '学院叠穿',
        'items': ['针织开衫', '打底', '九分裤', '乐福鞋'],
      },
      {
        'title': '学院休闲',
        'items': ['卫衣', '牛仔裤', '板鞋', '棒球帽'],
      },
    ];
  }
  // default: 简约/休闲/正式/度假/甜酷等走通用模板
  return [
    {
      'title': '简约日常',
      'items': ['纯色上衣', '直筒下装', '舒适鞋履', '简洁配饰'],
    },
    {
      'title': '层次显比例',
      'items': ['短外套/开衫', '内搭', '高腰下装', '利落鞋履'],
    },
    {
      'title': '轻正式',
      'items': ['西装外套', 'T恤/衬衫', '九分裤/半身裙', '皮鞋/低跟鞋'],
    },
  ];
}
