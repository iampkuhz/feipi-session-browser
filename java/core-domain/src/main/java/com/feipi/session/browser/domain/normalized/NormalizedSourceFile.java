package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import java.util.Objects;
import java.util.Optional;

/**
 * 归一化源文件元数据。
 *
 * <p>表示对归一化制品有贡献的一个物理文件。源适配器在扫描归一化阶段创建这些记录，
 * 实例为不可变元数据传输对象。当源文件属于主会话时，子 agent 相关字段为空。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code role} 和 {@code path} 不得为 null。
 *   <li>{@code subagentId} 和 {@code parentToolUseId} 使用 {@code Optional} 区分 absent。
 * </ul>
 *
 * @param role 源角色，如 transcript 或 companion metadata
 * @param path 文件系统路径，用于溯源
 * @param subagentId 产生该源文件的可选子 agent 实例标识
 * @param parentToolUseId 可选的父工具调用边标识
 */
@DomainModel
public record NormalizedSourceFile(
    @CoreField String role,
    @CoreField String path,
    Optional<String> subagentId,
    Optional<String> parentToolUseId) {

  /**
   * 紧凑构造器，执行非空约束。
   *
   * @throws NullPointerException 当 role 或 path 为 null 时
   */
  public NormalizedSourceFile {
    Objects.requireNonNull(role, "role 不得为 null");
    Objects.requireNonNull(path, "path 不得为 null");
    subagentId = subagentId == null ? Optional.empty() : subagentId;
    parentToolUseId = parentToolUseId == null ? Optional.empty() : parentToolUseId;
  }
}
