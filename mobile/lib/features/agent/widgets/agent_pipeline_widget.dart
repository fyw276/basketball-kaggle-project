import 'package:flutter/material.dart';

import '../models/agent_step.dart';

/// Vertical stepper-style widget showing the agent's pipeline progress.
///
/// Each step shows an icon (check / spinner / circle / error),
/// a Chinese label, elapsed time, and optional tool name.
class AgentPipelineWidget extends StatelessWidget {
  final List<AgentStep> steps;
  final String? answerContent;

  const AgentPipelineWidget({
    super.key,
    required this.steps,
    this.answerContent,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var i = 0; i < steps.length; i++) ...[
          _StepRow(step: steps[i], theme: theme),
          if (i < steps.length - 1)
            Container(
              margin: const EdgeInsets.only(left: 15),
              width: 2,
              height: 16,
              color: steps[i].isSuccess
                  ? theme.colorScheme.primary.withValues(alpha: 0.3)
                  : theme.dividerColor,
            ),
        ],
        if (answerContent != null && answerContent!.isNotEmpty) ...[
          const SizedBox(height: 12),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: theme.colorScheme.primaryContainer.withValues(alpha: 0.3),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(
              answerContent!,
              style: theme.textTheme.bodyMedium,
            ),
          ),
        ],
      ],
    );
  }
}

class _StepRow extends StatelessWidget {
  final AgentStep step;
  final ThemeData theme;

  const _StepRow({required this.step, required this.theme});

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildIcon(),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                step.label,
                style: theme.textTheme.bodyMedium?.copyWith(
                  fontWeight: FontWeight.w500,
                  color: step.isError
                      ? theme.colorScheme.error
                      : theme.textTheme.bodyMedium?.color,
                ),
              ),
              if (step.toolName.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: Text(
                    step.toolName,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.textTheme.bodySmall?.color
                          ?.withValues(alpha: 0.6),
                      fontFamily: 'monospace',
                    ),
                  ),
                ),
            ],
          ),
        ),
        if (step.elapsedMs > 0)
          Padding(
            padding: const EdgeInsets.only(left: 8, top: 2),
            child: Text(
              _formatMs(step.elapsedMs),
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.textTheme.bodySmall?.color?.withValues(alpha: 0.5),
              ),
            ),
          ),
      ],
    );
  }

  Widget _buildIcon() {
    const size = 24.0;
    if (step.isSuccess) {
      return Icon(Icons.check_circle,
          size: size, color: theme.colorScheme.primary);
    }
    if (step.isError) {
      return Icon(Icons.error, size: size, color: theme.colorScheme.error);
    }
    if (step.isRunning) {
      return SizedBox(
        width: size,
        height: size,
        child: CircularProgressIndicator(
          strokeWidth: 2.5,
          color: theme.colorScheme.primary,
        ),
      );
    }
    // pending
    return Icon(Icons.radio_button_unchecked,
        size: size, color: theme.dividerColor);
  }

  String _formatMs(int ms) {
    if (ms < 1000) return '${ms}ms';
    return '${(ms / 1000).toStringAsFixed(1)}s';
  }
}
