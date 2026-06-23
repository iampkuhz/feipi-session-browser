package com.feipi.session.browser.reuse.analyzer;

import com.feipi.session.browser.reuse.analyzer.model.Ownership;
import spoon.reflect.code.CtFieldRead;
import spoon.reflect.code.CtFieldWrite;
import spoon.reflect.code.CtInvocation;
import spoon.reflect.code.CtReturn;
import spoon.reflect.code.CtStatement;
import spoon.reflect.declaration.CtMethod;
import spoon.reflect.declaration.CtType;
import spoon.reflect.reference.CtFieldReference;
import spoon.reflect.visitor.CtScanner;

/**
 * 方法归属分类器。 根据方法对 owner type 的绑定强度分类为六种 ownership 之一。
 *
 * <p>分类依据：
 *
 * <ul>
 *   <li>是否访问 instance field
 *   <li>是否调用 owner 的 private 方法
 *   <li>是否维护 owner invariant
 *   <li>是否引用 nested type
 *   <li>是否只使用参数和 JDK API
 *   <li>是否涉及 I/O、path、hash、encoding、time、process、database 调用
 *   <li>是否有跨模块调用者
 *   <li>是否涉及 static/mutable static state
 * </ul>
 *
 * <p>注意：static 是 ownership 信号，不是 violation。
 */
public final class OwnershipClassifier {

  private OwnershipClassifier() {}

  /** 分类方法的归属。 */
  public static Ownership classify(CtMethod<?> method) {
    if (isFactoryOrConstructor(method)) {
      return Ownership.FACTORY_OR_CONSTRUCTOR;
    }
    if (isTrivialDelegation(method)) {
      return Ownership.TRIVIAL_DELEGATION;
    }

    // 使用数组作为可变标志位容器，以便在匿名内部类中修改。
    // 下标含义：[0]=是否访问 owner 字段 [1]=是否调用 owner 私有方法
    // [2]=是否使用可变静态状态 [3]=是否仅使用参数和 JDK 类（初始为 true）
    // [4]=是否包含 I/O 或系统调用
    boolean[] flags = new boolean[] {false, false, false, true, false};

    CtType<?> owner = method.getDeclaringType();
    String ownerQName = owner != null ? owner.getQualifiedName() : "";

    if (method.getBody() != null) {
      method
          .getBody()
          .accept(
              new CtScanner() {
                @Override
                public <T> void visitCtFieldRead(CtFieldRead<T> fieldRead) {
                  analyzeFieldRef(fieldRead.getVariable(), ownerQName, flags);
                  super.visitCtFieldRead(fieldRead);
                }

                @Override
                public <T> void visitCtFieldWrite(CtFieldWrite<T> fieldWrite) {
                  analyzeFieldRef(fieldWrite.getVariable(), ownerQName, flags);
                  super.visitCtFieldWrite(fieldWrite);
                }

                @Override
                public <T> void visitCtInvocation(CtInvocation<T> invocation) {
                  var exec = invocation.getExecutable();
                  if (exec != null && exec.getDeclaringType() != null) {
                    String declaringType = exec.getDeclaringType().getQualifiedName();
                    // 调用 owner 的 private 方法
                    if (declaringType.equals(ownerQName) && exec.isFinal()) {
                      flags[1] = true;
                    }
                    // 检查是否为 JDK 类
                    if (!isJdkClass(declaringType)) {
                      flags[3] = false;
                    }
                    // 检查 I/O 和系统调用
                    if (isIoOrSystemCall(declaringType, exec.getSimpleName())) {
                      flags[4] = true;
                    }
                  }
                  super.visitCtInvocation(invocation);
                }
              });
    }

    boolean accessesOwnerField = flags[0];
    boolean callsOwnerPrivate = flags[1];
    boolean usesStaticMutableState = flags[2];
    boolean usesOnlyParamsAndJdk = flags[3];
    boolean hasIoOrSystemCalls = flags[4];

    // 分类逻辑
    if (method.isStatic() && usesStaticMutableState) {
      // mutable static state → 作为信号记录，返回 OWNER_BOUND
      return Ownership.OWNER_BOUND;
    }
    if (accessesOwnerField || callsOwnerPrivate) {
      return Ownership.OWNER_BOUND;
    }
    if (usesOnlyParamsAndJdk && !hasIoOrSystemCalls) {
      return Ownership.DETACHED_BEHAVIOR;
    }
    if (hasIoOrSystemCalls && !accessesOwnerField) {
      return Ownership.SHARED_CAPABILITY;
    }
    if (!usesOnlyParamsAndJdk && !accessesOwnerField) {
      return Ownership.PROVIDER_SPECIFIC_CAPABILITY;
    }
    return Ownership.OWNER_BOUND;
  }

