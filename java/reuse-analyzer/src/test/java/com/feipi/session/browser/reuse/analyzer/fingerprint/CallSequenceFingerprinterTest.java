package com.feipi.session.browser.reuse.analyzer.fingerprint;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import spoon.Launcher;
import spoon.reflect.declaration.CtMethod;
import spoon.reflect.declaration.CtType;
import spoon.support.compiler.VirtualFile;

/** 调用序列指纹测试。 */
class CallSequenceFingerprinterTest {

  @Test
  void callSequenceFingerprintCapturesOrderedCalls() {
    String source =
        """
                package test;
                import java.util.List;
                import java.util.ArrayList;
                public class Caller {
                    public void doWork() {
                        List<String> list = new ArrayList<>();
                        list.add("hello");
                        int size = list.size();
                        list.clear();
                    }
                }
                """;
    CtMethod<?> method = buildSingleMethod(source);

    List<String> calls = CallSequenceFingerprinter.extractCallSequence(method);
    assertThat(calls).isNotEmpty();
    // 至少包含 ArrayList 构造和 add、size、clear
    assertThat(calls.size()).isGreaterThanOrEqualTo(3);

    // fingerprint 是稳定哈希
    String fp = CallSequenceFingerprinter.callSequenceFingerprint(method);
    assertThat(fp).hasSize(64).matches("[0-9a-f]{64}");
  }

  @Test
  void callSequenceFingerprintSameSequenceProducesSameHash() {
    String source1 =
        """
                package test;
                public class A { public void run() {
                    System.out.println("hello");
                    System.exit(0);
                }}
                """;
    String source2 =
        """
                package test;
                public class B { public void run() {
                    System.out.println("world");
                    System.exit(1);
                }}
                """;
    Launcher launcher = new Launcher();
    launcher.getEnvironment().setComplianceLevel(21);
    launcher.getEnvironment().setNoClasspath(true);
    launcher.getEnvironment().setCommentEnabled(false);
    launcher.getEnvironment().setShouldCompile(false);
    launcher.addInputResource(new VirtualFile(source1, "A.java"));
    launcher.addInputResource(new VirtualFile(source2, "B.java"));
    launcher.buildModel();

    var types = launcher.getModel().getAllTypes().stream().toList();
    CtMethod<?> mA = types.get(0).getMethods().stream().findFirst().orElseThrow();
    CtMethod<?> mB = types.get(1).getMethods().stream().findFirst().orElseThrow();

    List<String> seqA = CallSequenceFingerprinter.extractCallSequence(mA);
    List<String> seqB = CallSequenceFingerprinter.extractCallSequence(mB);

    // 调用序列相同（println + exit），fingerprint 应相同
    String fpA = CallSequenceFingerprinter.callSequenceFingerprint(mA);
    String fpB = CallSequenceFingerprinter.callSequenceFingerprint(mB);
    assertThat(fpA).isEqualTo(fpB);
  }

  @Test
  void callSequenceSimilarityIdenticalSequencesReturnOne() {
    List<String> seq = List.of("a#foo()", "b#bar()", "c#baz()");
    double sim = CallSequenceFingerprinter.callSequenceSimilarity(seq, seq);
    assertThat(sim).isEqualTo(1.0);
  }

  @Test
  void callSequenceSimilarityEmptySequencesReturnOne() {
    double sim = CallSequenceFingerprinter.callSequenceSimilarity(List.of(), List.of());
    assertThat(sim).isEqualTo(1.0);
  }

  @Test
  void callSequenceSimilarityOneEmptyReturnsZero() {
    List<String> seq = List.of("a#foo()");
    assertThat(CallSequenceFingerprinter.callSequenceSimilarity(seq, List.of())).isEqualTo(0.0);
    assertThat(CallSequenceFingerprinter.callSequenceSimilarity(List.of(), seq)).isEqualTo(0.0);
  }

  @Test
  void callSequenceSimilarityPartialOverlap() {
    List<String> seq1 = List.of("a#foo()", "b#bar()", "c#baz()");
    List<String> seq2 = List.of("a#foo()", "x#qux()", "c#baz()");
    double sim = CallSequenceFingerprinter.callSequenceSimilarity(seq1, seq2);
    assertThat(sim).isGreaterThan(0.0).isLessThan(1.0);
  }

  private CtMethod<?> buildSingleMethod(String source) {
    Launcher launcher = new Launcher();
    launcher.getEnvironment().setComplianceLevel(21);
    launcher.getEnvironment().setNoClasspath(true);
    launcher.getEnvironment().setCommentEnabled(false);
    launcher.getEnvironment().setShouldCompile(false);
    launcher.addInputResource(new VirtualFile(source, "Test.java"));
    launcher.buildModel();
    CtType<?> type = launcher.getModel().getAllTypes().stream().findFirst().orElseThrow();
    return type.getMethods().stream().findFirst().orElseThrow();
  }
}
