import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/providers/auth_provider.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/services/api_client.dart';
import '../../../core/services/feature_local_store.dart';
import '../models/agent_step.dart';
import '../widgets/agent_pipeline_widget.dart';

/// 示例问题列表
const _exampleQuestions = [
  '我有这件上衣，帮我推荐裤子',
  '明天要开会怎么穿？',
  '这件裙子适合我的肤色吗？',
];

/// 工具名 → 友好描述映射
const _friendlyToolNames = {
  'get_wardrobe_items': '正在查看你的衣橱…',
  'search_weather': '正在查询天气…',
  'get_user_profile': '正在读取你的偏好…',
  'analyze_similarity': '正在分析相似度…',
  'analyze_suitability': '正在分析适合度…',
  'recommend_outfits': '正在推荐搭配方案…',
  'virtual_tryon': '正在生成试衣效果…',
  'mood_recommend': '正在分析心情穿搭…',
};

/// Agent chat screen: send a message, see the pipeline execute, get the answer.
class AgentChatScreen extends StatelessWidget {
  const AgentChatScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => _AgentChatController(),
      child: const _AgentChatPage(),
    );
  }
}

// ── Controller ──────────────────────────────────────────────────────────────

class _ChatMessage {
  final String role; // user | assistant
  final String content;
  final List<AgentStep>? steps;
  final String? answerContent;
  final bool isGreeting;

  _ChatMessage({
    required this.role,
    required this.content,
    this.steps,
    this.answerContent,
    this.isGreeting = false,
  });

  Map<String, dynamic> toJson() => {'role': role, 'content': content};

  factory _ChatMessage.fromJson(Map<String, dynamic> json) {
    return _ChatMessage(
      role: json['role']?.toString() ?? 'assistant',
      content: json['content']?.toString() ?? '',
    );
  }
}

class _AgentChatController extends ChangeNotifier {
  static const _historyLimit = 100;
  static const _welcomeText = '你好！我是你的 AI 穿搭助手。你可以问我搭配、天气、衣橱和穿搭建议。';

  final List<_ChatMessage> messages = [];
  final TextEditingController inputCtrl = TextEditingController();
  bool isRunning = false;
  bool isHistoryLoading = true;
  List<AgentStep> currentSteps = [];
  String? currentAnswer;
  String? currentError;

  ApiClient? _api;
  String _historyFeatureId = 'agent_chat_history_guest';

  bool get hasConversation => messages.any((message) => !message.isGreeting);

  Future<void> init(ApiClient api, {String? username}) async {
    _api = api;
    final safeUsername = (username ?? 'guest').replaceAll(
      RegExp(r'[^a-zA-Z0-9_-]'),
      '_',
    );
    _historyFeatureId = 'agent_chat_history_$safeUsername';

    final cached = await FeatureLocalStore.loadJson(_historyFeatureId);
    final rawMessages = cached?['messages'];
    if (rawMessages is List) {
      for (final raw in rawMessages) {
        if (raw is! Map) continue;
        final message = _ChatMessage.fromJson(Map<String, dynamic>.from(raw));
        if ((message.role == 'user' || message.role == 'assistant') &&
            message.content.trim().isNotEmpty) {
          messages.add(message);
        }
      }
    }
    _ensureWelcomeMessage();
    isHistoryLoading = false;
    notifyListeners();
  }

  void _ensureWelcomeMessage() {
    if (messages.isEmpty) {
      messages.add(_ChatMessage(
        role: 'assistant',
        content: _welcomeText,
        isGreeting: true,
      ));
    }
  }

  Future<void> _persistMessages() async {
    final history = messages.where((message) => !message.isGreeting).toList();
    final bounded = history.length > _historyLimit
        ? history.sublist(history.length - _historyLimit)
        : history;
    await FeatureLocalStore.saveJson(_historyFeatureId, {
      'version': 1,
      'messages': bounded.map((message) => message.toJson()).toList(),
    });
  }

  Future<void> clearHistory() async {
    if (isRunning) return;
    await FeatureLocalStore.clear(_historyFeatureId);
    messages.clear();
    _ensureWelcomeMessage();
    notifyListeners();
  }

