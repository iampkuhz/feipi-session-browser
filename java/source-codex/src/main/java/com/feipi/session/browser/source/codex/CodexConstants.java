package com.feipi.session.browser.source.codex;

/**
 * Codex 源适配器模块级常量。
 *
 * <p>集中定义 Codex 会话目录发现和解析使用的常量值， 避免硬编码和魔法数字散落在实现类中。
 */
public final class CodexConstants {

  /** Codex 会话主事件文件名。 */
  public static final String SESSION_FILE = "session.jsonl";

  /** Codex 线程数据库文件名。 */
  public static final String THREADS_DB = "threads.sqlite3";

  /** 单个日期目录允许发现的最大会话数。 */
  public static final int MAX_SESSIONS_PER_DAY = 10_000;

  private CodexConstants() {
    // 禁止实例化
  }
}
