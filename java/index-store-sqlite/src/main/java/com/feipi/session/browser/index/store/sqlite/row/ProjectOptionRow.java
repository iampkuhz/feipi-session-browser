package com.feipi.session.browser.index.store.sqlite.row;

import com.feipi.session.browser.index.api.query.ProjectOption;
import com.feipi.session.browser.common.validation.ParamChecks;

/**
 * 会话列表过滤器中的项目候选项。
 *
 * @param projectKey 规范化 project key。
 * @param projectName 项目显示名称。
 */
public record ProjectOptionRow(String projectKey, String projectName) implements ProjectOption {

  /** 验证项目 key 非空，项目名 null 时回退为空字符串。 */
  public ProjectOptionRow {
    ParamChecks.nonEmpty(projectKey, "projectKey");
    projectName = projectName == null ? "" : projectName;
  }
}
