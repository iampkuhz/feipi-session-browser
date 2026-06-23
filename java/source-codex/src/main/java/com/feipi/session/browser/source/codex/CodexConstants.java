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

  /** Codex 会话索引文件名。 */
  public static final String SESSION_INDEX_FILE = "session_index.jsonl";

  /** 单个日期目录允许发现的最大会话数。 */
  public static final int MAX_SESSIONS_PER_DAY = 10_000;

  /** Codex JSONL 事件中表示会话元数据的类型值。 */
  public static final String EVENT_TYPE_SESSION_META = "session_meta";

  /** Codex JSONL 事件中表示事件消息的类型值。 */
  public static final String EVENT_TYPE_EVENT_MSG = "event_msg";

  /** Codex JSONL 事件中表示响应项的类型值。 */
  public static final String EVENT_TYPE_RESPONSE_ITEM = "response_item";

  /** 当 JSONL 事件缺少 {@code type} 字段时使用的占位类型标识。 */
  public static final String EVENT_TYPE_UNKNOWN = "unknown";

  /** 诊断代码：事件缺少 {@code type} 字段。 */
  public static final String DIAG_CODE_MISSING_TYPE = "UNKNOWN_BLOCK_TYPE";

  /** 诊断代码：SQLite 数据库读取失败。 */
  public static final String DIAG_CODE_SQLITE_ERROR = "SQLITE_READ_ERROR";

  /** 诊断代码：SQLite JDBC 驱动不可用。 */
  public static final String DIAG_CODE_DRIVER_MISSING = "SQLITE_DRIVER_MISSING";

  /** 诊断代码：rollout 文件未找到。 */
  public static final String DIAG_CODE_ROLLOUT_NOT_FOUND = "ROLLOUT_NOT_FOUND";

  private CodexConstants() {
    // 禁止实例化
  }
}
