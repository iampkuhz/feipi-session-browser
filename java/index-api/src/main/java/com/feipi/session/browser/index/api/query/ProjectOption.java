package com.feipi.session.browser.index.api.query;

/** session 列表过滤器中展示的 project 选项。 */
public interface ProjectOption {
  /** 返回规范化项目键。 */
  String projectKey();

  /** 返回项目显示名称。 */
  String projectName();
}
