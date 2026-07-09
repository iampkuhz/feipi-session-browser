package com.feipi.session.browser.index.api.query;

/** 索引查询端口暴露的抽象 session 查询结果。 */
public interface SessionRecord {
  String sessionKey();

  String agent();

  String sessionId();

  String title();

  String projectKey();

  String projectName();

  String cwd();

  String startedAt();

  String endedAt();

  double durationSeconds();

  double modelExecutionSeconds();

  double toolExecutionSeconds();

  String model();

  String gitBranch();

  String source();

  long userMessageCount();

  long assistantMessageCount();

  long toolCallCount();

  long outputTokens();

  long freshInputTokens();

  long cacheReadTokens();

  long cacheWriteTokens();

  long totalTokens();

  long failedToolCount();

  long subagentInstanceCount();

  double indexedAt();

  double fileMtime();

  String filePath();
}
