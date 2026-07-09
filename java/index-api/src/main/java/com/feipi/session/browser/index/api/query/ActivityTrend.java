package com.feipi.session.browser.index.api.query;

/** 每日 prompt 活动趋势行。 */
public interface ActivityTrend {
  String date();

  long claudePrompts();

  long codexPrompts();

  long qoderPrompts();

  long totalPrompts();

  long assistantTurns();

  long toolCalls();
}
