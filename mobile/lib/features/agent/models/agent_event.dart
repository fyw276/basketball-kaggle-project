/// Parsed agent pipeline event from the SSE stream.
class AgentEvent {
  /// Unique run identifier (12-char hex).
  final String runId;

  /// Monotonic step counter within this run.
  final int stepId;

  /// Event type: step | tool_call | tool_result | answer | error | done.
  final String event;

  /// Tool being invoked (empty for non-tool steps).
  final String toolName;

  /// Wall-clock milliseconds since run start.
  final int elapsedMs;

  /// Status: running | success | error.
  final String status;

  /// Event-type-specific payload.
  final Map<String, dynamic>? data;

  const AgentEvent({
    required this.runId,
    required this.stepId,
    required this.event,
    required this.toolName,
    required this.elapsedMs,
    required this.status,
    this.data,
  });

  factory AgentEvent.fromJson(Map<String, dynamic> json) {
    return AgentEvent(
      runId: json['run_id'] as String? ?? '',
      stepId: json['step_id'] as int? ?? 0,
      event: json['event'] as String? ?? '',
      toolName: json['tool_name'] as String? ?? '',
      elapsedMs: json['elapsed_ms'] as int? ?? 0,
      status: json['status'] as String? ?? 'running',
      data: json['data'] as Map<String, dynamic>?,
    );
  }

  /// Convenience getters for common data fields.
  String? get label => data?['label'] as String?;
  String? get message => data?['message'] as String?;
  String? get content => data?['content'] as String?;
  Map<String, dynamic>? get arguments =>
      data?['arguments'] as Map<String, dynamic>?;
  String? get resultPreview => data?['result_preview'] as String?;

  @override
  String toString() =>
      'AgentEvent(run=$runId step=$stepId type=$event tool=$toolName '
      'elapsed=${elapsedMs}ms status=$status)';
}
