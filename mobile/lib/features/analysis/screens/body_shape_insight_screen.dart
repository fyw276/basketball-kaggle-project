import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/providers/auth_provider.dart';
import '../../../core/widgets/analysis_feature_layout.dart';

/// 体型感知
class BodyShapeInsightScreen extends StatefulWidget {
  const BodyShapeInsightScreen({super.key});

  @override
  State<BodyShapeInsightScreen> createState() => _BodyShapeInsightScreenState();
}

class _BodyShapeInsightScreenState extends State<BodyShapeInsightScreen> {
  late Future<dynamic> _future;

  @override
  void initState() {
    super.initState();
    _future = Future.value(null);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      setState(() {
        _future = context.read<AuthProvider>().apiClient.getProfile();
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    return AnalysisFeatureLayout(
      title: '体型感知',
      showGenderBar: false,
      body: FutureBuilder(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          final data = snap.data;
          final body =
              data is Map<String, dynamic> && !data.containsKey('error')
                  ? data
                  : <String, dynamic>{};
          final height = body['height'];
          final bt = body['body_type'] ?? '—';

          return Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '根据您在「设置」中填写的体型与身高，系统会优先推荐修饰比例、强调优点的单品组合。',
                  style: TextStyle(color: Colors.grey.shade700, height: 1.45),
                ),
                const SizedBox(height: 20),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.straighten),
                  title: const Text('身高'),
                  trailing: Text(height != null ? '$height cm' : '未填写'),
                ),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.accessibility_new),
                  title: const Text('体型'),
                  trailing: Text('$bt'),
                ),
                const SizedBox(height: 16),
                const Text(
                  '提示：完善「个人设置」中的体型、希望修饰部位与风格偏好后，推荐与适合度分析会更贴合您。',
                  style: TextStyle(fontSize: 13),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}
