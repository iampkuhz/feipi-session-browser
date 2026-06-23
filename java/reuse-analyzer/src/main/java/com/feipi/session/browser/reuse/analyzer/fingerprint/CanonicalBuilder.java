package com.feipi.session.browser.reuse.analyzer.fingerprint;

import spoon.reflect.code.CtAnnotationFieldAccess;
import spoon.reflect.code.CtArrayRead;
import spoon.reflect.code.CtArrayWrite;
import spoon.reflect.code.CtAssert;
import spoon.reflect.code.CtAssignment;
import spoon.reflect.code.CtBinaryOperator;
import spoon.reflect.code.CtBlock;
import spoon.reflect.code.CtBreak;
import spoon.reflect.code.CtCase;
import spoon.reflect.code.CtCatch;
import spoon.reflect.code.CtComment;
import spoon.reflect.code.CtConditional;
import spoon.reflect.code.CtConstructorCall;
import spoon.reflect.code.CtContinue;
import spoon.reflect.code.CtDo;
import spoon.reflect.code.CtExpression;
import spoon.reflect.code.CtFieldAccess;
import spoon.reflect.code.CtFieldRead;
import spoon.reflect.code.CtFieldWrite;
import spoon.reflect.code.CtFor;
import spoon.reflect.code.CtForEach;
import spoon.reflect.code.CtIf;
import spoon.reflect.code.CtInvocation;
import spoon.reflect.code.CtLambda;
import spoon.reflect.code.CtLiteral;
import spoon.reflect.code.CtLocalVariable;
import spoon.reflect.code.CtNewArray;
import spoon.reflect.code.CtNewClass;
import spoon.reflect.code.CtOperatorAssignment;
import spoon.reflect.code.CtReturn;
import spoon.reflect.code.CtStatement;
import spoon.reflect.code.CtSuperAccess;
import spoon.reflect.code.CtSwitch;
import spoon.reflect.code.CtSwitchExpression;
import spoon.reflect.code.CtSynchronized;
import spoon.reflect.code.CtThisAccess;
import spoon.reflect.code.CtThrow;
import spoon.reflect.code.CtTry;
import spoon.reflect.code.CtTryWithResource;
import spoon.reflect.code.CtTypeAccess;
import spoon.reflect.code.CtUnaryOperator;
import spoon.reflect.code.CtVariableRead;
import spoon.reflect.code.CtVariableWrite;
import spoon.reflect.code.CtWhile;
import spoon.reflect.code.CtYieldStatement;
import spoon.reflect.declaration.CtMethod;
import spoon.reflect.declaration.CtModifiable;
import spoon.reflect.declaration.CtParameter;
import spoon.reflect.reference.CtExecutableReference;
import spoon.reflect.reference.CtFieldReference;
import spoon.reflect.reference.CtTypeReference;

/**
 * 基于 Spoon AST 的规范字符串构建器。 遍历 AST 节点，生成不含位置/格式/注释的规范表示。 用于计算 exact 和 alpha-normalized fingerprint。
 */
final class CanonicalBuilder {

  private final StringBuilder sb = new StringBuilder();
  private final boolean alphaNormalize;
  private int variableCounter;

  private CanonicalBuilder(boolean alphaNormalize) {
    this.alphaNormalize = alphaNormalize;
  }

  /** 构建方法的规范表示。 */
  static String buildMethod(CtMethod<?> method, boolean alphaNormalize) {
    CanonicalBuilder builder = new CanonicalBuilder(alphaNormalize);
    builder.visitMethodSignature(method);
    if (method.getBody() != null) {
      builder.visitStatements(method.getBody());
    }
    return builder.sb.toString();
  }

  /** 构建单个语句的规范表示。 */
  static String buildStatement(CtStatement stmt, boolean alphaNormalize) {
    CanonicalBuilder builder = new CanonicalBuilder(alphaNormalize);
    builder.visitStatement(stmt);
    return builder.sb.toString();
  }

  /** 构建表达式的规范表示。 */
  static String buildExpression(CtExpression<?> expr, boolean alphaNormalize) {
    CanonicalBuilder builder = new CanonicalBuilder(alphaNormalize);
    builder.visitExpression(expr);
    return builder.sb.toString();
  }

  private void visitMethodSignature(CtMethod<?> method) {
    sb.append("M(");
    // 修饰符（有序）
    if (method instanceof CtModifiable mod) {
      mod.getModifiers().stream().sorted().forEach(m -> sb.append(m.name()).append(','));
    }
    // 返回类型
    sb.append(typeRef(method.getType()));
    sb.append('#');
    // 方法名：exact 保留，alpha 替换为占位符
    if (!alphaNormalize) {
      sb.append(method.getSimpleName());
    } else {
      sb.append("_method");
    }
    sb.append('(');
    for (int i = 0; i < method.getParameters().size(); i++) {
      if (i > 0) sb.append(',');
      CtParameter<?> param = method.getParameters().get(i);
      sb.append(typeRef(param.getType()));
    }
    sb.append("))");
  }

