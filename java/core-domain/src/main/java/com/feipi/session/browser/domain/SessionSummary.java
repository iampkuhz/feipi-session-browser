package com.feipi.session.browser.domain;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import java.util.Map;
import java.util.Objects;

/**
 * 会话摘要领域模型。
 *
 * <p>表示一个 agent 会话的归一化摘要信息，包含会话标识、时间范围、token 统计、 工具调用计数和解析诊断等核心数据。该类型被索引写入器、查询器和扫描器消费， 是 S1
 * 阶段索引管线的核心数据传输对象。
 *
 * <p>字段分为两类：
 *
 * <ul>
 *   <li>{@code CoreField} 标注的核心字段影响业务标识、状态、计量或时间语义。
 *   <li>未标注的字段为派生统计或辅助信息。
 * </ul>
 *
 * @param agent 产生本次会话的 agent 类型标识，如 claude、codex、qoder
 * @param sessionId 会话全局唯一标识符
 * @param title 会话标题，通常由用户或系统自动生成
 * @param projectKey 所属项目的归一化标识键
 * @param projectName 所属项目的显示名称
 * @param cwd 会话执行时的工作目录绝对路径
 * @param startedAt 会话起始时间戳（ISO 8601 格式）
 * @param endedAt 会话结束时间戳（ISO 8601 格式）
 * @param durationSeconds 会话总耗时，单位为秒
 * @param modelExecutionSeconds 模型推理阶段耗时，单位为秒
 * @param toolExecutionSeconds 工具执行阶段耗时，单位为秒
 * @param model 使用的模型标识符
 * @param gitBranch 会话关联的 Git 分支名称
 * @param source 数据来源类型，如 claude_code_jsonl、codex_rollout 等
 * @param userMessageCount 用户消息总数
 * @param assistantMessageCount 助手消息总数
 * @param toolCallCount 工具调用总次数
 * @param outputTokens 输出 token 总数
 * @param hasSensitiveData 是否包含敏感数据标记
 * @param freshInputTokens 非缓存的输入 token 数
 * @param cacheReadTokens 缓存命中的读取 token 数
 * @param cacheWriteTokens 缓存写入 token 数
 * @param totalTokens 归一化后的 token 总计
 * @param failedToolCount 执行失败的工具调用次数
 * @param subagentInstanceCount 子 agent 实例数量
 * @param parseDiagnostics 解析过程中的诊断信息键值对，不可变
 * @param filePath 源文件的绝对路径
 */
@DomainModel
public record SessionSummary(
    @CoreField String agent,
    @CoreField String sessionId,
    @CoreField String title,
    @CoreField String projectKey,
    @CoreField String projectName,
    @CoreField String cwd,
    @CoreField String startedAt,
    @CoreField String endedAt,
    @CoreField double durationSeconds,
    double modelExecutionSeconds,
    double toolExecutionSeconds,
    @CoreField String model,
    @CoreField String gitBranch,
    @CoreField String source,
    long userMessageCount,
    long assistantMessageCount,
    long toolCallCount,
    @CoreField long outputTokens,
    boolean hasSensitiveData,
    @CoreField long freshInputTokens,
    @CoreField long cacheReadTokens,
    @CoreField long cacheWriteTokens,
    @CoreField long totalTokens,
    long failedToolCount,
    long subagentInstanceCount,
    Map<String, Object> parseDiagnostics,
    String filePath) {

  /**
   * 紧凑构造器，执行非空约束和防御性拷贝。
   *
   * <p>{@code parseDiagnostics} 使用不可变副本替换，确保 record 不可变性。 {@code agent}、{@code sessionId} 和 {@code
   * projectKey} 不允许为 null。
   */
  public SessionSummary {
    Objects.requireNonNull(agent, "agent 不得为 null");
    Objects.requireNonNull(sessionId, "sessionId 不得为 null");
    Objects.requireNonNull(projectKey, "projectKey 不得为 null");
    parseDiagnostics = parseDiagnostics == null ? Map.of() : Map.copyOf(parseDiagnostics);
  }

  /**
   * 计算会话唯一键，由 agent 和 sessionId 拼接。
   *
   * @return 格式为 {@code agent:sessionId} 的会话唯一键
   */
  public String sessionKey() {
    return agent + ":" + sessionId;
  }

  /**
   * 计算各分量 token 之和。
   *
   * @return 输入、缓存读取、缓存写入和输出 token 的合计值
   */
  public long tokenComponentTotal() {
    return freshInputTokens + cacheReadTokens + cacheWriteTokens + outputTokens;
  }
}
