package com.feipi.session.browser.query.api;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/** 复合过滤器契约测试。 */
class CompositeFilterTest {

  @Nested
  class SessionListFilterTests {

    @Test
    void defaultsNoFiltersApplied() {
      SessionListFilter f = SessionListFilter.defaults();
      assertThat(f.agentFilter().isUnfiltered()).isTrue();
      assertThat(f.projectFilter().isUnfiltered()).isTrue();
      assertThat(f.modelFilter().isUnfiltered()).isTrue();
      assertThat(f.titleFilter().isUnfiltered()).isTrue();
      assertThat(f.failureStatus()).isEqualTo(FailureStatus.ALL);
      assertThat(f.sort()).isEqualTo(Sort.DEFAULT_SESSION);
      assertThat(f.page()).isEqualTo(PageRequest.DEFAULT);
    }

    @Test
    void withAgentReplacesAgentFilter() {
      SessionListFilter f = SessionListFilter.defaults().withAgent(AgentFilter.of("claude_code"));
      assertThat(f.agentFilter().agent()).isEqualTo("claude_code");
      assertThat(f.projectFilter().isUnfiltered()).isTrue();
    }

    @Test
    void withProjectReplacesProjectFilter() {
      SessionListFilter f =
          SessionListFilter.defaults().withProject(ProjectFilter.of("my-project"));
      assertThat(f.projectFilter().projectKey()).isEqualTo("my-project");
    }

    @Test
    void withModelReplacesModelFilter() {
      SessionListFilter f = SessionListFilter.defaults().withModel(ModelFilter.of("claude-3"));
      assertThat(f.modelFilter().model()).isEqualTo("claude-3");
    }

    @Test
    void withTitleReplacesTitleFilter() {
      SessionListFilter f = SessionListFilter.defaults().withTitle(TitleFilter.of("search-term"));
      assertThat(f.titleFilter().keyword()).isEqualTo("search-term");
    }

    @Test
    void withFailureStatusReplacesStatus() {
      SessionListFilter f =
          SessionListFilter.defaults().withFailureStatus(FailureStatus.FAILED_ONLY);
      assertThat(f.failureStatus()).isEqualTo(FailureStatus.FAILED_ONLY);
    }

    @Test
    void withSortReplacesSort() {
      Sort newSort = Sort.ofSession(SessionSortField.TOTAL_TOKENS, SortOrder.DESC);
      SessionListFilter f = SessionListFilter.defaults().withSort(newSort);
      assertThat(f.sort()).isEqualTo(newSort);
    }

    @Test
    void withPageReplacesPage() {
      PageRequest newPage = PageRequest.ofOffset(100, 25);
      SessionListFilter f = SessionListFilter.defaults().withPage(newPage);
      assertThat(f.page()).isEqualTo(newPage);
    }

    @Test
    void chainingMultipleFilters() {
      SessionListFilter f =
          SessionListFilter.defaults()
              .withAgent(AgentFilter.of("claude_code"))
              .withProject(ProjectFilter.of("my-project"))
              .withSort(Sort.ofSession(SessionSortField.TOTAL_TOKENS, SortOrder.DESC))
              .withPage(PageRequest.ofOffset(10, 20));

      assertThat(f.agentFilter().agent()).isEqualTo("claude_code");
      assertThat(f.projectFilter().projectKey()).isEqualTo("my-project");
      assertThat(f.sort().sortKey()).isEqualTo("total_tokens");
      assertThat(f.page().offset()).isEqualTo(10);
      assertThat(f.page().limit()).isEqualTo(20);
    }

    @Test
    void immutabilityOriginalUnchanged() {
      SessionListFilter original = SessionListFilter.defaults();
      SessionListFilter modified = original.withAgent(AgentFilter.of("codex"));
      assertThat(original.agentFilter().isUnfiltered()).isTrue();
      assertThat(modified.agentFilter().agent()).isEqualTo("codex");
    }
  }

  @Nested
  class ProjectListFilterTests {

    @Test
    void defaultsNoFiltersApplied() {
      ProjectListFilter f = ProjectListFilter.defaults();
      assertThat(f.titleFilter().isUnfiltered()).isTrue();
      assertThat(f.sort()).isEqualTo(Sort.DEFAULT_PROJECT);
      assertThat(f.page()).isEqualTo(PageRequest.DEFAULT);
    }

    @Test
    void withTitleReplacesTitleFilter() {
      ProjectListFilter f = ProjectListFilter.defaults().withTitle(TitleFilter.of("search"));
      assertThat(f.titleFilter().keyword()).isEqualTo("search");
    }

    @Test
    void withSortReplacesSort() {
      Sort newSort = Sort.ofProject(ProjectSortField.TOTAL_SESSIONS, SortOrder.ASC);
      ProjectListFilter f = ProjectListFilter.defaults().withSort(newSort);
      assertThat(f.sort()).isEqualTo(newSort);
    }

    @Test
    void withPageReplacesPage() {
      PageRequest newPage = PageRequest.ofOffset(50, 10);
      ProjectListFilter f = ProjectListFilter.defaults().withPage(newPage);
      assertThat(f.page()).isEqualTo(newPage);
    }
  }

  @Nested
  class DashboardFilterTests {

    @Test
    void defaultsNoFiltersApplied() {
      DashboardFilter f = DashboardFilter.defaults();
      assertThat(f.agentFilter().isUnfiltered()).isTrue();
      assertThat(f.page()).isEqualTo(PageRequest.DEFAULT);
    }

    @Test
    void withAgentReplacesAgentFilter() {
      DashboardFilter f = DashboardFilter.defaults().withAgent(AgentFilter.of("qoder"));
      assertThat(f.agentFilter().agent()).isEqualTo("qoder");
    }

    @Test
    void withPageReplacesPage() {
      PageRequest newPage = PageRequest.ofLimit(100);
      DashboardFilter f = DashboardFilter.defaults().withPage(newPage);
      assertThat(f.page()).isEqualTo(newPage);
    }
  }
}
