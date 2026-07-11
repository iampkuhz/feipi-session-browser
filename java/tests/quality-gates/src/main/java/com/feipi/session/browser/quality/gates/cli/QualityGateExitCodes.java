package com.feipi.session.browser.quality.gates.cli;

/** CLI 退出码常量。 */
public final class QualityGateExitCodes {

  /** 检查通过，无违规。 */
  public static final int OK = 0;

  /** 发现违规。 */
  public static final int VIOLATIONS = 1;

  /** 参数无效或发生内部异常。 */
  public static final int ERROR = 2;

  private QualityGateExitCodes() {}
}
