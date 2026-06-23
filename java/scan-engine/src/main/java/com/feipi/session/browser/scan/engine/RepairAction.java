package com.feipi.session.browser.scan.engine;

/**
 * Repair 操作对已索引会话的决策动作。
 *
 * <p>区分五种状态：源文件确认删除、根目录不可用、临时缺失、重命名检测和无需操作。 决策依据是源文件是否存在以及根目录是否可访问，不在网络文件系统假设 WAL/atomic move。
 *
 * <p>删除 DB row/artifact 的顺序和失败恢复：
 *
 * <ol>
 *   <li>先删除 {@code session_artifacts} 行（外键依赖）。
 *   <li>再删除 {@code sessions} 行。
 *   <li>单行失败不中断批量操作，错误记录到 {@link RepairSummary}。
 * </ol>
 */
public enum RepairAction {

  /**
   * 源文件已确认不存在，安全删除 DB row 和相关 artifact。
   *
   * <p>触发条件：根目录可访问，源文件不存在，且无法通过重命名检测找到新位置。
   */
  CONFIRMED_DELETE,

  /**
   * 根目录不可访问（如网络文件系统断开），保留 DB row 不做删除。
   *
   * <p>触发条件：{@link com.feipi.session.browser.source.spi.SourceAdapter#checkRoot} 返回 unsafe 或 IO 异常。
   */
  ROOT_UNAVAILABLE,

  /**
   * 源文件暂时缺失，可能是临时权限问题或文件系统延迟，暂不删除。
   *
   * <p>触发条件：源文件缺失但根目录可访问，且重命名检测未找到新位置；保留 DB row 供下次 repair 再判断。
   */
  SOURCE_MISSING_TEMPORARY,

  /**
   * 检测到会话已重命名或移动到新路径，更新 DB 中的 {@code file_path}。
   *
   * <p>触发条件：源文件不存在，但在同一源的其他项目目录中找到相同 session_id 的源文件。
   */
  RENAME_DETECTED,

  /**
   * 源文件存在且路径未变化，无需操作。
   *
   * <p>触发条件：源文件存在，{@code file_path} 与 DB 记录一致。
   */
  NO_ACTION
}
