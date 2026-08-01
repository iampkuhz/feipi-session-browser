package com.feipi.session.browser.quality.gates.core;

import java.util.List;

/** 单 JVM quality-gate registry 中的一条 Java 源码规则。 */
public interface QualityRule {

  /** 返回稳定 rule id。 */
  String id();

  /**
   * 判断仓库相对路径是否属于本规则；默认只接收 production Java 源码。
   *
   * @param relativePath 仓库相对 POSIX 路径。
   * @return 属于本规则时返回 true。
   */
  default boolean supportsPath(String relativePath) {
    return relativePath.endsWith(".java") && relativePath.contains("/src/main/java/");
  }

  /**
   * 声明收到 changed-files 时是否只检查变更源码；默认规则支持增量收窄。
   *
   * @return 只检查 changed-files 时返回 true；始终全量检查时返回 false。
   */
  default boolean usesChangedFiles() {
    return true;
  }

  /** 对共享输入执行规则，不得自行扫描 Git 或再次解析源码。 */
  List<QualityViolation> check(QualityContext context) throws Exception;
}
