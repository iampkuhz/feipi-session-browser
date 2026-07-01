package com.feipi.session.browser.source.claude;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import java.util.Objects;

/**
 * Claude Code history.jsonl 中的一条会话记录。
 *
 * <p>不可变值对象，表示 history.jsonl 中去重后的一条会话条目。
 *
 * @param sessionId Claude 会话 UUID
 * @param project 项目目录键（编码后的工作目录路径）
 * @param display 人类可读标题（display 字段）
 * @param timestamp 时间戳（毫秒）
 */
@DomainModel
public record ClaudeHistoryEntry(
    @CoreField String sessionId,
    @CoreField String project,
    @CoreField String display,
    @CoreField long timestamp) {

  public ClaudeHistoryEntry {
    Objects.requireNonNull(sessionId, "sessionId 不得为 null");
    Objects.requireNonNull(project, "project 不得为 null");
    if (sessionId.isEmpty()) {
      throw new IllegalArgumentException("sessionId 不得为空");
    }
    project = project == null ? "" : project;
    display = display == null ? "" : display;
  }
}
