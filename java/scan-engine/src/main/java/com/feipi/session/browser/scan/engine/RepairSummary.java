package com.feipi.session.browser.scan.engine;

import java.util.List;
import java.util.Objects;

/**
 * Repair 操作的汇总结果。
 *
 * <p>记录各类 repair 动作的计数、决策列表、错误列表和执行时长。 用于审计和监控 repair 行为，所有 destructive action 均有明确摘要。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>所有计数非负。
 *   <li>{@code decisions} 和 {@code errors} 不得为 null。
 *   <li>{@code durationMs} 非负。
 * </ul>
 *
 * @param deletedCount 确认删除的会话数
 * @param renamedCount 检测到重命名并更新路径的会话数
 * @param keptCount 无需操作的会话数
 * @param rootUnavailableCount 根目录不可用而保留的会话数
 * @param temporaryMissingCount 临时缺失而保留的会话数
 * @param artifactOrphanCount 删除的孤儿 artifact 数
 * @param decisions 全部决策列表（按 sessionKey 排序）
 * @param errors 执行过程中的错误列表
 * @param durationMs 执行时长（毫秒）
 */
public record RepairSummary(
    int deletedCount,
    int renamedCount,
    int keptCount,
    int rootUnavailableCount,
    int temporaryMissingCount,
    int artifactOrphanCount,
    List<RepairDecision> decisions,
    List<String> errors,
    long durationMs) {

  /**
   * 紧凑构造器，验证不变量并执行防御性拷贝。
   *
   * @throws NullPointerException 当列表字段为 null 时
   * @throws IllegalArgumentException 当计数为负或 duration 为负时
   */
  public RepairSummary {
    if (deletedCount < 0
        || renamedCount < 0
        || keptCount < 0
        || rootUnavailableCount < 0
        || temporaryMissingCount < 0
        || artifactOrphanCount < 0) {
      throw new IllegalArgumentException("全部计数必须非负");
    }
    Objects.requireNonNull(decisions, "decisions 不得为 null");
    Objects.requireNonNull(errors, "errors 不得为 null");
    if (durationMs < 0) {
      throw new IllegalArgumentException("durationMs 不得为负: " + durationMs);
    }
    decisions = List.copyOf(decisions);
    errors = List.copyOf(errors);
  }

  /**
   * 全部处理过的会话总数（不含 kept）。
   *
   * @return 执行了实际动作的会话数
   */
  public int totalActions() {
    return deletedCount + renamedCount + rootUnavailableCount + temporaryMissingCount;
  }

  /**
   * 是否产生了任何破坏性动作（删除或重命名）。
   *
   * @return 存在删除或重命名时返回 true
   */
  public boolean hasDestructiveActions() {
    return deletedCount > 0 || renamedCount > 0 || artifactOrphanCount > 0;
  }

  /**
   * 是否包含错误。
   *
   * @return 存在错误时返回 true
   */
  public boolean hasErrors() {
    return !errors.isEmpty();
  }
}
