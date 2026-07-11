package com.feipi.session.browser.quality.gates.core;

import java.util.List;

/**
 * 质量门接口。
 *
 * <p>每个实现对应一个可独立执行的质量门禁，例如 record component Javadoc 检查。
 */
public interface QualityGate {

  /**
   * 返回门禁唯一标识，例如 {@code record-component-javadocs}。
   *
   * @return 门禁 id。
   */
  String id();

  /**
   * 执行质量检查并返回违规列表。
   *
   * @param context 包含仓库根目录、输入路径和环境的上下文。
   * @return 违规列表；为空表示通过。
   * @throws Exception 检查过程中出现异常时抛出。
   */
  List<QualityViolation> check(QualityGateContext context) throws Exception;
}
