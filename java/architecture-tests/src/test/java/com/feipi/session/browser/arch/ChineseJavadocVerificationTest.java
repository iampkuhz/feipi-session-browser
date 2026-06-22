package com.feipi.session.browser.arch;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * 中文 Javadoc 验证测试。
 *
 * <p>包含正向测试（验证合规源码通过）和负向测试（验证各种违规场景被正确检测）。 使用临时目录写入 Java 源文件并通过 {@link ChineseJavadocVerifier} 验证。
 */
@DisplayName("Chinese Javadoc verification")
class ChineseJavadocVerificationTest {

  private Path tempDir;

  @BeforeEach
  void setUp() throws IOException {
    tempDir = Files.createTempDirectory("javadoc-verify-test");
  }

  // ===== 正向测试：{@code core-domain} 源码扫描 =====

  @Test
  @DisplayName("core-domain sources pass Chinese Javadoc verification (with exclusions)")
  void verifyCoreDomainSources() throws IOException {
    Path repoRoot = resolveRepoRoot();
    Path coreDomainSrc = repoRoot.resolve("java/core-domain/src/main/java");
    ChineseJavadocVerifier verifier = new ChineseJavadocVerifier(coreDomainSrc);
    ChineseJavadocVerifier.VerificationResult result = verifier.verify();
    assertTrue(
        result.passed(),
        () -> "core-domain source verification failed:\n" + String.join("\n", result.failures()));
  }

  // ===== 负向 fixture 测试 =====

  @Nested
  @DisplayName("Negative fixtures — violations are detected")
  class NegativeFixtures {

    @Test
    @DisplayName("class without Javadoc fails")
    void classWithoutJavadocFails() throws IOException {
      String source = "package test;\npublic class NoJavadoc {}\n";
      writeTempFile("NoJavadoc.java", source);
      ChineseJavadocVerifier.VerificationResult vr = new ChineseJavadocVerifier(tempDir).verify();
      assertFalse(vr.passed());
      assertThat(vr.failures()).anyMatch(f -> f.contains("NoJavadoc"));
    }

    @Test
    @DisplayName("class with English-only Javadoc fails")
    void classWithEnglishOnlyJavadocFails() throws IOException {
      String source = "package test;\n/** This is English only. */\npublic class EnglishOnly {}\n";
      writeTempFile("EnglishOnly.java", source);
      ChineseJavadocVerifier.VerificationResult vr = new ChineseJavadocVerifier(tempDir).verify();
      assertFalse(vr.passed());
      assertThat(vr.failures())
          .anyMatch(f -> f.contains("EnglishOnly") && f.contains("English-only"));
    }

    @Test
    @DisplayName("class with TODO-only Javadoc fails")
    void classWithTodoOnlyJavadocFails() throws IOException {
      String source = "package test;\n/** TODO */\npublic class TodoOnly {}\n";
      writeTempFile("TodoOnly.java", source);
      ChineseJavadocVerifier.VerificationResult vr = new ChineseJavadocVerifier(tempDir).verify();
      assertFalse(vr.passed());
      assertThat(vr.failures()).anyMatch(f -> f.contains("TodoOnly"));
    }

    @Test
    @DisplayName("public method without Javadoc fails")
    void publicMethodWithoutJavadocFails() throws IOException {
      String source =
          "package test;\n"
              + "/** 有中文文档的类。 */\n"
              + "public class MethodNoDoc {\n"
              + "    public void doSomething() {}\n"
              + "}\n";
      writeTempFile("MethodNoDoc.java", source);
      ChineseJavadocVerifier.VerificationResult vr = new ChineseJavadocVerifier(tempDir).verify();
      assertFalse(vr.passed());
      assertThat(vr.failures()).anyMatch(f -> f.contains("doSomething"));
    }

    @Test
    @DisplayName("public method with English-only Javadoc fails")
    void publicMethodWithEnglishOnlyFails() throws IOException {
      String source =
          "package test;\n"
              + "/** 有中文文档的类。 */\n"
              + "public class MethodEnglish {\n"
              + "    /** Does something. */\n"
              + "    public void doSomething() {}\n"
              + "}\n";
      writeTempFile("MethodEnglish.java", source);
      ChineseJavadocVerifier.VerificationResult vr = new ChineseJavadocVerifier(tempDir).verify();
      assertFalse(vr.passed());
      assertThat(vr.failures())
          .anyMatch(f -> f.contains("doSomething") && f.contains("English-only"));
    }