  private void visitStatements(CtBlock<?> block) {
    for (CtStatement stmt : block.getStatements()) {
      if (stmt instanceof CtComment) {
        continue; // 跳过注释
      }
      visitStatement(stmt);
    }
  }

  private void visitStatement(CtStatement stmt) {
    if (stmt instanceof CtComment) {
      return;
    }
    if (stmt instanceof CtBlock<?> block) {
      sb.append("BLOCK{");
      visitStatements(block);
      sb.append("}");
      return;
    }
    if (stmt instanceof CtReturn<?> ret) {
      sb.append("RET(");
      if (ret.getReturnedExpression() != null) {
        visitExpression(ret.getReturnedExpression());
      }
      sb.append(")");
      return;
    }
    if (stmt instanceof CtIf ifStmt) {
      sb.append("IF(");
      visitExpression(ifStmt.getCondition());
      sb.append("){");
      visitStatement(ifStmt.getThenStatement());
      sb.append("}");
      if (ifStmt.getElseStatement() != null) {
        sb.append("ELSE{");
        visitStatement(ifStmt.getElseStatement());
        sb.append("}");
      }
      return;
    }
    if (stmt instanceof CtFor forStmt) {
      sb.append("FOR(");
      for (CtStatement init : forStmt.getForInit()) {
        visitStatement(init);
        sb.append(';');
      }
      sb.append('|');
      if (forStmt.getExpression() != null) {
        visitExpression(forStmt.getExpression());
      }
      sb.append('|');
      for (CtStatement update : forStmt.getForUpdate()) {
        visitStatement(update);
        sb.append(';');
      }
      sb.append("){");
      visitStatement(forStmt.getBody());
      sb.append("}");
      return;
    }
    if (stmt instanceof CtForEach forEach) {
      sb.append("FOREACH(");
      sb.append(typeRef(forEach.getVariable().getType()));
      sb.append(':');
      visitExpression(forEach.getExpression());
      sb.append("){");
      visitStatement(forEach.getBody());
      sb.append("}");
      return;
    }
    if (stmt instanceof CtWhile whileStmt) {
      sb.append("WHILE(");
      visitExpression(whileStmt.getLoopingExpression());
      sb.append("){");
      visitStatement(whileStmt.getBody());
      sb.append("}");
      return;
    }
    if (stmt instanceof CtDo doStmt) {
      sb.append("DO{");
      visitStatement(doStmt.getBody());
      sb.append("}WHILE(");
      visitExpression(doStmt.getLoopingExpression());
      sb.append(")");
      return;
    }
    if (stmt instanceof CtTryWithResource tryRes) {
      sb.append("TRY_R(");
      for (var res : tryRes.getResources()) {
        if (res instanceof CtStatement resStmt) {
          visitStatement(resStmt);
        } else {
          sb.append("RESOURCE(");
          sb.append(res.getClass().getSimpleName());
          sb.append(")");
        }
        sb.append(';');
      }
      sb.append("){");
      visitStatement(tryRes.getBody());
      sb.append("}");
      for (CtCatch c : tryRes.getCatchers()) {
        visitCatch(c);
      }
      if (tryRes.getFinalizer() != null) {
        sb.append("FINALLY{");
        visitStatements(tryRes.getFinalizer());
        sb.append("}");
      }
      return;
    }
    if (stmt instanceof CtTry tryStmt) {
      sb.append("TRY{");
      visitStatement(tryStmt.getBody());
      sb.append("}");
      for (CtCatch c : tryStmt.getCatchers()) {
        visitCatch(c);
      }
      if (tryStmt.getFinalizer() != null) {
        sb.append("FINALLY{");
        visitStatements(tryStmt.getFinalizer());
        sb.append("}");
      }
      return;
    }
    if (stmt instanceof CtThrow throwStmt) {
      sb.append("THROW(");
      visitExpression(throwStmt.getThrownExpression());
      sb.append(")");
      return;
    }
    if (stmt instanceof CtSwitch<?> switchStmt) {
      sb.append("SWITCH(");
      visitExpression(switchStmt.getSelector());
      sb.append("){");
      for (CtCase<?> c : switchStmt.getCases()) {
        visitCase(c);
      }
      sb.append("}");
      return;
    }
    if (stmt instanceof CtSynchronized sync) {
      sb.append("SYNC(");
      if (sync.getExpression() != null) {
        visitExpression(sync.getExpression());
      }
      sb.append("){");
      visitStatement(sync.getBlock());
      sb.append("}");
      return;
    }
    if (stmt instanceof CtAssert<?> assertStmt) {
      sb.append("ASSERT(");
      visitExpression(assertStmt.getAssertExpression());
      if (assertStmt.getExpression() != null) {
        sb.append(':');
        visitExpression(assertStmt.getExpression());
      }
      sb.append(")");
      return;
    }
    if (stmt instanceof CtBreak) {
      sb.append("BREAK");
      return;
    }
    if (stmt instanceof CtContinue) {
      sb.append("CONTINUE");
      return;
    }
    if (stmt instanceof CtLocalVariable<?> local) {
      sb.append("LOCAL(");
      sb.append(typeRef(local.getType()));
      sb.append('=');
      if (local.getDefaultExpression() != null) {
        visitExpression(local.getDefaultExpression());
      }
      sb.append(")");
      return;
    }
    if (stmt instanceof CtAssignment<?, ?> assign) {
      visitExpression(assign.getAssigned());
      sb.append("=");
      visitExpression(assign.getAssignment());
      return;
    }
    if (stmt instanceof CtOperatorAssignment<?, ?> opAssign) {
      visitExpression(opAssign.getAssigned());
      sb.append(opAssign.getKind().name());
      sb.append("=");
      visitExpression(opAssign.getAssignment());
      return;
    }
    if (stmt instanceof CtInvocation<?> inv) {
      visitExpression(inv);
      return;
    }
    // 兜底：使用元素类的简单名
    sb.append(stmt.getClass().getSimpleName());
  }

