package com.feipi.session.browser.reuse.analyzer;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import spoon.Launcher;
import spoon.support.compiler.VirtualFile;

/**
 * 验证 Spoon 在仓库中实际使用的 compliance level 能正常工作。
 *
 * <p>Spoon 11.x 基于 Eclipse JDT，支持到 Java 21。 仓库使用 Java 25 编译但语法向下兼容，因此 analyzer 使用 21 作为 compliance
 * level。
 */
class ComplianceTest {

  @Test
  void analyzerComplianceLevelIsSupported() {
    // 验证 SpoonAnalyzer 使用的 compliance level 能成功构建模型
    Launcher launcher = new Launcher();
    launcher.getEnvironment().setComplianceLevel(21);
    launcher.getEnvironment().setNoClasspath(true);
    launcher.getEnvironment().setShouldCompile(false);
    launcher.addInputResource(new VirtualFile("class T { void m() {} }", "T.java"));
    launcher.buildModel();

    assertThat(launcher.getModel().getAllTypes()).isNotEmpty();
  }

  @Test
  void unsupportedHigherLevelIsRejected() {
    // 验证 Spoon 不支持 compliance level 25（仓库不依赖此级别）
    Launcher launcher = new Launcher();
    launcher.getEnvironment().setComplianceLevel(25);
    launcher.getEnvironment().setNoClasspath(true);
    launcher.getEnvironment().setShouldCompile(false);
    launcher.addInputResource(new VirtualFile("class T {}", "T.java"));

    org.junit.jupiter.api.Assertions.assertThrows(Exception.class, launcher::buildModel);
  }
}
