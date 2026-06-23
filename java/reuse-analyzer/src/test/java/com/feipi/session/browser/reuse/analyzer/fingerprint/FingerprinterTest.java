package com.feipi.session.browser.reuse.analyzer.fingerprint;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import spoon.Launcher;
import spoon.reflect.declaration.CtMethod;
import spoon.reflect.declaration.CtType;
import spoon.support.compiler.VirtualFile;

/** Fingerprinter 测试：验证 exact、alpha、statement 和 expression 指纹。 */
class FingerprinterTest {

  private static CtType<?> duplicateType;
  private static CtType<?> alphaType;

  @BeforeAll
  static void setup() {
    // 完全相同方法的两个类（one-line duplication）
    String source1 =
        """
                package test;
                public class ClassA {
                    public int compute(int x) {
                        return x * 2 + 1;
                    }
                }
                """;
    String source2 =
        """
                package test;
                public class ClassB {
                    public int compute(int x) {
                        return x * 2 + 1;
                    }
                }
                """;

    Launcher launcher = buildModel(source1, source2);
    duplicateType =
        launcher.getModel().getAllTypes().stream()
            .filter(t -> t.getSimpleName().equals("ClassA"))
            .findFirst()
            .orElseThrow();

    // Alpha 等价（变量重命名）的两个类
    String source3 =
        """
                package test;
                public class ClassC {
                    public int process(int value) {
                        return value * 3;
                    }
                }
                """;
    String source4 =
        """
                package test;
                public class ClassD {
                    public int process(int data) {
                        return data * 3;
                    }
                }
                """;

    Launcher launcher2 = buildModel(source3, source4);
    alphaType =
        launcher2.getModel().getAllTypes().stream()
            .filter(t -> t.getSimpleName().equals("ClassC"))
            .findFirst()
            .orElseThrow();
  }

  @Test
  void exactMethodFingerprintIdenticalMethodsProduceSameHash() {
    CtMethod<?> methodA = duplicateType.getMethods().stream().findFirst().orElseThrow();

    // 构建另一个包含完全相同方法的模型
    Launcher launcher =
        buildModel(
            "package test; public class ClassA2 { public int compute(int x) { return x * 2 + 1; } }",
            "package test; public class ClassB2 { public int compute(int x) { return x * 2 + 1; } }");
    var types = launcher.getModel().getAllTypes().stream().toList();
    CtMethod<?> methodA2 = types.get(0).getMethods().stream().findFirst().orElseThrow();
    CtMethod<?> methodB2 = types.get(1).getMethods().stream().findFirst().orElseThrow();

    String fpA = Fingerprinter.exactMethodFingerprint(methodA);
    String fpA2 = Fingerprinter.exactMethodFingerprint(methodA2);
    String fpB2 = Fingerprinter.exactMethodFingerprint(methodB2);

    // 完全相同方法 → exact fingerprint 相同
    assertThat(fpA).isEqualTo(fpA2);
    assertThat(fpA2).isEqualTo(fpB2);
    // fingerprint 是 64 位 hex（SHA-256）
    assertThat(fpA).hasSize(64).matches("[0-9a-f]{64}");
  }

  @Test
  void exactMethodFingerprintDifferentMethodsProduceDifferentHash() {
    Launcher launcher =
        buildModel(
            "package test; public class E { public int foo(int x) { return x + 1; } }",
            "package test; public class F { public int bar(int y) { return y - 1; } }");
    var types = launcher.getModel().getAllTypes().stream().toList();
    CtMethod<?> foo = types.get(0).getMethods().stream().findFirst().orElseThrow();
    CtMethod<?> bar = types.get(1).getMethods().stream().findFirst().orElseThrow();

    String fpFoo = Fingerprinter.exactMethodFingerprint(foo);
    String fpBar = Fingerprinter.exactMethodFingerprint(bar);

    assertThat(fpFoo).isNotEqualTo(fpBar);
  }

  @Test
  void alphaMethodFingerprintVariableRenamingProducesSameHash() {
    // ClassC 和 ClassD 的方法体只是变量名不同
    Launcher launcher =
        buildModel(
            "package test; public class C1 { public int process(int value) { return value * 3; } }",
            "package test; public class D1 { public int process(int data) { return data * 3; } }");
    var types = launcher.getModel().getAllTypes().stream().toList();
    CtMethod<?> m1 = types.get(0).getMethods().stream().findFirst().orElseThrow();
    CtMethod<?> m2 = types.get(1).getMethods().stream().findFirst().orElseThrow();

    String alpha1 = Fingerprinter.alphaMethodFingerprint(m1);
    String alpha2 = Fingerprinter.alphaMethodFingerprint(m2);

    // alpha-normalized → 相同
    assertThat(alpha1).isEqualTo(alpha2);

    // 但 exact 应不同（变量名不同）
    String exact1 = Fingerprinter.exactMethodFingerprint(m1);
    String exact2 = Fingerprinter.exactMethodFingerprint(m2);
    assertThat(exact1).isNotEqualTo(exact2);
  }

  @Test
  void statementFingerprintSingleStatement() {
    Launcher launcher =
        buildModel("package test; public class S { public void doIt() { int x = 42; } }");
    CtType<?> type = launcher.getModel().getAllTypes().stream().findFirst().orElseThrow();
    CtMethod<?> method = type.getMethods().stream().findFirst().orElseThrow();

    java.util.List<String> fps = Fingerprinter.allStatementFingerprints(method);
    assertThat(fps).isNotEmpty();
    // 每个 fingerprint 都是 64 位 hex
    fps.forEach(fp -> assertThat(fp).hasSize(64).matches("[0-9a-f]{64}"));
  }

  @Test
  void statementFingerprintRollingSubsequences() {
    String source =
        """
                package test;
                public class R {
                    public void multi() {
                        int a = 1;
                        int b = 2;
                        int c = a + b;
                    }
                }
                """;
    Launcher launcher = buildModel(source);
    CtType<?> type = launcher.getModel().getAllTypes().stream().findFirst().orElseThrow();
    CtMethod<?> method = type.getMethods().stream().findFirst().orElseThrow();

    java.util.List<String> rolling = Fingerprinter.rollingStatementFingerprints(method.getBody());
    // 3 条语句，window=2 有 2 个，window=3 有 1 个 → 总共 3 个
    assertThat(rolling).hasSize(3);
  }

  @Test
  void expressionFingerprintExtractsAllExpressions() {
    String source =
        """
                package test;
                public class Expr {
                    public int calc(int x, int y) {
                        return x * y + 1;
                    }
                }
                """;
    Launcher launcher = buildModel(source);
    CtType<?> type = launcher.getModel().getAllTypes().stream().findFirst().orElseThrow();
    CtMethod<?> method = type.getMethods().stream().findFirst().orElseThrow();

    java.util.List<String> fps = Fingerprinter.allExpressionFingerprints(method);
    // 应提取出多个表达式：x, y, x*y, 1, x*y+1
    assertThat(fps).hasSizeGreaterThanOrEqualTo(3);
  }

  private static Launcher buildModel(String... sources) {
    Launcher launcher = new Launcher();
    launcher.getEnvironment().setComplianceLevel(21);
    launcher.getEnvironment().setNoClasspath(true);
    launcher.getEnvironment().setCommentEnabled(false);
    launcher.getEnvironment().setShouldCompile(false);
    int i = 0;
    for (String src : sources) {
      launcher.addInputResource(new VirtualFile(src, "Source" + (i++) + ".java"));
    }
    launcher.buildModel();
    return launcher;
  }
}
