package com.feipi.session.browser.quality.gates.core;

import java.util.List;

/** 单 JVM quality-gate registry 中的一条 Java 源码规则。 */
public interface QualityRule {

  /** 返回稳定 rule id。 */
  String id();

  /** 对共享 compiler AST 执行规则，不得自行扫描 Git 或再次解析源码。 */
  List<QualityViolation> check(QualityContext context) throws Exception;
}
