package com.feipi.session.browser.cli.diagnose;

import java.util.List;
import java.util.Map;

/**
 * diagnose session 输出数据模型。
 *
 * <p>所有 record 均为不可变的，直接序列化为 JSON 或渲染为人类可读格式。
 */
public final class DiagnoseOutputModel {

  private DiagnoseOutputModel() {}

  /** diagnose 输出的 schema 版本。 */
  public static final String SCHEMA_VERSION = "diagnose-session.v1";

  /**
   * 顶层诊断输出。
   *
   * @param schemaVersion diagnose 输出的 schema 版本
   * @param request 请求参数回显
   * @param source 源文件定位结果
   * @param raw 原始 JSONL 结构统计
   * @param normalization 归一化结果摘要
   * @param projection 投影摘要
   * @param divergence 分歧检测结果
   * @param timing 各阶段耗时
   * @param warnings 警告信息列表
   */
  public record DiagnoseOutput(
      String schemaVersion,
      RequestInfo request,
      SourceInfo source,
      RawInfo raw,
      NormalizationInfo normalization,
      ProjectionInfo projection,
      DivergenceInfo divergence,
      TimingInfo timing,
      List<String> warnings) {}

  /**
   * 请求参数回显。
   *
   * @param agent agent 类型（如 "claude_code"）
   * @param sessionId 目标 session ID
   * @param sourceDir 源数据根目录
   */
  public record RequestInfo(String agent, String sessionId, String sourceDir) {}

  /**
   * 源文件定位结果。
   *
   * @param status 定位状态（OBSERVED / ERROR / UNAVAILABLE）
   * @param transcriptPath transcript 文件的绝对路径
   * @param transcriptSizeBytes transcript 文件大小（字节）
   * @param subagentsDir subagent 目录的绝对路径
   * @param subagentFileCount subagent JSONL 文件数量
   * @param subagentFiles subagent 文件详情列表
   * @param metaStatus 元数据状态
   * @param meta 元数据键值对
   */
  public record SourceInfo(
      String status,
      String transcriptPath,
      long transcriptSizeBytes,
      String subagentsDir,
      int subagentFileCount,
      List<SubagentFileInfo> subagentFiles,
      String metaStatus,
      Map<String, String> meta) {}

  /**
   * subagent 文件信息。
   *
   * @param fileName 文件名
   * @param sizeBytes 文件大小（字节）
   * @param metaStatus 对应 .meta.json 的状态
   */
  public record SubagentFileInfo(String fileName, long sizeBytes, String metaStatus) {}

  /**
   * 原始 JSONL 结构统计。
   *
   * @param status 解析状态
   * @param totalEvents 事件总数
   * @param eventTypeCounts 各类型事件计数
   * @param assistantMessages assistant 消息数
   * @param userMessages user 消息数
   * @param toolUseCount tool_use 调用数
   * @param toolResultCount tool_result 调用数
   * @param parseErrors 解析错误数
   * @param sourceErrors 源层错误列表
   */
  public record RawInfo(
      String status,
      int totalEvents,
      Map<String, Integer> eventTypeCounts,
      int assistantMessages,
      int userMessages,
      int toolUseCount,
      int toolResultCount,
      int parseErrors,
      List<String> sourceErrors) {}

  /**
   * 归一化结果摘要。
   *
   * @param status 归一化状态
   * @param schemaVersion 归一化 schema 版本
   * @param callCount 总调用数
   * @param mainCallCount 主会话调用数
   * @param subagentCallCount subagent 调用数
   * @param toolExecutionCount 工具执行数
   * @param diagnosticCount 诊断信息数
   * @param totalTokens 总 token 数
   * @param sourceFileCount 源文件数
   */
  public record NormalizationInfo(
      String status,
      String schemaVersion,
      int callCount,
      int mainCallCount,
      int subagentCallCount,
      int toolExecutionCount,
      int diagnosticCount,
      long totalTokens,
      int sourceFileCount) {}

  /**
   * 投影摘要（无 index 的轻量结构投影）。
   *
   * @param status 投影状态
   * @param detectedAgents 检测到的 agent 数
   * @param detectedSubagents 检测到的 subagent 数
   * @param mainToolCallCount 主会话工具调用数
   * @param subagentToolCallCount subagent 工具调用数
   * @param totalCallCount 总调用数
   */
  public record ProjectionInfo(
      String status,
      int detectedAgents,
      int detectedSubagents,
      int mainToolCallCount,
      int subagentToolCallCount,
      int totalCallCount) {}

  /**
   * 分歧检测结果。
   *
   * @param status 分歧状态（MATCH / MISMATCH / SKIPPED）
   * @param first 首个分歧详情，无分歧时为 null
   */
  public record DivergenceInfo(String status, FirstDivergence first) {}

  /**
   * 首个分歧详情。
   *
   * @param stage 分歧所在阶段
   * @param status 该阶段的期望状态
   * @param expected 预期值
   * @param observed 实际观测值
   * @param evidence 证据描述
   * @param nextInspection 下一步检查建议
   */
  public record FirstDivergence(
      String stage,
      String status,
      String expected,
      String observed,
      String evidence,
      String nextInspection) {}

  /**
   * 各阶段耗时。
   *
   * @param totalMs 总耗时（毫秒）
   * @param sourceMs source 层耗时（毫秒）
   * @param rawMs raw 层耗时（毫秒）
   * @param normalizationMs 归一化层耗时（毫秒）
   * @param projectionMs 投影层耗时（毫秒）
   */
  public record TimingInfo(
      long totalMs, long sourceMs, long rawMs, long normalizationMs, long projectionMs) {}
}