  Future<void> send() async {
    final text = inputCtrl.text.trim();
    if (text.isEmpty || isRunning || isHistoryLoading || _api == null) return;

    inputCtrl.clear();
    messages.add(_ChatMessage(role: 'user', content: text));
    isRunning = true;
    currentSteps = [];
    currentAnswer = null;
    currentError = null;
    notifyListeners();
    await _persistMessages();

    try {
      final history = messages
          .where((m) => !m.isGreeting && m.role != 'system')
          .map((m) => {'role': m.role, 'content': m.content})
          .toList();

      await for (final raw in _api!.agentChatStream(
        message: text,
        conversationHistory:
            history.length > 1 ? history.sublist(0, history.length - 1) : null,
      )) {
        _handleEvent(raw);
      }
    } catch (e) {
      currentError = '连接出错: $e';
    } finally {
      // Finalize the pipeline as a persistent assistant message.
      if (currentAnswer != null && currentAnswer!.isNotEmpty) {
        messages.add(_ChatMessage(
          role: 'assistant',
          content: currentAnswer!,
          steps: List.from(currentSteps),
          answerContent: currentAnswer,
        ));
      } else if (currentError != null && currentError!.isNotEmpty) {
        messages.add(_ChatMessage(
          role: 'assistant',
          content: currentError!,
          steps: List.from(currentSteps),
          answerContent: currentError,
        ));
      }
      isRunning = false;
      currentSteps = [];
      currentAnswer = null;
      currentError = null;
      await _persistMessages();
      notifyListeners();
    }
  }

  void _handleEvent(Map<String, dynamic> raw) {
    final eventType = raw['event'] as String? ?? '';
    final data = raw['data'] as Map<String, dynamic>?;

    switch (eventType) {
      case 'step':
        final label = data?['label'] as String? ?? '处理中...';
        final stepId = raw['step_id'] as int? ?? currentSteps.length;
        // Find existing step or add new one
        final existing = currentSteps.where((s) => s.stepId == stepId).toList();
        if (existing.isNotEmpty) {
          existing.first
            ..label = label
            ..status = raw['status'] as String? ?? 'running'
            ..elapsedMs = raw['elapsed_ms'] as int? ?? 0;
        } else {
          currentSteps.add(AgentStep(
            stepId: stepId,
            label: label,
            toolName: raw['tool_name'] as String? ?? '',
            status: raw['status'] as String? ?? 'running',
            elapsedMs: raw['elapsed_ms'] as int? ?? 0,
          ));
        }
        notifyListeners();

      case 'tool_call':
        final toolName = raw['tool_name'] as String? ?? '';
        final stepId = raw['step_id'] as int? ?? currentSteps.length;
        final friendlyLabel = _friendlyToolNames[toolName] ?? '调用 $toolName';
        final existing = currentSteps.where((s) => s.stepId == stepId).toList();
        if (existing.isNotEmpty) {
          existing.first
            ..toolName = toolName
            ..label = friendlyLabel
            ..status = 'running';
        } else {
          currentSteps.add(AgentStep(
            stepId: stepId,
            label: friendlyLabel,
            toolName: toolName,
            status: 'running',
          ));
        }
        notifyListeners();

      case 'tool_result':
        final stepId = raw['step_id'] as int? ?? 0;
        final existing = currentSteps.where((s) => s.stepId == stepId).toList();
        if (existing.isNotEmpty) {
          existing.first
            ..status = raw['status'] as String? ?? 'success'
            ..elapsedMs = raw['elapsed_ms'] as int? ?? 0
            ..resultPreview = data?['result_preview'] as String?;
        }
        notifyListeners();

      case 'answer':
        currentAnswer = data?['content'] as String? ?? '';
        // Mark all steps as complete
        for (final s in currentSteps) {
          if (s.isRunning) s.status = 'success';
        }
        notifyListeners();

      case 'error':
        final msg = data?['message'] as String? ?? '未知错误';
        currentError = msg;
        currentSteps.add(AgentStep(
          stepId: currentSteps.length,
          label: '错误: $msg',
          status: 'error',
        ));
        notifyListeners();

      case 'done':
        for (final s in currentSteps) {
          if (s.isRunning) s.status = 'success';
        }
        notifyListeners();
    }
  }
}

// ── Page ────────────────────────────────────────────────────────────────────

class _AgentChatPage extends StatefulWidget {
  const _AgentChatPage();

  @override
  State<_AgentChatPage> createState() => _AgentChatPageState();
}

