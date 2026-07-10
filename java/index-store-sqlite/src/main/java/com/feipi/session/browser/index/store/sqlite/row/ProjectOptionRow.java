package com.feipi.session.browser.index.store.sqlite.row;

import com.feipi.session.browser.index.api.query.ProjectOption;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.NotBlank;

/**
 * 会话列表过滤器中的项目候选项。
 *
 * @param projectKey 规范化项目键值。
 * @param projectName 项目显示名称。
 */
public record ProjectOptionRow(
    /* 规范化项目键值。 */ @NotBlank String projectKey, /* 项目显示名称。 */ String projectName)
    implements ProjectOption {

  /** 紧凑构造器，校验 record component 约束；项目名 null 时回退为空字符串。 */
  public ProjectOptionRow {
    ValidationSupport.validateCanonicalConstructor(ProjectOptionRow.class, projectKey, projectName);
    projectName = projectName == null ? "" : projectName;
  }
}