  private static boolean isFactoryOrConstructor(CtMethod<?> method) {
    if (method.getSimpleName().equals("<init>")) return true;
    // 检查是否返回 owner 类型（工厂方法模式）
    CtType<?> owner = method.getDeclaringType();
    if (owner != null && method.getType() != null) {
      if (method.getType().getQualifiedName().equals(owner.getQualifiedName())) {
        return true;
      }
    }
    // 检查方法名是否以 "create"、"build"、"of"、"from" 开头
    String name = method.getSimpleName();
    return name.startsWith("create")
        || name.startsWith("build")
        || name.startsWith("newInstance")
        || name.startsWith("factory");
  }

  private static boolean isTrivialDelegation(CtMethod<?> method) {
    if (method.getBody() == null) return false;
    var stmts = method.getBody().getStatements();
    // 只有一条 return 或一条 invocation 语句
    if (stmts.size() == 1) {
      CtStatement stmt = stmts.get(0);
      if (stmt instanceof CtReturn<?> ret) {
        var returnedExpr = ret.getReturnedExpression();
        // 委托给 owner field 的方法调用 → TRIVIAL_DELEGATION
        if (returnedExpr instanceof CtInvocation<?> invocation) {
          return isFieldDelegation(invocation, method);
        }
      }
      if (stmt instanceof CtInvocation<?> invocation) {
        return isFieldDelegation(invocation, method);
      }
    }
    return false;
  }

  /** 判断调用是否是委托给 owner 的 instance field 的方法。 例如 {@code items.size()} 其中 items 是 owner 的 field。 */
  private static boolean isFieldDelegation(CtInvocation<?> invocation, CtMethod<?> method) {
    var target = invocation.getTarget();
    if (target instanceof CtFieldRead<?> fieldRead) {
      return isOwnerFieldAccess(fieldRead.getVariable(), method);
    }
    return false;
  }

  /** 判断 field 引用是否指向 owner type 自身的 instance field。 */
  private static boolean isOwnerFieldAccess(CtFieldReference<?> ref, CtMethod<?> method) {
    if (ref == null) return false;
    CtType<?> owner = method.getDeclaringType();
    if (owner == null) return false;
    String ownerQName = owner.getQualifiedName();
    // 检查声明类型是否是 owner
    if (ref.getDeclaringType() != null
        && ref.getDeclaringType().getQualifiedName().equals(ownerQName)) {
      return true;
    }
    // 如果 declaring type 未解析（noClasspath），尝试通过 field 名称匹配 owner 的 field
    return owner.getField(ref.getSimpleName()) != null;
  }

  private static void analyzeFieldRef(CtFieldReference<?> ref, String ownerQName, boolean[] flags) {
    if (ref != null && ref.getDeclaringType() != null) {
      if (ref.getDeclaringType().getQualifiedName().equals(ownerQName)) {
        // 访问 owner 的 field
        if (!ref.isStatic()) {
          flags[0] = true;
        } else {
          // static field → 检查是否 mutable
          flags[2] = true;
        }
      }
    }
  }

  private static boolean isJdkClass(String qualifiedName) {
    return qualifiedName.startsWith("java.")
        || qualifiedName.startsWith("javax.")
        || qualifiedName.startsWith("sun.")
        || qualifiedName.startsWith("jdk.");
  }

  private static boolean isIoOrSystemCall(String declaringType, String methodName) {
    // I/O 相关
    if (declaringType.startsWith("java.io.") || declaringType.startsWith("java.nio.")) {
      return true;
    }
    // Path 相关
    if (declaringType.equals("java.nio.file.Path")
        || declaringType.equals("java.nio.file.Paths")
        || declaringType.equals("java.nio.file.Files")) {
      return true;
    }
    // 哈希和编码相关
    if (declaringType.startsWith("java.security.")
        || declaringType.equals("java.util.Base64")
        || declaringType.startsWith("javax.crypto.")) {
      return true;
    }
    // 时间相关
    if (declaringType.startsWith("java.time.")) {
      return true;
    }
    // 进程相关
    if (declaringType.equals("java.lang.ProcessBuilder")
        || declaringType.equals("java.lang.Runtime")) {
      return true;
    }
    return false;
  }
}
