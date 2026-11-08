package com.feipi.session.browser.cli;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 检查实际安装和发行 launcher 传给 JVM 的堆上限，而不是匹配脚本文本。 */
class LauncherProfileRegressionTest {

  @TempDir Path workDir;

  @Test
  void launchersChooseHeapForScanAndServe() throws Exception {
    for (Path launcher : List.of(installedLauncher(), runtimeLauncher())) {
      assertHeap(launcher, null, 128, "scan");
      assertHeap(launcher, null, 512, "scan", "--full");
      assertHeap(launcher, null, 512, "serve");
    }
  }

  @Test
  void installedLauncherPreservesUserOverride() throws Exception {
    assertHeap(installedLauncher(), "-Xmx256m", 256, "scan", "--full");
  }

  private static Path installedLauncher() {
    return Path.of(System.getProperty("cli.install.dir"), "bin", "app-cli");
  }

  private static Path runtimeLauncher() {
    return Path.of(System.getProperty("cli.runtime.dir"), "bin", "run");
  }

  private void assertHeap(Path launcher, String override, long mib, String... arguments)
      throws Exception {
    var command = new ArrayList<>(List.of(launcher.toString()));
    command.addAll(List.of(arguments));
    command.add("--help");
    Path output = workDir.resolve("jvm-output");
    var builder =
        new ProcessBuilder(command)
            .directory(workDir.toFile())
            .redirectErrorStream(true)
            .redirectOutput(output.toFile());
    var env = builder.environment();
    List.of("JAVA_OPTS", "APP_CLI_OPTS", "_JAVA_OPTIONS", "JAVA_TOOL_OPTIONS", "CLASSPATH")
        .forEach(env::remove);
    env.put("JAVA_HOME", System.getProperty("java.home"));
    env.put("JDK_JAVA_OPTIONS", "-XX:+PrintFlagsFinal");
    if (override != null) {
      env.put("APP_CLI_OPTS", override);
    }
    Process process = builder.start();
    try {
      assertThat(process.waitFor(20, TimeUnit.SECONDS)).as("launcher did not exit").isTrue();
      String flags = java.nio.file.Files.readString(output, StandardCharsets.UTF_8);
      assertThat(process.exitValue()).as("launcher output: %s", flags).isZero();
      assertThat(flags).containsPattern("(?m)\\bMaxHeapSize\\s*:?=\\s*" + (mib << 20) + "\\s");
    } finally {
      if (process.isAlive()) {
        process.destroyForcibly();
      }
    }
  }
}
