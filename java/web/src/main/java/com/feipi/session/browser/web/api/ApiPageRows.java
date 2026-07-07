package com.feipi.session.browser.web.api;

import com.feipi.session.browser.web.api.PageApiDtos.PageStateDto;
import com.feipi.session.browser.web.api.PageApiDtos.PaginationDto;
import com.feipi.session.browser.web.page.QueryParams;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;

/** 列表 rows API 的分页响应共享构造器。 */
final class ApiPageRows {

  private ApiPageRows() {}

  /** 构建带 filters、rows、pagination 与 state 的列表响应。 */
  static <F, R> Object response(
      Map<String, String> params,
      Function<Map<String, String>, F> filters,
      List<R> rows,
      long totalCount,
      PageStateDto state,
      RowsResponseFactory<F, R> factory) {
    Objects.requireNonNull(params, "params must not be null");
    Objects.requireNonNull(filters, "filters must not be null");
    Objects.requireNonNull(rows, "rows must not be null");
    Objects.requireNonNull(state, "state must not be null");
    Objects.requireNonNull(factory, "factory must not be null");
    return factory.create(
        ApiResponses.SCHEMA_VERSION,
        filters.apply(params),
        rows,
        PaginationDto.of(
            QueryParams.parsePage(params), QueryParams.parsePageSize(params), totalCount),
        state);
  }

  @FunctionalInterface
  interface RowsResponseFactory<F, R> {
    /** 创建实际 API rows response 对象。 */
    Object create(
        String schemaVersion,
        F filters,
        List<R> rows,
        PaginationDto pagination,
        PageStateDto state);
  }
}
