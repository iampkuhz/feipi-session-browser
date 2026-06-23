package com.feipi.session.browser.reuse.analyzer;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.reuse.analyzer.model.AnalysisResult;
import com.feipi.session.browser.reuse.analyzer.model.InputManifest;
import com.feipi.session.browser.reuse.analyzer.model.ModuleManifest;
import com.feipi.session.browser.reuse.analyzer.model.Severity;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** ReuseAnalyzer 集成测试。 使用 synthetic fixture 验证各种分析场景。 */
class ReuseAnalyzerTest {

  @TempDir Path tempDir;

  @TempDir Path cacheDir;

  private Path sourceDir;

  @BeforeEach
  void setup() throws IOException {
    sourceDir = tempDir.resolve("src/main/java");
    Files.createDirectories(sourceDir);
  }

  @Test
  void selfTestReturnsEmptyResult() {
    ReuseAnalyzer analyzer = new ReuseAnalyzer(cacheDir);
    AnalysisResult result = analyzer.selfTest();
    assertThat(result.status()).isEqualTo("PASS");
    assertThat(result.findings()).isEmpty();
  }

  @Test
  void analyzeIncrementalWithoutBootstrapStateReturnsBootstrapRequired() throws IOException {
    ReuseAnalyzer analyzer = new ReuseAnalyzer(cacheDir);
    InputManifest manifest = createSimpleManifest();

    AnalysisResult result = analyzer.analyzeIncremental(manifest, null);
    assertThat(result.status()).isEqualTo("BOOTSTRAP_REQUIRED");
  }

  @Test
  void analyzeIncrementalWithMissingBootstrapFileReturnsBootstrapRequired() throws IOException {
    ReuseAnalyzer analyzer = new ReuseAnalyzer(cacheDir);
    InputManifest manifest = createSimpleManifest();

    Path missingFile = tempDir.resolve("nonexistent-bootstrap.json");
    AnalysisResult result = analyzer.analyzeIncremental(manifest, missingFile);
    assertThat(result.status()).isEqualTo("BOOTSTRAP_REQUIRED");
  }

  @Test
  void analyzeIncrementalWithAcceptedBootstrapProceedsAnalysis() throws IOException {
    // 创建 bootstrap state 文件
    Path bootstrapFile = tempDir.resolve("bootstrap-state.json");
    Files.writeString(
        bootstrapFile,
        """
                {
                    "status": "accepted",
                    "analyzerModulePath": "java/reuse-analyzer",
                    "analyzerVersion": "0.1.0",
                    "schemaVersion": 1,
                    "policySha256": "0000000000000000000000000000000000000000000000000000000000000000",
                    "baselineSha256": "0000000000000000000000000000000000000000000000000000000000000000",
                    "bootstrapCommit": "abc1234567"
                }
                """);

    ReuseAnalyzer analyzer = new ReuseAnalyzer(cacheDir);
    InputManifest manifest =
        new InputManifest(
            25,
            List.of(
                new ModuleManifest(
                    ":test:module", List.of(sourceDir.toString()), List.of(), List.of())),
            List.of(), // 无变更文件
            "abc123",
            "0000000000000000000000000000000000000000000000000000000000000000");

    AnalysisResult result = analyzer.analyzeIncremental(manifest, bootstrapFile);
    // 无 changed files → 空结果
    assertThat(result.status()).isEqualTo("PASS");
    assertThat(result.findings()).isEmpty();
  }

  @Test
  void analyzeIncrementalWithNonAcceptedBootstrapReturnsBootstrapRequired() throws IOException {
    Path bootstrapFile = tempDir.resolve("bootstrap-state.json");
    Files.writeString(
        bootstrapFile,
        """
                {
                    "status": "pending",
                    "analyzerModulePath": "java/reuse-analyzer",
                    "analyzerVersion": "0.1.0",
                    "schemaVersion": 1,
                    "policySha256": "0000000000000000000000000000000000000000000000000000000000000000",
                    "baselineSha256": "0000000000000000000000000000000000000000000000000000000000000000",
                    "bootstrapCommit": "abc1234567"
                }
                """);

    ReuseAnalyzer analyzer = new ReuseAnalyzer(cacheDir);
    InputManifest manifest = createSimpleManifest();

    AnalysisResult result = analyzer.analyzeIncremental(manifest, bootstrapFile);
    assertThat(result.status()).isEqualTo("BOOTSTRAP_REQUIRED");
  }

