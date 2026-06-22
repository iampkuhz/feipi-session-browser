package com.feipi.session.browser.source.claude;

/**
 * Claude Code 源适配器模块级常量。
 *
 * <p>集中定义 Claude Code 会话目录发现和解析使用的常量值， 避免硬编码和魔法数字散落在实现类中。
 */
public final class ClaudeConstants {

  /** Claude Code 会话项目子目录名称。 */
  public static final String PROJECTS_DIR = "projects";

  /** Claude Code 会话文件后缀。 */
  public static final String SESSION_FILE_SUFFIX = ".jsonl";

  /** 单个项目目录允许发现的最大会话文件数。 */
  public static final int MAX_SESSIONS_PER_PROJECT = 10_000;

  private ClaudeConstants() {
    // 禁止实例化
  }
}