    @Test
    @DisplayName("override method with only {@inheritDoc} fails")
    void overrideWithInheritDocOnlyFails() throws IOException {
      String source =
          "package test;\n"
              + "/** 基类。 */\n"
              + "abstract class Base {\n"
              + "    /** 执行操作。 */\n"
              + "    public abstract void doWork();\n"
              + "}\n"
              + "/** 子类。 */\n"
              + "class Child extends Base {\n"
              + "    /** {@inheritDoc} */\n"
              + "    @Override\n"
              + "    public void doWork() {}\n"
              + "}\n";
      writeTempFile("InheritDocOnly.java", source);
      ChineseJavadocVerifier.VerificationResult vr = new ChineseJavadocVerifier(tempDir).verify();
      assertFalse(vr.passed());
      assertThat(vr.failures()).anyMatch(f -> f.contains("inheritDoc"));
    }

    @Test
    @DisplayName("public constructor without Javadoc fails")
    void publicConstructorWithoutJavadocFails() throws IOException {
      String source =
          "package test;\n"
              + "/** 有中文文档的类。 */\n"
              + "public class NoCtorDoc {\n"
              + "    public NoCtorDoc() {}\n"
              + "}\n";
      writeTempFile("NoCtorDoc.java", source);
      ChineseJavadocVerifier.VerificationResult vr = new ChineseJavadocVerifier(tempDir).verify();
      assertFalse(vr.passed());
      assertThat(vr.failures()).anyMatch(f -> f.contains("NoCtorDoc") && f.contains("constructor"));
    }

    @Test
    @DisplayName("record component without Chinese @param fails")
    void recordComponentWithoutParamFails() throws IOException {
      String source = "package test;\n/** 一条记录。 */\npublic record NoParamRecord(String value) {}\n";
      writeTempFile("NoParamRecord.java", source);
      ChineseJavadocVerifier.VerificationResult vr = new ChineseJavadocVerifier(tempDir).verify();
      assertFalse(vr.passed());
      assertThat(vr.failures()).anyMatch(f -> f.contains("value") && f.contains("@param"));
    }

    @Test
    @DisplayName("record component with English-only @param fails")
    void recordComponentWithEnglishParamFails() throws IOException {
      String source =
          "package test;\n"
              + "/** 一条记录。\n"
              + " * @param value The value.\n"
              + " */\n"
              + "public record EnglishParamRecord(String value) {}\n";
      writeTempFile("EnglishParamRecord.java", source);
      ChineseJavadocVerifier.VerificationResult vr = new ChineseJavadocVerifier(tempDir).verify();
      assertFalse(vr.passed());
      assertThat(vr.failures()).anyMatch(f -> f.contains("value") && f.contains("English-only"));
    }

    @Test
    @DisplayName("annotation type without Chinese Javadoc fails")
    void annotationTypeWithoutChineseJavadocFails() throws IOException {
      String source =
          "package test;\n"
              + "public @interface NoChineseAnno {\n"
              + "    /** The name. */\n"
              + "    String name();\n"
              + "}\n";
      writeTempFile("NoChineseAnno.java", source);
      ChineseJavadocVerifier.VerificationResult vr = new ChineseJavadocVerifier(tempDir).verify();
      assertFalse(vr.passed());
      assertThat(vr.failures()).anyMatch(f -> f.contains("NoChineseAnno"));
    }

    @Test
    @DisplayName("enum constant without Chinese Javadoc fails")
    void enumConstantWithoutChineseJavadocFails() throws IOException {
      String source =
          "package test;\n"
              + "/** 一个枚举。 */\n"
              + "public enum NoChineseEnum {\n"
              + "    /** Active status. */\n"
              + "    ACTIVE\n"
              + "}\n";
      writeTempFile("NoChineseEnum.java", source);
      ChineseJavadocVerifier.VerificationResult vr = new ChineseJavadocVerifier(tempDir).verify();
      assertFalse(vr.passed());
      assertThat(vr.failures()).anyMatch(f -> f.contains("ACTIVE"));
    }

    @Test
    @DisplayName("regular comments not counted as Javadoc")
    void regularCommentNotCountedAsJavadoc() throws IOException {
      String source =
          "package test;\n"
              + "// This is a line comment\n"
              + "/* This is a block comment */\n"
              + "public class NotJavadoc {}\n";
      writeTempFile("NotJavadoc.java", source);
      ChineseJavadocVerifier.VerificationResult vr = new ChineseJavadocVerifier(tempDir).verify();
      assertFalse(vr.passed());
      assertThat(vr.failures()).anyMatch(f -> f.contains("NotJavadoc"));
    }
  }

  // ===== 正向 fixture 测试 =====

  @Nested
  @DisplayName("Positive fixtures — compliant code passes")
  class PositiveFixtures {

    @Test
    @DisplayName("Chinese class Javadoc passes")
    void chineseClassJavadocPasses() throws IOException {
      String source =
          "package test;\n" + "/** 这是一个有中文文档的类。 */\n" + "public class ChineseClass {}\n";
      writeTempFile("ChineseClass.java", source);
      ChineseJavadocVerifier.VerificationResult vr = new ChineseJavadocVerifier(tempDir).verify();
      assertTrue(vr.passed(), () -> "Expected pass but got: " + vr.failures());
    }