class _AgentChatPageState extends State<_AgentChatPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final auth = context.read<AuthProvider>();
      final ctrl = context.read<_AgentChatController>();
      ctrl.init(auth.apiClient, username: auth.username);
    });
  }

  @override
  Widget build(BuildContext context) {
    final ctrl = context.watch<_AgentChatController>();
    final palette = context.watch<ThemeProvider>().palette;
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('AI 穿搭助手'),
        actions: [
          IconButton(
            tooltip: '清空聊天记录',
            onPressed: ctrl.hasConversation && !ctrl.isRunning
                ? () => ctrl.clearHistory()
                : null,
            icon: const Icon(Icons.delete_outline),
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: ctrl.messages.length + (ctrl.isRunning ? 1 : 0),
              itemBuilder: (context, index) {
                if (index < ctrl.messages.length) {
                  return _buildMessage(ctrl.messages[index], theme);
                }
                return _buildRunningPipeline(ctrl, theme);
              },
            ),
          ),
          // 示例问题（仅在无消息时显示）
          if (ctrl.messages.isEmpty && !ctrl.isRunning)
            _buildWelcomeSection(palette, ctrl, theme),
          // 输入框
          _buildInputBar(ctrl, theme, palette),
        ],
      ),
    );
  }

  Widget _buildWelcomeSection(
    dynamic palette,
    _AgentChatController ctrl,
    ThemeData theme,
  ) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.auto_awesome, color: palette.primary, size: 20),
              const SizedBox(width: 8),
              Text(
                '你可以这样问我',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: palette.textBody,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: _exampleQuestions.map((q) {
              return InkWell(
                onTap: () {
                  ctrl.inputCtrl.text = q;
                  ctrl.send();
                },
                borderRadius: BorderRadius.circular(20),
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 14,
                    vertical: 8,
                  ),
                  decoration: BoxDecoration(
                    color: palette.primary.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                      color: palette.primary.withValues(alpha: 0.2),
                    ),
                  ),
                  child: Text(
                    q,
                    style: TextStyle(
                      fontSize: 13,
                      color: palette.primary,
                    ),
                  ),
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }

  Widget _buildMessage(_ChatMessage msg, ThemeData theme) {
    final isUser = msg.role == 'user';
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(12),
        constraints: const BoxConstraints(maxWidth: 320),
        decoration: BoxDecoration(
          color: isUser
              ? theme.colorScheme.primary
              : theme.colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (!isUser && msg.steps != null && msg.steps!.isNotEmpty) ...[
              AgentPipelineWidget(
                steps: msg.steps!,
                answerContent: msg.answerContent,
              ),
            ] else
              Text(
                msg.content,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: isUser
                      ? theme.colorScheme.onPrimary
                      : theme.textTheme.bodyMedium?.color,
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildRunningPipeline(_AgentChatController ctrl, ThemeData theme) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(12),
        constraints: const BoxConstraints(maxWidth: 320),
        decoration: BoxDecoration(
          color: theme.colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(16),
        ),
        child: AgentPipelineWidget(
          steps: ctrl.currentSteps,
          answerContent: ctrl.currentAnswer,
        ),
      ),
    );
  }

  Widget _buildInputBar(
      _AgentChatController ctrl, ThemeData theme, dynamic palette) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
      decoration: BoxDecoration(
        color: theme.scaffoldBackgroundColor,
        border: Border(top: BorderSide(color: theme.dividerColor)),
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: ctrl.inputCtrl,
              enabled: !ctrl.isRunning && !ctrl.isHistoryLoading,
              decoration: InputDecoration(
                hintText: ctrl.isHistoryLoading ? '正在加载历史对话...' : '问我穿搭问题...',
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(24),
                ),
                contentPadding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 10,
                ),
              ),
              onSubmitted: (_) => ctrl.send(),
            ),
          ),
          const SizedBox(width: 8),
          IconButton.filled(
            onPressed: ctrl.isRunning || ctrl.isHistoryLoading
                ? null
                : () => ctrl.send(),
            icon: ctrl.isRunning
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : Icon(Icons.send, color: theme.colorScheme.onPrimary),
            style: IconButton.styleFrom(
              backgroundColor:
                  ctrl.isRunning ? theme.disabledColor : palette.primary,
            ),
          ),
        ],
      ),
    );
  }
}
