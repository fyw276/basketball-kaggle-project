import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/providers/auth_provider.dart';
import '../../../core/services/api_client.dart';
import '../models/agent_step.dart';
import '../widgets/agent_pipeline_widget.dart';

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

  _ChatMessage({
    required this.role,
    required this.content,
    this.steps,
    this.answerContent,
  });
}

class _AgentChatController extends ChangeNotifier {
  final List<_ChatMessage> messages = [];
  final TextEditingController inputCtrl = TextEditingController();
  bool isRunning = false;
  List<AgentStep> currentSteps = [];
  String? currentAnswer;

  ApiClient? _api;

  void init(ApiClient api) {
    _api = api;
  }

  Future<void> send() async {
    final text = inputCtrl.text.trim();
    if (text.isEmpty || isRunning || _api == null) return;

    inputCtrl.clear();
    messages.add(_ChatMessage(role: 'user', content: text));
    isRunning = true;
    currentSteps = [];
    currentAnswer = null;
    notifyListeners();

    try {
      final history = messages
          .where((m) => m.role != 'system')
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
      messages.add(_ChatMessage(
        role: 'assistant',
        content: '连接出错: $e',
      ));
    } finally {
      isRunning = false;
      // Finalize: add assistant message if we got an answer
      if (currentAnswer != null && currentAnswer!.isNotEmpty) {
        messages.add(_ChatMessage(
          role: 'assistant',
          content: currentAnswer!,
          steps: List.from(currentSteps),
          answerContent: currentAnswer,
        ));
      }
      currentSteps = [];
      currentAnswer = null;
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
        final existing = currentSteps.where((s) => s.stepId == stepId).toList();
        if (existing.isNotEmpty) {
          existing.first
            ..toolName = toolName
            ..status = 'running';
        } else {
          currentSteps.add(AgentStep(
            stepId: stepId,
            label: '调用 $toolName',
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
      ctrl.init(auth.apiClient);
    });
  }

  @override
  Widget build(BuildContext context) {
    final ctrl = context.watch<_AgentChatController>();
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('AI 穿搭助手')),
      body: Column(
        children: [
          // Message list
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: ctrl.messages.length + (ctrl.isRunning ? 1 : 0),
              itemBuilder: (context, index) {
                if (index < ctrl.messages.length) {
                  return _buildMessage(ctrl.messages[index], theme);
                }
                // Running indicator
                return _buildRunningPipeline(ctrl, theme);
              },
            ),
          ),
          // Input bar
          _buildInputBar(ctrl, theme),
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

  Widget _buildInputBar(_AgentChatController ctrl, ThemeData theme) {
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
              enabled: !ctrl.isRunning,
              decoration: InputDecoration(
                hintText: '问我穿搭问题...',
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
            onPressed: ctrl.isRunning ? null : () => ctrl.send(),
            icon: ctrl.isRunning
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.send),
          ),
        ],
      ),
    );
  }
}
