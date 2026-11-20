package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.domain.annotation.DomainModel;
import java.util.Optional;

/**
 * 工具所属声明调用确定执行者；目标及状态仅表示这条源事实。
 *
 * @param kind 操作种类
 * @param phase 声明或本次结果报告
 * @param actorId 声明调用的完整实例标识，主上下文或未知时为空
 * @param targetId 完整目标实例标识
 * @param sourceLocator 原始声明或结果记录定位锚点
 * @param reportedStatus 本次结果报告状态，不表示持续状态
 * @param actorIdentityReason 执行者身份依据；匿名上下文不是 provider 实例
 * @param reason 关联或缺失原因
 */
@DomainModel
public record NormalizedCollaborationAction(
    String kind,
    String phase,
    Optional<String> actorId,
    Optional<String> targetId,
    String sourceLocator,
    Optional<String> reportedStatus,
    String reason,
    String actorIdentityReason) {}
