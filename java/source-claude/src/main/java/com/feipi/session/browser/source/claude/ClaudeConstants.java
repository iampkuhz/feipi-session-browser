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

  /** Claude Code JSONL 事件中表示用户消息的类型值。 */
  public static final String EVENT_TYPE_USER = "user";

  /** Claude Code JSONL 事件中表示助手消息的类型值。 */
  public static final String EVENT_TYPE_ASSISTANT = "assistant";

  /** Claude Code JSONL 事件中表示结果消息的类型值。 */
  public static final String EVENT_TYPE_RESULT = "result";

  /** Claude Code JSONL 事件中表示摘要的类型值。 */
  public static final String EVENT_TYPE_SUMMARY = "summary";

  /** 当 JSONL 事件缺少 {@code type} 字段时使用的占位类型标识。 */
  public static final String EVENT_TYPE_UNKNOWN = "unknown";

  /** 诊断代码：事件缺少 {@code type} 字段。 */
  public static final String DIAG_CODE_MISSING_TYPE = "UNKNOWN_BLOCK_TYPE";

  private ClaudeConstants() {
    // 禁止实例化
  }
}
