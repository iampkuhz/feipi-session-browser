package com.feipi.session.browser.reuse.analyzer.fingerprint;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.List;
import spoon.reflect.code.CtBlock;
import spoon.reflect.code.CtExpression;
import spoon.reflect.code.CtStatement;
import spoon.reflect.declaration.CtMethod;

/**
 * AST 指纹计算入口。 提供 exact、alpha、statement、expression 和 call sequence 指纹。 所有指纹使用 SHA-256 哈希，确保定长和均匀分布。
 */
public final class Fingerprinter {

  private static final String HASH_ALGORITHM = "SHA-256";

  private Fingerprinter() {}

  /** 计算方法的 exact fingerprint：保留类型、调用目标、运算符、字面量，移除位置/格式/注释。 */
  public static String exactMethodFingerprint(CtMethod<?> method) {
    String canonical = CanonicalBuilder.buildMethod(method, false);
    return sha256(canonical);
  }

  /** 计算方法的 alpha-normalized fingerprint：参数和局部变量按首次出现顺序标准化。 */
  public static String alphaMethodFingerprint(CtMethod<?> method) {
    String canonical = CanonicalBuilder.buildMethod(method, true);
    return sha256(canonical);
  }

  /** 计算单条语句的 fingerprint。 */
  public static String statementFingerprint(CtStatement statement) {
    String canonical = CanonicalBuilder.buildStatement(statement, false);
    return sha256(canonical);
  }

  /** 计算表达式的 fingerprint。 */
  public static String expressionFingerprint(CtExpression<?> expression) {
    String canonical = CanonicalBuilder.buildExpression(expression, false);
    return sha256(canonical);
  }

  /** 计算语句块的 rolling fingerprint。 生成所有连续子序列（长度 2..N）的指纹列表，使用滚动哈希。 返回有序列表，每个元素是该子序列的 SHA-256。 */
  public static List<String> rollingStatementFingerprints(CtBlock<?> block) {
    List<CtStatement> stmts = new ArrayList<>();
    for (CtStatement stmt : block.getStatements()) {
      if (!(stmt instanceof spoon.reflect.code.CtComment)) {
        stmts.add(stmt);
      }
    }
    List<String> result = new ArrayList<>();
    for (int windowSize = 2; windowSize <= stmts.size(); windowSize++) {
      for (int start = 0; start + windowSize <= stmts.size(); start++) {
        StringBuilder sb = new StringBuilder();
        for (int i = start; i < start + windowSize; i++) {
          sb.append(CanonicalBuilder.buildStatement(stmts.get(i), false));
          if (i < start + windowSize - 1) {
            sb.append('|');
          }
        }
        result.add(sha256(sb.toString()));
      }
    }
    return result;
  }

  /** 从方法体提取所有单语句指纹。 包含 block 内所有非注释语句。 */
  public static List<String> allStatementFingerprints(CtMethod<?> method) {
    List<String> result = new ArrayList<>();
    if (method.getBody() != null) {
      collectStatementFingerprints(method.getBody(), result);
    }
    return result;
  }

  /** 从方法体提取所有表达式指纹。 递归遍历所有子表达式。 */
  public static List<String> allExpressionFingerprints(CtMethod<?> method) {
    List<String> result = new ArrayList<>();
    if (method.getBody() != null) {
      collectExpressionFingerprints(method.getBody(), result);
    }
    return result;
  }

  /** 递归收集 block 内所有语句的指纹。 */
  private static void collectStatementFingerprints(CtBlock<?> block, List<String> result) {
    for (CtStatement stmt : block.getStatements()) {
      if (stmt instanceof spoon.reflect.code.CtComment) {
        continue;
      }
      result.add(statementFingerprint(stmt));
      // 递归进入嵌套 block
      collectNestedStatements(stmt, result);
    }
  }

  private static void collectNestedStatements(CtStatement stmt, List<String> result) {
    if (stmt instanceof CtBlock<?> block) {
      collectStatementFingerprints(block, result);
    } else if (stmt instanceof spoon.reflect.code.CtIf ifStmt) {
      collectStatementFrom(ifStmt.getThenStatement(), result);
      if (ifStmt.getElseStatement() != null) {
        collectStatementFrom(ifStmt.getElseStatement(), result);
      }
    } else if (stmt instanceof spoon.reflect.code.CtFor forStmt) {
      collectStatementFrom(forStmt.getBody(), result);
    } else if (stmt instanceof spoon.reflect.code.CtForEach forEach) {
      collectStatementFrom(forEach.getBody(), result);
    } else if (stmt instanceof spoon.reflect.code.CtWhile whileStmt) {
      collectStatementFrom(whileStmt.getBody(), result);
    } else if (stmt instanceof spoon.reflect.code.CtDo doStmt) {
      collectStatementFrom(doStmt.getBody(), result);
    } else if (stmt instanceof spoon.reflect.code.CtTry tryStmt) {
      collectStatementFrom(tryStmt.getBody(), result);
      for (var catcher : tryStmt.getCatchers()) {
        if (catcher.getBody() != null) {
          collectStatementFingerprints(catcher.getBody(), result);
        }
      }
      if (tryStmt.getFinalizer() != null) {
        collectStatementFingerprints(tryStmt.getFinalizer(), result);
      }
    } else if (stmt instanceof spoon.reflect.code.CtTryWithResource tryRes) {
      collectStatementFrom(tryRes.getBody(), result);
      for (var catcher : tryRes.getCatchers()) {
        if (catcher.getBody() != null) {
          collectStatementFingerprints(catcher.getBody(), result);
        }
      }
      if (tryRes.getFinalizer() != null) {
        collectStatementFingerprints(tryRes.getFinalizer(), result);
      }
    } else if (stmt instanceof spoon.reflect.code.CtSynchronized sync) {
      if (sync.getBlock() != null) {
        collectStatementFrom(sync.getBlock(), result);
      }
    } else if (stmt instanceof spoon.reflect.code.CtSwitch<?> switchStmt) {
      for (var caze : switchStmt.getCases()) {
        for (var s : caze.getStatements()) {
          collectStatementFrom(s, result);
        }
      }
    }
  }

  private static void collectStatementFrom(CtStatement stmt, List<String> result) {
    if (stmt instanceof CtBlock<?> block) {
      collectStatementFingerprints(block, result);
    } else if (stmt != null) {
      result.add(statementFingerprint(stmt));
      collectNestedStatements(stmt, result);
    }
  }

  /** 递归收集所有表达式指纹。 */
  private static void collectExpressionFingerprints(CtStatement stmt, List<String> result) {
    stmt.getElements(
            new spoon.reflect.visitor.Filter<CtExpression<?>>() {
              @Override
              public boolean matches(CtExpression<?> element) {
                // 收集所有非空表达式
                return true;
              }
            })
        .forEach(expr -> result.add(expressionFingerprint(expr)));
  }

  /** 计算输入字符串的哈希摘要值。 */
  static String sha256(String input) {
    try {
      MessageDigest digest = MessageDigest.getInstance(HASH_ALGORITHM);
      byte[] hash = digest.digest(input.getBytes(StandardCharsets.UTF_8));
      return bytesToHex(hash);
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException("SHA-256 not available", e);
    }
  }

  private static String bytesToHex(byte[] bytes) {
    StringBuilder sb = new StringBuilder(bytes.length * 2);
    for (byte b : bytes) {
      sb.append(String.format("%02x", b));
    }
    return sb.toString();
  }
}