  @Test
  void analyzeFullEmptySourceDirReturnsEmptyResult() throws IOException {
    ReuseAnalyzer analyzer = new ReuseAnalyzer(cacheDir);
    InputManifest manifest = createSimpleManifest();

    AnalysisResult result = analyzer.analyzeFull(manifest);
    // 空 source dir → 空结果
    assertThat(result.status()).isEqualTo("PASS");
    assertThat(result.findings()).isEmpty();
  }

  @Test
  void analyzeFullWithDuplicateMethodsDetectsFindings() throws IOException {
    // 创建两个具有完全相同方法的类（full family duplicate fixture）
    writeSourceFile(
        "test",
        "ClassA.java",
        """
                package test;
                public class ClassA {
                    public int compute(int x) {
                        return x * 2 + 1;
                    }
                    public String describe() {
                        return "ClassA";
                    }
                }
                """);
    writeSourceFile(
        "test",
        "ClassB.java",
        """
                package test;
                public class ClassB {
                    public int compute(int x) {
                        return x * 2 + 1;
                    }
                    public String describe() {
                        return "ClassB";
                    }
                }
                """);

    ReuseAnalyzer analyzer = new ReuseAnalyzer(cacheDir);
    InputManifest manifest =
        new InputManifest(
            25,
            List.of(
                new ModuleManifest(
                    ":test:module", List.of(sourceDir.toString()), List.of(), List.of())),
            List.of(),
            "abc123",
            "policy123");

    AnalysisResult result = analyzer.analyzeFull(manifest);
    // 应检测到 compute 方法的 exact 重复
    assertThat(result.findings()).isNotEmpty();
    boolean foundExactDup =
        result.findings().stream().anyMatch(f -> f.kind().equals("EXACT_METHOD_DUPLICATE"));
    assertThat(foundExactDup).isTrue();
  }

  @Test
  void analyzeFullProviderSpecificSimilarNoMerge() throws IOException {
    // provider-specific 类似但不合并的 fixture
    writeSourceFile(
        "test",
        "JsonProvider.java",
        """
                package test;
                import java.io.InputStream;
                public class JsonProvider {
                    public String parse(InputStream input) {
                        return "json";
                    }
                }
                """);
    writeSourceFile(
        "test",
        "XmlProvider.java",
        """
                package test;
                import java.io.InputStream;
                public class XmlProvider {
                    public String parse(InputStream input) {
                        return "xml";
                    }
                }
                """);

    ReuseAnalyzer analyzer = new ReuseAnalyzer(cacheDir);
    InputManifest manifest =
        new InputManifest(
            25,
            List.of(
                new ModuleManifest(
                    ":test:module", List.of(sourceDir.toString()), List.of(), List.of())),
            List.of(),
            "abc123",
            "policy123");

    AnalysisResult result = analyzer.analyzeFull(manifest);
    // JsonProvider 和 XmlProvider 不实现相同 interface → 不应在 peer group 中
    // 返回的 literal 不同 → exact fingerprint 不同
    // 不应产生 P0 finding
    boolean hasP0 = result.findings().stream().anyMatch(f -> f.severity() == Severity.P0);
    assertThat(hasP0).isFalse();
  }

  @Test
  void analyzeFullWithInterfacePeerGroupDetectsPeerDuplicate() throws IOException {
    // 实现相同 interface 的两个类有相同方法 → peer group + exact dup
    writeSourceFile(
        "test",
        "Processor.java",
        """
                package test;
                public interface Processor {
                    int process(int input);
                }
                """);
    writeSourceFile(
        "test",
        "ProcessorA.java",
        """
                package test;
                public class ProcessorA implements Processor {
                    public int process(int input) {
                        return input * 2;
                    }
                }
                """);
    writeSourceFile(
        "test",
        "ProcessorB.java",
        """
                package test;
                public class ProcessorB implements Processor {
                    public int process(int input) {
                        return input * 2;
                    }
                }
                """);

    ReuseAnalyzer analyzer = new ReuseAnalyzer(cacheDir);
    InputManifest manifest =
        new InputManifest(
            25,
            List.of(
                new ModuleManifest(
                    ":test:module", List.of(sourceDir.toString()), List.of(), List.of())),
            List.of(),
            "abc123",
            "policy123");

    AnalysisResult result = analyzer.analyzeFull(manifest);
    // 两个 peer group 类型有完全相同的方法 → P0
    boolean foundP0 =
        result.findings().stream()
            .anyMatch(
                f -> f.severity() == Severity.P0 && f.kind().equals("EXACT_METHOD_DUPLICATE"));
    assertThat(foundP0).isTrue();
  }

