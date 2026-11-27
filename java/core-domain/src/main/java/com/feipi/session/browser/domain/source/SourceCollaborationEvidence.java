package com.feipi.session.browser.domain.source;

import com.feipi.session.browser.domain.annotation.DomainModel;
import java.util.Optional;

/**
 * 明确协议中的紧凑协作事实，不保存任务或结果正文。
 *
 * @param toolCallId 原始工具标识
 * @param kind 操作种类
 * @param phase 声明或本次结果报告
 * @param targetId 完整目标实例标识，未知时为空
 * @param reportedStatus 本次结果明确报告的状态，不是生命周期
 * @param sourceLocator 原始事实记录定位符
 * @param reason 关联或缺失原因
 */
@DomainModel
public record SourceCollaborationEvidence(
    String toolCallId,
    String kind,
    String phase,
    Optional<String> targetId,
    Optional<String> reportedStatus,
    String reason,
    String sourceLocator) {
  /** 未绑定原点时由记录入口补齐的源码便利构造器。 */
  public SourceCollaborationEvidence(
      String toolCallId,
      String kind,
      String phase,
      Optional<String> targetId,
      Optional<String> reportedStatus,
      String reason) {
    this(toolCallId, kind, phase, targetId, reportedStatus, reason, "");
  }

  /** 仅替换原始事实锚点。 */
  public SourceCollaborationEvidence withSourceLocator(String locator) {
    return new SourceCollaborationEvidence(
        toolCallId, kind, phase, targetId, reportedStatus, reason, locator);
  }

  /** 规范化未知字段；全文不得进入此模型。 */
  public SourceCollaborationEvidence {
    sourceLocator = sourceLocator == null ? "" : sourceLocator;
    targetId = targetId == null ? Optional.empty() : targetId;
    reportedStatus = reportedStatus == null ? Optional.empty() : reportedStatus;
    if (!java.util.Set.of("delegate", "wait", "input").contains(kind)
        || !java.util.Set.of("declaration", "result_report").contains(phase)) {
      throw new IllegalArgumentException("未知协作事实种类");
    }
  }

  /** 使用唯一工具 occurrence 替换原始工具标识。 */
  public SourceCollaborationEvidence withToolCallId(String id) {
    return new SourceCollaborationEvidence(
        id, kind, phase, targetId, reportedStatus, reason, sourceLocator);
  }
}
