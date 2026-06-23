package com.feipi.session.browser.reuse.analyzer;

import spoon.reflect.declaration.CtMethod;
import spoon.reflect.declaration.CtType;

/**
 * 稳定的 methodId 生成器。 格式：declaringType#methodName(paramType1,paramType2)returnType 不包含位置信息，确保跨构建稳定。
 */
public final class MethodIdGenerator {

  private MethodIdGenerator() {}

  /** 生成方法的全局唯一稳定标识符。 */
  public static String methodId(CtMethod<?> method) {
    CtType<?> declaringType = method.getDeclaringType();
    String typeName = declaringType != null ? declaringType.getQualifiedName() : "?";
    StringBuilder sb = new StringBuilder();
    sb.append(typeName).append('#').append(method.getSimpleName()).append('(');
    var params = method.getParameters();
    for (int i = 0; i < params.size(); i++) {
      if (i > 0) sb.append(',');
      if (params.get(i).getType() != null) {
        sb.append(params.get(i).getType().getQualifiedName());
      } else {
        sb.append("?");
      }
    }
    sb.append(')');
    if (method.getType() != null) {
      sb.append(method.getType().getQualifiedName());
    }
    return sb.toString();
  }
}
