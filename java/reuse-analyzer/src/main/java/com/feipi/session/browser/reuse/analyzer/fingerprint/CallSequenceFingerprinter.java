package com.feipi.session.browser.reuse.analyzer.fingerprint;

import java.util.ArrayList;
import java.util.List;
import spoon.reflect.code.CtInvocation;
import spoon.reflect.declaration.CtMethod;
import spoon.reflect.reference.CtExecutableReference;
import spoon.reflect.reference.CtTypeReference;
import spoon.reflect.visitor.CtScanner;

/** 调用序列指纹：提取方法体内按顺序排列的已解析可执行签名列表。 使用解析后的 executable signature，保留顺序和关键 receiver/type 信息。 */
public final class CallSequenceFingerprinter {

  private CallSequenceFingerprinter() {}

  /** 提取方法内所有调用（按执行顺序）的可执行签名列表。 签名格式：declaringType#methodName(paramTypes) */
  public static List<String> extractCallSequence(CtMethod<?> method) {
    List<String> calls = new ArrayList<>();
    if (method.getBody() == null) {
      return calls;
    }
    method
        .getBody()
        .accept(
            new CtScanner() {
              @Override
              public <T> void visitCtInvocation(CtInvocation<T> invocation) {
                CtExecutableReference<?> exec = invocation.getExecutable();
                if (exec != null) {
                  calls.add(formatExecutableRef(exec));
                }
                super.visitCtInvocation(invocation);
              }
            });
    return calls;
  }

  /** 将调用序列转换为 fingerprint（SHA-256）。 */
  public static String callSequenceFingerprint(CtMethod<?> method) {
    List<String> calls = extractCallSequence(method);
    if (calls.isEmpty()) {
      return Fingerprinter.sha256("EMPTY_CALL_SEQ");
    }
    return Fingerprinter.sha256(String.join("->", calls));
  }

  /** 将两个方法的调用序列比较，返回匹配度（0.0~1.0）。 */
  public static double callSequenceSimilarity(List<String> seq1, List<String> seq2) {
    if (seq1.isEmpty() && seq2.isEmpty()) return 1.0;
    if (seq1.isEmpty() || seq2.isEmpty()) return 0.0;

    // 使用最长公共子序列（LCS）长度作为相似度
    int lcsLen = longestCommonSubsequenceLength(seq1, seq2);
    return (2.0 * lcsLen) / (seq1.size() + seq2.size());
  }

  private static int longestCommonSubsequenceLength(List<String> a, List<String> b) {
    int m = a.size();
    int n = b.size();
    int[][] dp = new int[m + 1][n + 1];
    for (int i = 1; i <= m; i++) {
      for (int j = 1; j <= n; j++) {
        if (a.get(i - 1).equals(b.get(j - 1))) {
          dp[i][j] = dp[i - 1][j - 1] + 1;
        } else {
          dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
        }
      }
    }
    return dp[m][n];
  }

  private static String formatExecutableRef(CtExecutableReference<?> ref) {
    String declaringType =
        ref.getDeclaringType() != null ? ref.getDeclaringType().getQualifiedName() : "?";
    StringBuilder sb = new StringBuilder();
    sb.append(declaringType).append('#').append(ref.getSimpleName());
    sb.append('(');
    List<CtTypeReference<?>> params = ref.getParameters();
    for (int i = 0; i < params.size(); i++) {
      if (i > 0) sb.append(',');
      String paramType = params.get(i).getQualifiedName();
      // 只取简单名以保持紧凑
      int dot = paramType.lastIndexOf('.');
      sb.append(dot >= 0 ? paramType.substring(dot + 1) : paramType);
    }
    sb.append(')');
    return sb.toString();
  }
}
