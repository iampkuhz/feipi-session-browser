package com.feipi.session.browser.web.page;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/** QueryParams 查询参数解析测试。 */
@DisplayName("QueryParams 查询参数解析测试")
class QueryParamsTest {

  @Nested
  @DisplayName("分页参数解析")
  class PaginationParsing {

    @Test
    @DisplayName("默认页码为 1")
    void defaultPage() {
      assertThat(QueryParams.parsePage(Map.of())).isEqualTo(1);
    }

    @Test
    @DisplayName("合法页码返回原值")
    void validPage() {
      assertThat(QueryParams.parsePage(Map.of("page", "5"))).isEqualTo(5);
    }

    @Test
    @DisplayName("非法页码回退到 1")
    void invalidPage() {
      assertThat(QueryParams.parsePage(Map.of("page", "abc"))).isEqualTo(1);
    }

    @Test
    @DisplayName("负数页码回退到 1")
    void negativePage() {
      assertThat(QueryParams.parsePage(Map.of("page", "-3"))).isEqualTo(1);
    }

    @Test
    @DisplayName("默认页面大小为 25")
    void defaultPageSize() {
      assertThat(QueryParams.parsePageSize(Map.of())).isEqualTo(25);
    }

    @Test
    @DisplayName("合法页面大小 50 返回原值")
    void validPageSize() {
      assertThat(QueryParams.parsePageSize(Map.of("page_size", "50"))).isEqualTo(50);
    }

    @Test
    @DisplayName("非法页面大小回退到 25")
    void invalidPageSize() {
      assertThat(QueryParams.parsePageSize(Map.of("page_size", "999"))).isEqualTo(25);
    }
  }

  @Nested
  @DisplayName("UI 排序键回显")
  class UiSortKey {

    @Test
    @DisplayName("ended-at 映射为 updated")
    void endedAtToUpdated() {
      assertThat(QueryParams.uiSortKey(Map.of("sort", "ended-at"))).isEqualTo("updated");
    }

    @Test
    @DisplayName("空 sort 返回 ended-at")
    void emptySort() {
      assertThat(QueryParams.uiSortKey(Map.of())).isEqualTo("ended-at");
    }

    @Test
    @DisplayName("其他 sort 原样返回")
    void otherSort() {
      assertThat(QueryParams.uiSortKey(Map.of("sort", "tokens"))).isEqualTo("tokens");
    }
  }
}
