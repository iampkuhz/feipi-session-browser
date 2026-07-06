package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.domain.annotation.DomainModel;
import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * 源文件角色枚举。
 *
 * <p>标识源文件在归一化制品中的角色。兼容旧的 {@code transcript}/{@code companion} 值， 并提供 normalized v3 的展示角色值。
 */
@DomainModel
@RequiredArgsConstructor
public enum SourceFileRole {
  /** 主会话转录文件。 */
  TRANSCRIPT("transcript"),

  /** 伴随元数据文件。 */
  COMPANION("companion"),

  /** 主会话文件。 */
  MAIN_SESSION("main_session"),

  /** Codex 主会话 rollout 源文件。 */
  CODEX_ROLLOUT("codex_rollout"),

  /** 子 agent 会话文件。 */
  SUBAGENT_SESSION("subagent_session");

  /** 稳定外部协议值。 */
  @Getter private final String value;

  /**
   * 根据字符串值查找对应的枚举常量。
   *
   * @param value 与 Python 兼容的字符串值
   * @return 对应的枚举常量
   * @throws IllegalArgumentException 当值不在合法范围内时
   */
  public static SourceFileRole fromValue(String value) {
    for (SourceFileRole role : values()) {
      if (role.value.equals(value)) {
        return role;
      }
    }
    throw new IllegalArgumentException("invalid source file role: " + value);
  }
}
