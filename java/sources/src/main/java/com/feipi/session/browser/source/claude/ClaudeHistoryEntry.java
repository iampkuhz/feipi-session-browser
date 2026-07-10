package com.feipi.session.browser.source.claude;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

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
    /* Claude 会话唯一标识 */
    @CoreField @NotBlank String sessionId,
    /* 项目目录键（编码后的工作目录路径） */
    @CoreField @NotNull String project,
    /* 人类可读标题（display 字段） */
    @CoreField String display,
    /* 时间戳（毫秒） */
    @CoreField long timestamp) {

  /** 校验并规范化 Claude history 条目字段。 */
  public ClaudeHistoryEntry {
    ValidationSupport.validateCanonicalConstructor(
        ClaudeHistoryEntry.class, sessionId, project, display, timestamp);
    display = display == null ? "" : display;
  }
}
