package com.feipi.session.browser.scan.engine;

import java.util.Objects;
import java.util.Optional;

/**
 * Repair 对单个已索引会话的决策。
 *
 * <p>包含原始指纹数据、决策动作和可选的新路径（用于重命名检测）。 每条决策都带有原因描述，用于审计日志。
 *
 * @param fingerprint 已索引会话的指纹数据
 * @param action 对该会话的 repair 决策
 * @param newFilePath 重命名检测时的新文件路径，仅在 {@link RepairAction#RENAME_DETECTED} 时非空
 * @param reason 决策原因描述，用于审计
 */
public record RepairDecision(
    StoredSessionFingerprint fingerprint,
    RepairAction action,
    Optional<String> newFilePath,
    String reason) {

  /**
   * 紧凑构造器，验证不变量。
   *
   * @throws NullPointerException 当必填字段为 null 时
   * @throws IllegalArgumentException 当 {@link RepairAction#RENAME_DETECTED} 时 newFilePath 为空
   */
  public RepairDecision {
    Objects.requireNonNull(fingerprint, "fingerprint 不得为 null");
    Objects.requireNonNull(action, "action 不得为 null");
    Objects.requireNonNull(newFilePath, "newFilePath 不得为 null");
    Objects.requireNonNull(reason, "reason 不得为 null");
    if (action == RepairAction.RENAME_DETECTED && newFilePath.isEmpty()) {
      throw new IllegalArgumentException("RENAME_DETECTED 必须提供 newFilePath");
    }
  }

  /**
   * 创建无需操作的决策。
   *
   * @param fingerprint 已索引会话的指纹数据
   * @return 无需操作的决策
   */
  static RepairDecision noAction(StoredSessionFingerprint fingerprint) {
    return new RepairDecision(fingerprint, RepairAction.NO_ACTION, Optional.empty(), "源文件存在且路径未变化");
  }

  /**
   * 创建确认删除的决策。
   *
   * @param fingerprint 已索引会话的指纹数据
   * @param reason 删除原因
   * @return 确认删除的决策
   */
  static RepairDecision confirmedDelete(StoredSessionFingerprint fingerprint, String reason) {
    return new RepairDecision(fingerprint, RepairAction.CONFIRMED_DELETE, Optional.empty(), reason);
  }

  /**
   * 创建根目录不可用的决策。
   *
   * @param fingerprint 已索引会话的指纹数据
   * @return 根目录不可用的决策
   */
  static RepairDecision rootUnavailable(StoredSessionFingerprint fingerprint) {
    return new RepairDecision(
        fingerprint, RepairAction.ROOT_UNAVAILABLE, Optional.empty(), "根目录不可访问，暂不删除");
  }

  /**
   * 创建临时缺失的决策。
   *
   * @param fingerprint 已索引会话的指纹数据
   * @return 临时缺失的决策
   */
  static RepairDecision sourceMissingTemporary(StoredSessionFingerprint fingerprint) {
    return new RepairDecision(
        fingerprint,
        RepairAction.SOURCE_MISSING_TEMPORARY,
        Optional.empty(),
        "源文件暂时缺失，下次 repair 再判断");
  }

  /**
   * 创建重命名检测的决策。
   *
   * @param fingerprint 已索引会话的指纹数据
   * @param newPath 新文件路径
   * @return 重命名检测的决策
   */
  static RepairDecision renameDetected(StoredSessionFingerprint fingerprint, String newPath) {
    return new RepairDecision(
        fingerprint,
        RepairAction.RENAME_DETECTED,
        Optional.of(newPath),
        "检测到重命名: " + fingerprint.filePath() + " -> " + newPath);
  }
}
