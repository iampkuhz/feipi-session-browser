package com.feipi.session.browser.index.api.query;

import com.feipi.session.browser.query.api.PageResult;
import com.feipi.session.browser.query.api.SessionListFilter;
import java.util.List;
import java.util.Optional;

/** session 列表与查找查询读取端口。 */
public interface SessionQueryPort {

  /** 按 route 或 canonical session key 查找单个 session。 */
  Optional<SessionRecord> getSession(String sessionKey);

  /** 使用已校验的过滤、排序和分页列出 session。 */
  PageResult<SessionRecord> listSessions(SessionListFilter filter);

  /** 统计匹配给定过滤条件的 session 数量。 */
  long countSessions(SessionListFilter filter);

  /** 返回给定过滤条件下的完整列表摘要总量。 */
  SessionListSummary listSummary(SessionListFilter filter);

  /** 返回给定过滤条件下的 model 选项值。 */
  List<String> listModelOptions(SessionListFilter filter);

  /** 返回给定过滤条件下的 project 选项值。 */
  List<ProjectOption> listProjectOptions(SessionListFilter filter);

  /** 返回给定过滤条件下的紧凑聚合总量。 */
  SessionListAggregate listAggregate(SessionListFilter filter);
}
