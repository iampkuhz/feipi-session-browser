package com.feipi.session.browser.reuse.analyzer;

import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import spoon.reflect.declaration.CtClass;
import spoon.reflect.declaration.CtInterface;
import spoon.reflect.declaration.CtType;
import spoon.reflect.reference.CtTypeReference;

/**
 * Peer group 解析器。 类型满足以下任一条件即为 peer：
 *
 * <ul>
 *   <li>实现相同非 JDK interface
 *   <li>继承相同项目 abstract class
 *   <li>被同一 registry/factory/ServiceLoader extension point 注册
 * </ul>
 *
 * <p>注意：peer group 基于共享的 interface/abstract base/registry， 不得只依赖类名以 Adapter/Service/Controller 等结尾。
 */
public final class PeerGroupResolver {

  private PeerGroupResolver() {}

  /** 解析类型的 peer group。 返回 peer group id（可能为 null 表示无 peer group）。 同一 peer group 的类型共享相同 id。 */
  public static String resolvePeerGroup(CtType<?> type) {
    Set<String> groupIds = new LinkedHashSet<>();

    // 1. 检查实现的非 JDK interface
    if (type instanceof CtClass<?> ctClass) {
      for (CtTypeReference<?> iface : ctClass.getSuperInterfaces()) {
        String qname = iface.getQualifiedName();
        if (!isJdkType(qname)) {
          groupIds.add("iface:" + qname);
        }
      }
    } else if (type instanceof CtInterface<?> ctIface) {
      // interface 继承的其他 interface
      for (CtTypeReference<?> superIface : ctIface.getSuperInterfaces()) {
        String qname = superIface.getQualifiedName();
        if (!isJdkType(qname)) {
          groupIds.add("iface:" + qname);
        }
      }
    }

    // 2. 检查继承的项目 abstract class
    if (type instanceof CtClass<?> ctClass) {
      CtTypeReference<?> superClass = ctClass.getSuperclass();
      if (superClass != null && !isJdkType(superClass.getQualifiedName())) {
        // 尝试解析父类是否为 abstract
        try {
          CtType<?> resolved = superClass.getTypeDeclaration();
          if (resolved instanceof CtClass<?> parentClass
              && parentClass.hasModifier(spoon.reflect.declaration.ModifierKind.ABSTRACT)) {
            groupIds.add("abstract:" + superClass.getQualifiedName());
          }
        } catch (Exception e) {
          // 无法解析，跳过
          groupIds.add("abstract:" + superClass.getQualifiedName());
        }
      }
    }

    if (groupIds.isEmpty()) {
      return null;
    }
    // 使用排序后的第一个 group id 作为主 group
    return groupIds.stream().sorted().findFirst().orElse(null);
  }

  /** 从类型集合中构建 peer group 映射。 key 是 peer group id，value 是该 group 中的类型 qualified name 列表。 */
  public static Map<String, List<String>> buildPeerGroups(Collection<CtType<?>> types) {
    Map<String, List<String>> groups = new LinkedHashMap<>();
    for (CtType<?> type : types) {
      String groupId = resolvePeerGroup(type);
      if (groupId != null) {
        groups.computeIfAbsent(groupId, k -> new ArrayList<>()).add(type.getQualifiedName());
      }
    }
    // 排序各组内的类型
    for (var entry : groups.entrySet()) {
      entry.setValue(entry.getValue().stream().sorted().distinct().toList());
    }
    // 只保留至少有两个成员的 group（真正的 peer group）
    groups.entrySet().removeIf(e -> e.getValue().size() < 2);
    return groups;
  }

  private static boolean isJdkType(String qualifiedName) {
    return qualifiedName.startsWith("java.")
        || qualifiedName.startsWith("javax.")
        || qualifiedName.startsWith("sun.")
        || qualifiedName.startsWith("jdk.");
  }
}