  @Test
  void analyzeFullSkipsRecordAccessorMethods() throws IOException {
    // 多个 record 有相同组件名 → record accessor 不应被报告为 duplicate
    writeSourceFile(
        "test",
        "RecordA.java",
        """
                package test;
                public record RecordA(String contentHash, int size) {}
                """);
    writeSourceFile(
        "test",
        "RecordB.java",
        """
                package test;
                public record RecordB(String contentHash, int size) {}
                """);
    writeSourceFile(
        "test",
        "RecordC.java",
        """
                package test;
                public record RecordC(String contentHash, int size) {}
                """);

    ReuseAnalyzer analyzer = new ReuseAnalyzer(cacheDir);
    InputManifest manifest =
        new InputManifest(
            25,
            List.of(
                new ModuleManifest(
                    ":test:module", List.of(sourceDir.toString()), List.of(), List.of())),
            List.of(),
            "abc123",
            "policy123");

    AnalysisResult result = analyzer.analyzeFull(manifest);
    // record accessor 方法（contentHash、size）不应出现在 findings 中
    boolean foundRecordAccessorDup =
        result.findings().stream()
            .anyMatch(
                f ->
                    f.occurrences().stream()
                        .anyMatch(
                            o ->
                                "contentHash".equals(o.get("method"))
                                    || "size".equals(o.get("method"))));
    assertThat(foundRecordAccessorDup).isFalse();
  }

  @Test
  void analyzeFullDoesNotSkipNonAccessorRecordMethods() throws IOException {
    // record 中的自定义方法（非 accessor）应正常被分析
    writeSourceFile(
        "test",
        "RecordX.java",
        """
                package test;
                public record RecordX(String name) {
                    public int compute(int x) {
                        return x * 2 + 1;
                    }
                }
                """);
    writeSourceFile(
        "test",
        "RecordY.java",
        """
                package test;
                public record RecordY(String name) {
                    public int compute(int x) {
                        return x * 2 + 1;
                    }
                }
                """);

    ReuseAnalyzer analyzer = new ReuseAnalyzer(cacheDir);
    InputManifest manifest =
        new InputManifest(
            25,
            List.of(
                new ModuleManifest(
                    ":test:module", List.of(sourceDir.toString()), List.of(), List.of())),
            List.of(),
            "abc123",
            "policy123");

    AnalysisResult result = analyzer.analyzeFull(manifest);
    // 自定义方法 compute 应该被检测到重复，但 name accessor 不应被报告
    boolean foundComputeDup =
        result.findings().stream()
            .anyMatch(
                f -> f.occurrences().stream().anyMatch(o -> "compute".equals(o.get("method"))));
    assertThat(foundComputeDup).isTrue();

    boolean foundNameAccessorDup =
        result.findings().stream()
            .anyMatch(f -> f.occurrences().stream().anyMatch(o -> "name".equals(o.get("method"))));
    assertThat(foundNameAccessorDup).isFalse();
  }

  private InputManifest createSimpleManifest() {
    return new InputManifest(
        25,
        List.of(
            new ModuleManifest(
                ":test:module", List.of(sourceDir.toString()), List.of(), List.of())),
        List.of(),
        "abc123",
        "0000000000000000000000000000000000000000000000000000000000000000");
  }

  private void writeSourceFile(String packagePath, String fileName, String content)
      throws IOException {
    Path packageDir = sourceDir.resolve(packagePath);
    Files.createDirectories(packageDir);
    Files.writeString(packageDir.resolve(fileName), content);
  }
}
