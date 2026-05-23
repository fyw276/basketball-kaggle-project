/// A single step in the agent pipeline, updated in-place as events arrive.
class AgentStep {
  final int stepId;
  String label;
  String toolName;
  String status; // pending | running | success | error
  int elapsedMs;
  String? resultPreview;

  AgentStep({
    required this.stepId,
    required this.label,
    this.toolName = '',
    this.status = 'pending',
    this.elapsedMs = 0,
    this.resultPreview,
  });

  bool get isPending => status == 'pending';
  bool get isRunning => status == 'running';
  bool get isSuccess => status == 'success';
  bool get isError => status == 'error';
}