    @Test
    @DisplayName("Chinese record Javadoc with @param passes")
    void chineseRecordJavadocWithParamPasses() throws IOException {
      String source =
          "package test;\n"
              + "/** 一条中文记录。\n"
              + " * @param name 名称字段\n"
              + " * @param value 值字段\n"
              + " */\n"
              + "public record ChineseRecord(String name, int value) {}\n";
      writeTempFile("ChineseRecord.java", source);
      ChineseJavadocVerifier.VerificationResult vr = new ChineseJavadocVerifier(tempDir).verify();
      assertTrue(vr.passed(), () -> "Expected pass but got: " + vr.failures());
    }

    @Test
    @DisplayName("Chinese public method Javadoc passes")
    void chinesePublicMethodJavadocPasses() throws IOException {
      String source =
          "package test;\n"
              + "/** 一个有方法的类。\n"
              + " * @param name 名称。\n"
              + " */\n"
              + "public record MethodDocRecord(String name) {\n"
              + "    /** 获取名称。 */\n"
              + "    public String displayName() { return name; }\n"
              + "}\n";
      writeTempFile("MethodDocRecord.java", source);
      ChineseJavadocVerifier.VerificationResult vr = new ChineseJavadocVerifier(tempDir).verify();
      assertTrue(vr.passed(), () -> "Expected pass but got: " + vr.failures());
    }

    @Test
    @DisplayName("Chinese with {@inheritDoc} passes")
    void chineseWithInheritDocPasses() throws IOException {
      String source =
          "package test;\n"
              + "/** 基类。 */\n"
              + "abstract class InheritBase {\n"
              + "    /** 执行工作。 */\n"
              + "    public abstract void doWork();\n"
              + "}\n"
              + "/** 子类实现。 */\n"
              + "class InheritChild extends InheritBase {\n"
              + "    /** 具体执行工作逻辑。{@inheritDoc} */\n"
              + "    @Override\n"
              + "    public void doWork() {}\n"
              + "}\n";
      writeTempFile("InheritDoc.java", source);
      ChineseJavadocVerifier.VerificationResult vr = new ChineseJavadocVerifier(tempDir).verify();
      assertTrue(vr.passed(), () -> "Expected pass but got: " + vr.failures());
    }

    @Test
    @DisplayName("mixed Chinese with technical terms passes")
    void mixedChineseWithTechnicalTermsPasses() throws IOException {
      String source =
          "package test;\n"
              + "/** 表示一个 Session 的唯一标识符 ID。\n"
              + " * @param value 会话标识的原始值\n"
              + " */\n"
              + "public record SessionId(String value) {}\n";
      writeTempFile("SessionId.java", source);
      ChineseJavadocVerifier.VerificationResult vr = new ChineseJavadocVerifier(tempDir).verify();
      assertTrue(vr.passed(), () -> "Expected pass but got: " + vr.failures());
    }

    @Test
    @DisplayName("Chinese annotation type and element passes")
    void chineseAnnotationAndElementPasses() throws IOException {
      String source =
          "package test;\n"
              + "/** 标记注解。 */\n"
              + "public @interface ChineseAnno {\n"
              + "    /** 名称属性。 */\n"
              + "    String name();\n"
              + "}\n";
      writeTempFile("ChineseAnno.java", source);
      ChineseJavadocVerifier.VerificationResult vr = new ChineseJavadocVerifier(tempDir).verify();
      assertTrue(vr.passed(), () -> "Expected pass but got: " + vr.failures());
    }

    @Test
    @DisplayName("Chinese enum constant passes")
    void chineseEnumConstantPasses() throws IOException {
      String source =
          "package test;\n"
              + "/** 状态枚举。 */\n"
              + "public enum ChineseEnum {\n"
              + "    /** 活跃状态。 */\n"
              + "    ACTIVE,\n"
              + "    /** 非活跃状态。 */\n"
              + "    INACTIVE\n"
              + "}\n";
      writeTempFile("ChineseEnum.java", source);
      ChineseJavadocVerifier.VerificationResult vr = new ChineseJavadocVerifier(tempDir).verify();
      assertTrue(vr.passed(), () -> "Expected pass but got: " + vr.failures());
    }
  }

  // ===== 辅助方法 =====

  private Path writeTempFile(String name, String content) throws IOException {
    Path file = tempDir.resolve(name);
    Files.writeString(file, content);
    return file;
  }

  /** 解析仓库根目录。优先使用系统属性 {@code repo.root.dir}， 回退到用户目录下的默认路径。 */
  private static Path resolveRepoRoot() {
    String prop = System.getProperty("repo.root.dir");
    if (prop != null) {
      return Path.of(prop);
    }
    return Path.of(System.getProperty("user.dir")).getParent().getParent();
  }
}
