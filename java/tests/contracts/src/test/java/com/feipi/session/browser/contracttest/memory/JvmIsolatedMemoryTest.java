package com.feipi.session.browser.contracttest.memory;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.fail;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * 独立 JVM 内存验证测试。
 *
 * <p>通过 ProcessBuilder 在 512m 堆预算下运行 MemoryBenchmarkRunner，验证大数据集下扫描成功完成，且发现数 > 0。
 *
 * <p>此测试证明 serve launcher 的堆预算调整（128m 到 512m）是必要的。
 */
class JvmIsolatedMemoryTest {

  @TempDir Path tempDir;

  private Path dataDir;
  private Path outputFile;
  private String javaExe;
  private String classpath;

  @BeforeEach
  void setup() throws IOException {
    dataDir = tempDir.resolve("data");
    Files.createDirectories(dataDir);
    outputFile = tempDir.resolve("benchmark-output.txt");

    // 使用当前 java.home 的 java 可执行文件，保证同 JDK
    javaExe = System.getProperty("java.home") + "/bin/java";
    if (!Files.isExecutable(Path.of(javaExe))) {
      // Windows 平台需要追加 .exe 后缀
      javaExe = javaExe + ".exe";
      if (!Files.isExecutable(Path.of(javaExe))) {
        fail("找不到 java 可执行文件: " + javaExe);
      }
    }

    // 使用测试运行时 classpath，包含测试类和所有依赖
    classpath = System.getProperty("java.class.path");
    assertThat(classpath).as("测试运行时 classpath 不得为空").isNotNull().isNotEmpty();
  }

  @Test
  void largeDatasetSucceedsWith512mHeap() throws Exception {
    // 生成数据集：50 会话 × 500 事件 = 25k 事件
    int sessions = 50;
    int eventsPerSession = 500;

    int exitCode = runBenchmark(512, sessions, eventsPerSession);

    String output = Files.readString(outputFile);

    // 512m 堆应该成功
    assertThat(exitCode)
        .as("512m 堆在 %d 会话 × %d 事件下应成功。输出：%s", sessions, eventsPerSession, output)
        .isEqualTo(0);

    // 验证输出包含预期的 BENCHMARK_RESULT 行
    assertThat(output)
        .as("输出应包含 BENCHMARK_RESULT: candidates=")
        .contains("BENCHMARK_RESULT: candidates=");

    // 验证发现数 > 0
    int candidates = extractInt(output, "BENCHMARK_RESULT: candidates=(\\d+)");
    assertThat(candidates).as("发现候选数应 > 0").isGreaterThan(0);

    // 验证索引数据库存在
    Path dbPath = dataDir.resolve("index/sessions.db");
    assertThat(dbPath).exists();

    // 验证 artifact 目录存在
    Path artifactDir = dataDir.resolve("index/artifacts/normalized-sessions");
    assertThat(artifactDir).isDirectory();
  }

  private int extractInt(String output, String regex) {
    Pattern pattern = Pattern.compile(regex);
    Matcher matcher = pattern.matcher(output);
    assertThat(matcher.find()).as("输出应包含匹配 %s 的内容", regex).isTrue();
    return Integer.parseInt(matcher.group(1));
  }

  private int runBenchmark(int xmxMb, int sessions, int eventsPerSession)
      throws IOException, InterruptedException {
    ProcessBuilder pb =
        new ProcessBuilder(
            javaExe,
            "-Xmx" + xmxMb + "m",
            "-Dxmx=" + xmxMb + "m",
            "-cp",
            classpath,
            "com.feipi.session.browser.contracttest.memory.MemoryBenchmarkRunner",
            dataDir.toString(),
            String.valueOf(sessions),
            String.valueOf(eventsPerSession));

    // 输出重定向到临时文件，避免 reader.lines() 阻塞
    pb.redirectOutput(outputFile.toFile());
    pb.redirectErrorStream(true);

    Process process = pb.start();
    try {
      // 先有界 wait，超时失效
      boolean finished = process.waitFor(120, TimeUnit.SECONDS);
      if (!finished) {
        process.destroyForcibly();
        return -1;
      }
      return process.exitValue();
    } finally {
      // finally 只清理自己子进程
      if (process.isAlive()) {
        process.destroyForcibly();
      }
    }
  }
}