  private void visitCatch(CtCatch catcher) {
    sb.append("CATCH(");
    sb.append(typeRef(catcher.getParameter().getType()));
    sb.append("){");
    if (catcher.getBody() != null) {
      visitStatements(catcher.getBody());
    }
    sb.append("}");
  }

  private void visitCase(CtCase<?> caze) {
    sb.append("CASE(");
    for (CtExpression<?> selector : caze.getCaseExpressions()) {
      visitExpression(selector);
      sb.append(',');
    }
    sb.append("){");
    for (CtStatement stmt : caze.getStatements()) {
      visitStatement(stmt);
    }
    sb.append("}");
  }

  private void visitExpression(CtExpression<?> expr) {
    if (expr == null) {
      sb.append("NULL");
      return;
    }
    if (expr instanceof CtLiteral<?> lit) {
      sb.append("LIT(");
      if (lit.getType() != null) {
        sb.append(typeRef(lit.getType()));
      }
      sb.append(':');
      sb.append(lit.getValue());
      sb.append(")");
      return;
    }
    if (expr instanceof CtBinaryOperator<?> binOp) {
      sb.append("BINOP(");
      sb.append(binOp.getKind().name());
      sb.append(':');
      visitExpression(binOp.getLeftHandOperand());
      sb.append(',');
      visitExpression(binOp.getRightHandOperand());
      sb.append(")");
      return;
    }
    if (expr instanceof CtUnaryOperator<?> unOp) {
      sb.append("UNOP(");
      sb.append(unOp.getKind().name());
      sb.append(':');
      visitExpression(unOp.getOperand());
      sb.append(")");
      return;
    }
    if (expr instanceof CtInvocation<?> inv) {
      sb.append("INV(");
      if (inv.getTarget() != null && !(inv.getTarget() instanceof CtTypeAccess)) {
        visitExpression(inv.getTarget());
        sb.append('.');
      }
      sb.append(execRef(inv.getExecutable()));
      sb.append('(');
      for (int i = 0; i < inv.getArguments().size(); i++) {
        if (i > 0) sb.append(',');
        visitExpression(inv.getArguments().get(i));
      }
      sb.append("))");
      return;
    }
    if (expr instanceof CtConstructorCall<?> ctor) {
      sb.append("NEW(");
      sb.append(typeRef(ctor.getType()));
      sb.append('(');
      for (int i = 0; i < ctor.getArguments().size(); i++) {
        if (i > 0) sb.append(',');
        visitExpression(ctor.getArguments().get(i));
      }
      sb.append("))");
      return;
    }
    if (expr instanceof CtNewClass<?> newClass) {
      sb.append("NEW_ANON(");
      sb.append(typeRef(newClass.getType()));
      sb.append(")");
      return;
    }
    if (expr instanceof CtFieldRead<?> fieldRead) {
      sb.append("FREAD(");
      sb.append(fieldRef(fieldRead.getVariable()));
      sb.append(")");
      return;
    }
    if (expr instanceof CtFieldWrite<?> fieldWrite) {
      sb.append("FWRITE(");
      sb.append(fieldRef(fieldWrite.getVariable()));
      sb.append(")");
      return;
    }
    if (expr instanceof CtFieldAccess<?> fieldAccess) {
      sb.append("FACC(");
      sb.append(fieldRef(fieldAccess.getVariable()));
      sb.append(")");
      return;
    }
    if (expr instanceof CtArrayRead<?> arrayRead) {
      sb.append("AREAD(");
      visitExpression(arrayRead.getTarget());
      sb.append('[');
      visitExpression(arrayRead.getIndexExpression());
      sb.append("])");
      return;
    }
    if (expr instanceof CtArrayWrite<?> arrayWrite) {
      sb.append("AWRITE(");
      visitExpression(arrayWrite.getTarget());
      sb.append('[');
      visitExpression(arrayWrite.getIndexExpression());
      sb.append("])");
      return;
    }
    if (expr instanceof CtVariableRead<?> varRead) {
      if (alphaNormalize) {
        sb.append("VREAD(_v").append(variableCounter++).append(")");
      } else {
        sb.append("VREAD(");
        sb.append(varRead.getVariable().getSimpleName());
        sb.append(")");
      }
      return;
    }
    if (expr instanceof CtVariableWrite<?> varWrite) {
      if (alphaNormalize) {
        sb.append("VWRITE(_v").append(variableCounter++).append(")");
      } else {
        sb.append("VWRITE(");
        sb.append(varWrite.getVariable().getSimpleName());
        sb.append(")");
      }
      return;
    }
    if (expr instanceof CtThisAccess<?>) {
      sb.append("THIS");
      return;
    }
    if (expr instanceof CtSuperAccess<?>) {
      sb.append("SUPER");
      return;
    }
    if (expr instanceof CtTypeAccess<?> typeAccess) {
      sb.append("TACC(");
      sb.append(typeRef(typeAccess.getAccessedType()));
      sb.append(")");
      return;
    }
    if (expr instanceof CtAssignment<?, ?> assign) {
      visitExpression(assign.getAssigned());
      sb.append("=");
      visitExpression(assign.getAssignment());
      return;
    }
    if (expr instanceof CtConditional<?> cond) {
      sb.append("COND(");
      visitExpression(cond.getCondition());
      sb.append('?');
      visitExpression(cond.getThenExpression());
      sb.append(':');
      visitExpression(cond.getElseExpression());
      sb.append(")");
      return;
    }
    if (expr instanceof CtLambda<?> lambda) {
      sb.append("LAMBDA(");
      sb.append(lambda.getParameters().size());
      sb.append("){");
      if (lambda.getBody() != null) {
        visitStatements(lambda.getBody());
      } else if (lambda.getExpression() != null) {
        sb.append("RET(");
        visitExpression(lambda.getExpression());
        sb.append(")");
      }
      sb.append("})");
      return;
    }
    if (expr instanceof CtNewArray<?> newArray) {
      sb.append("NEWARR(");
      sb.append(typeRef(newArray.getType()));
      sb.append('{');
      for (int i = 0; i < newArray.getElements().size(); i++) {
        if (i > 0) sb.append(',');
        visitExpression(newArray.getElements().get(i));
      }
      sb.append("})");
      return;
    }
    if (expr instanceof CtSwitchExpression<?, ?> switchExpr) {
      sb.append("SWITCH_EXPR(");
      visitExpression(switchExpr.getSelector());
      sb.append(")");
      return;
    }
    if (expr instanceof CtAnnotationFieldAccess<?> annAccess) {
      sb.append("ANNREAD(");
      sb.append(fieldRef(annAccess.getVariable()));
      sb.append(")");
      return;
    }
    if (expr instanceof CtYieldStatement yieldStmt) {
      sb.append("YIELD(");
      if (yieldStmt.getExpression() != null) {
        visitExpression(yieldStmt.getExpression());
      }
      sb.append(")");
      return;
    }
    // 兜底：使用元素的简短类名
    sb.append(expr.getClass().getSimpleName());
  }

  private String typeRef(CtTypeReference<?> ref) {
    if (ref == null) return "?";
    String qname = ref.getQualifiedName();
    return qname != null ? qname : ref.getSimpleName();
  }

  private String execRef(CtExecutableReference<?> ref) {
    if (ref == null) return "?";
    String declName =
        ref.getDeclaringType() != null ? ref.getDeclaringType().getQualifiedName() : "?";
    return declName + "#" + ref.getSimpleName();
  }

  private String fieldRef(CtFieldReference<?> ref) {
    if (ref == null) return "?";
    String declName =
        ref.getDeclaringType() != null ? ref.getDeclaringType().getQualifiedName() : "?";
    return declName + "#" + ref.getSimpleName();
  }
}
