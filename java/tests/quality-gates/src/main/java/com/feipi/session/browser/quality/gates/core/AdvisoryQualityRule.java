package com.feipi.session.browser.quality.gates.core;

import java.util.List;

/** 仅为确实具有非阻断诊断的规则扩展统一执行结果，普通规则无需感知建议语义。 */
public interface AdvisoryQualityRule extends QualityRule {

  /** 一次完成阻断项与建议项判定，避免 CLI 为两种严重级别重复扫描。 */
  Evaluation evaluate(QualityContext context) throws Exception;

  /** 兼容只消费阻断项的 {@link QualityRule} 调用方。 */
  @Override
  default List<QualityViolation> check(QualityContext context) throws Exception {
    return evaluate(context).violations();
  }

  /**
   * 一条规则的一次完整判定结果。
   *
   * @param violations 会使质量门失败的违规。
   * @param advisories 不改变退出码的改进建议。
   */
  record Evaluation(List<QualityViolation> violations, List<QualityAdvisory> advisories) {

    /** 对两类诊断做防御性复制。 */
    public Evaluation {
      violations = List.copyOf(violations);
      advisories = List.copyOf(advisories);
    }
  }
}
