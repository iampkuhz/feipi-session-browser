package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import com.feipi.session.browser.domain.enums.CallScope;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/**
 * 工具执行边表行。
 *
 * <p>建模由一次调用声明并被另一次调用消费的工具调用边。语义构建器在遍历工具批次时生成这些记录， 制品验证器将它们水合为不可变边元数据。当 provider 未报告执行详情时，可选字段为空。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code toolCallId}、{@code name}、{@code declaredByCallId} 不得为 null。
 *   <li>{@code toolCallId} 不得为空字符串。
 *   <li>{@code durationMs} 必须非负。
 *   <li>{@code filesTouched} 使用不可变副本。
 * </ul>
 *
 * @param toolCallId 稳定的工具调用标识符
 * @param name provider 报告的工具名称
 * @param scope 工具执行的作用域（main/subagent）
 * @param declaredByCallId 声明该工具调用的调用标识符
 * @param resultConsumedByCallId 消费该工具结果的后续调用标识符
 * @param status 可选的非完成状态详情
 * @param exitCode 可选的进程风格退出码
 * @param durationMs 非负的执行时长（毫秒）
 * @param filesTouched 工具执行涉及的文件列表
 * @param subagentId 可选的关联子 agent 实例标识
 */
@DomainModel
public record NormalizedToolExecution(
    @CoreField String toolCallId,
    @CoreField String name,
    @CoreField CallScope scope,
    @CoreField String declaredByCallId,
    Optional<String> resultConsumedByCallId,
    Optional<String> status,
    Optional<Integer> exitCode,
    long durationMs,
    List<String> filesTouched,
    Optional<String> subagentId) {

  /**
   * 紧凑构造器，验证不变量并执行防御性拷贝。
   *
   * @throws NullPointerException 当必填字段为 null 时
   * @throws IllegalArgumentException 当 toolCallId 为空或 durationMs 为负数时
   */
  public NormalizedToolExecution {
    Objects.requireNonNull(toolCallId, "toolCallId 不得为 null");
    if (toolCallId.isEmpty()) {
      throw new IllegalArgumentException("toolCallId 不得为空");
    }
    Objects.requireNonNull(name, "name 不得为 null");
    Objects.requireNonNull(scope, "scope 不得为 null");
    Objects.requireNonNull(declaredByCallId, "declaredByCallId 不得为 null");
    if (durationMs < 0) {
      throw new IllegalArgumentException("tool.durationMs must be non-negative; got " + durationMs);
    }

    // Optional 字段规范化
    resultConsumedByCallId =
        resultConsumedByCallId == null ? Optional.empty() : resultConsumedByCallId;
    status = status == null ? Optional.empty() : status;
    exitCode = exitCode == null ? Optional.empty() : exitCode;
    subagentId = subagentId == null ? Optional.empty() : subagentId;

    // 集合防御性拷贝
    List<String> filesCopy =
        filesTouched == null ? Collections.emptyList() : List.copyOf(filesTouched);
    if (filesCopy.size() > NormalizedConstants.MAX_COLLECTION_SIZE) {
      throw new IllegalArgumentException(
          "filesTouched size "
              + filesCopy.size()
              + " exceeds limit "
              + NormalizedConstants.MAX_COLLECTION_SIZE);
    }
    filesTouched = filesCopy;
  }
}
