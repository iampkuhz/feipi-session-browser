package com.feipi.session.browser.index.api.query;

import com.feipi.session.browser.query.api.PageResult;
import com.feipi.session.browser.query.api.ProjectListFilter;

/** project 列表与详情聚合查询读取端口。 */
public interface ProjectQueryPort {

  /** 返回单个 project key 的聚合统计。 */
  ProjectStats projectStats(String projectKey);

  /** 统计匹配给定过滤条件的 project 数量。 */
  long countProjects(ProjectListFilter filter);

  /** 返回给定过滤条件下 project 列表摘要总量。 */
  ProjectListSummary projectListSummary(ProjectListFilter filter);

  /** 使用已校验的过滤、排序和分页列出 project 聚合行。 */
  PageResult<ProjectStats> listProjects(ProjectListFilter filter);
}
