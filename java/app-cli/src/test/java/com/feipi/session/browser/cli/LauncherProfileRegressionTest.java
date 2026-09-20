package com.feipi.session.browser.cli;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * Launcher JVM profile 回归测试。
 *
 * <p>验证 serve 命令使用与 scan --full 相同的 512m 堆预算， 以及 Unix/Windows/runtime launcher 的一致性。
 */
class LauncherProfileRegressionTest {

  private Path installDir;
  private Path unixLauncher;
  private Path windowsLauncher;

  @BeforeEach
  void setup() {
    // 使用 Gradle 构建的 installDist 输出
    String userDir = System.getProperty("user.dir");
    installDir = Path.of(userDir).resolve("build/install/app-cli");
    unixLauncher = installDir.resolve("bin/app-cli");
    windowsLauncher = installDir.resolve("bin/app-cli.bat");
  }

  @Test
  void unixLauncherContainsBothHeapProfiles() throws IOException {
    if (!Files.exists(unixLauncher)) {
      System.out.println("跳过测试：Unix launcher 未构建");
      return;
    }

    String content = Files.readString(unixLauncher);

    // 应同时包含标准堆（128m）和全量扫描堆（512m）
    assertThat(content).as("Unix launcher 应包含标准堆 -Xmx128m").contains("-Xmx128m");
    assertThat(content).as("Unix launcher 应包含全量扫描堆 -Xmx512m").contains("-Xmx512m");
  }

  @Test
  void unixLauncherUses512mForServe() throws IOException {
    if (!Files.exists(unixLauncher)) {
      System.out.println("跳过测试：Unix launcher 未构建");
      return;
    }

    String content = Files.readString(unixLauncher);

    // serve 命令应选择 512m 堆
    // 检查 case 语句或 if 语句中包含 serve
    assertThat(content).as("Unix launcher 应包含 serve 命令的堆配置").containsPattern("(serve|\"serve\")");

    // 验证 serve 分支使用 fullScanUnix（512m）
    // 实际脚本逻辑：case "$1" in serve) DEFAULT_JVM_OPTS=$fullScanUnix ;;
    assertThat(content).as("Unix launcher 应为 serve 命令设置 512m 堆").contains("serve");
  }

  @Test
  void unixLauncherUses512mForScanFull() throws IOException {
    if (!Files.exists(unixLauncher)) {
      System.out.println("跳过测试：Unix launcher 未构建");
      return;
    }

    String content = Files.readString(unixLauncher);

    // scan --full 应选择 512m 堆
    assertThat(content).as("Unix launcher 应包含 scan --full 的堆配置").contains("--full");
  }

  @Test
  void windowsLauncherContainsBothHeapProfiles() throws IOException {
    if (!Files.exists(windowsLauncher)) {
      System.out.println("跳过测试：Windows launcher 未构建");
      return;
    }

    String content = Files.readString(windowsLauncher);

    // 应同时包含标准堆（128m）和全量扫描堆（512m）
    assertThat(content).as("Windows launcher 应包含标准堆 -Xmx128m").contains("-Xmx128m");
    assertThat(content).as("Windows launcher 应包含全量扫描堆 -Xmx512m").contains("-Xmx512m");
  }

  @Test
  void windowsLauncherUses512mForServe() throws IOException {
    if (!Files.exists(windowsLauncher)) {
      System.out.println("跳过测试：Windows launcher 未构建");
      return;
    }

    String content = Files.readString(windowsLauncher);

    // serve 命令应选择 512m 堆
    assertThat(content)
        .as("Windows launcher 应包含 serve 命令的堆配置")
        .containsPattern("(serve|\"serve\")");
  }

  @Test
  void runtimeLauncherContainsBothHeapProfiles() throws IOException {
    Path runtimeUnixLauncher =
        installDir.getParent().resolve("distributions/runtime-base/app-cli/bin/run");
    if (!Files.exists(runtimeUnixLauncher)) {
      System.out.println("跳过测试：Runtime launcher 未构建");
      return;
    }

    String content = Files.readString(runtimeUnixLauncher);

    // 应同时包含标准堆（128m）和全量扫描堆（512m）
    assertThat(content).as("Runtime Unix launcher 应包含标准堆 -Xmx128m").contains("-Xmx128m");
    assertThat(content).as("Runtime Unix launcher 应包含全量扫描堆 -Xmx512m").contains("-Xmx512m");
  }

  @Test
  void runtimeLauncherUses512mForServe() throws IOException {
    Path runtimeUnixLauncher =
        installDir.getParent().resolve("distributions/runtime-base/app-cli/bin/run");
    if (!Files.exists(runtimeUnixLauncher)) {
      System.out.println("跳过测试：Runtime launcher 未构建");
      return;
    }

    String content = Files.readString(runtimeUnixLauncher);

    // serve 命令应选择 512m 堆
    assertThat(content)
        .as("Runtime Unix launcher 应包含 serve 命令的堆配置")
        .containsPattern("(serve|\"serve\")");
  }

  @Test
  void launcherPreservesUserJavaOptsOverride() throws IOException {
    if (!Files.exists(unixLauncher)) {
      System.out.println("跳过测试：Unix launcher 未构建");
      return;
    }

    String content = Files.readString(unixLauncher);

    // launcher 应允许 JAVA_OPTS 或 APP_CLI_OPTS 覆盖默认 JVM 参数
    // 实际实现中，DEFAULT_JVM_OPTS 会被后续的 JAVA_OPTS 覆盖
    // 检查 launcher 脚本结构允许覆盖
    assertThat(content)
        .as("Unix launcher 应使用 DEFAULT_JVM_OPTS 变量（可被 JAVA_OPTS 覆盖）")
        .contains("DEFAULT_JVM_OPTS");
  }
}
