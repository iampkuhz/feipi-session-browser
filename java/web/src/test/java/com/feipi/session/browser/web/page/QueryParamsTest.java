package com.feipi.session.browser.web.page;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.query.api.FailureStatus;
import com.feipi.session.browser.query.api.SessionListFilter;
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

  @Nested
  @DisplayName("Sessions agent/status 参数解析")
  class SessionFilterParsing {

    @Test
    @DisplayName("agent=all 等价于不过滤")
    void agentAllMeansUnfiltered() {
      SessionListFilter filter = QueryParams.parseSessionListFilter(Map.of("agent", "all"));

      assertThat(filter.agentFilter().isUnfiltered()).isTrue();
    }

    @Test
    @DisplayName("claude-code URL 别名归一化为 claude_code")
    void claudeCodeAliasNormalizesToUnderscore() {
      SessionListFilter filter = QueryParams.parseSessionListFilter(Map.of("agent", "claude-code"));

      assertThat(filter.agentFilter().agent()).isEqualTo("claude_code");
    }

    @Test
    @DisplayName("status=failed 解析为仅失败会话")
    void failedStatusParsesToFailedOnly() {
      SessionListFilter filter = QueryParams.parseSessionListFilter(Map.of("status", "failed"));

      assertThat(filter.failureStatus()).isEqualTo(FailureStatus.FAILED_ONLY);
    }
  }
}
