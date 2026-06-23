package com.feipi.session.browser.contracttest.query.sessions;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.index.sqlite.IndexConnection;
import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.index.sqlite.PragmaConfig;
import com.feipi.session.browser.index.sqlite.SessionListAggregate;
import com.feipi.session.browser.index.sqlite.SessionQueryRepository;
import com.feipi.session.browser.index.sqlite.SessionRow;
import com.feipi.session.browser.query.api.AgentFilter;
import com.feipi.session.browser.query.api.FailureStatus;
import com.feipi.session.browser.query.api.PageRequest;
import com.feipi.session.browser.query.api.PageResult;
import com.feipi.session.browser.query.api.ProjectFilter;
import com.feipi.session.browser.query.api.SessionListFilter;
import com.feipi.session.browser.query.api.SessionSortField;
import com.feipi.session.browser.query.api.Sort;
import com.feipi.session.browser.query.api.SortOrder;
import com.feipi.session.browser.query.api.TitleFilter;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * 会话查询契约测试。
 *
 * <p>验证 Java session 查询与 Python {@code queries.py} 行为一致： 参数化 SQL、排序白名单、分页语义和空值处理。
 */
@DisplayName("会话查询契约：list / search / count / lookup")
class SessionQueryContractTest {

  @TempDir Path tempDir;
  private IndexConnection ic;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("contract-qa030.db");
    String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();
    Connection writerConn = DriverManager.getConnection(jdbcUrl);
    PragmaConfig.DEFAULTS.apply(writerConn);
    ic = IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl);
    IndexSchema.withDefaults().ensureSchema(ic.writerConnection());
    insertFixtures();
  }

  private void insertFixtures() throws Exception {
    // 使用 writer 连接直接插入 fixture 数据
    try (Statement stmt = ic.writerConnection().createStatement()) {
      stmt.execute(
          "INSERT INTO sessions"
              + " (session_key, agent, session_id, title, project_key, project_name,"
              + " cwd, started_at, ended_at, duration_seconds, model_execution_seconds,"
              + " tool_execution_seconds, model, git_branch, source,"
              + " user_message_count, assistant_message_count, tool_call_count,"
              + " output_tokens, fresh_input_tokens, cache_read_tokens, cache_write_tokens,"
              + " total_tokens, failed_tool_count, subagent_instance_count,"
              + " indexed_at, file_mtime, file_path)"
              + " VALUES"
              + " ('cc:s1', 'claude_code', 's1', '会话 Alpha', 'pk1', '项目一', '/a',"
              + " '2024-01-01T00:00:00Z', '2024-01-01T01:00:00Z', 3600, 3000, 600,"
              + " 'claude-3-opus', 'main', 'cli', 5, 10, 20,"
              + " 50000, 25000, 15000, 10000, 100000, 0, 0,"
              + " 1704067200, 1704067200, '/f1'),"
              + " ('cc:s2', 'claude_code', 's2', '会话 Beta', 'pk1', '项目一', '/a',"
              + " '2024-01-02T00:00:00Z', '2024-01-02T02:00:00Z', 7200, 5000, 2000,"
              + " 'claude-3-sonnet', 'main', 'cli', 10, 20, 40,"
              + " 100000, 50000, 30000, 20000, 200000, 5, 1,"
              + " 1704153600, 1704153600, '/f2'),"
              + " ('cx:s3', 'codex', 's3', '会话 Gamma', 'pk2', '项目二', '/b',"
              + " '2024-01-03T00:00:00Z', '2024-01-03T03:00:00Z', 10800, 8000, 3000,"
              + " 'gpt-4', 'dev', 'vscode', 15, 30, 60,"
              + " 150000, 75000, 45000, 30000, 300000, 0, 0,"
              + " 1704240000, 1704240000, '/f3')");
    }
  }

  @Nested
  @DisplayName("Lookup：按主键查找")
  class Lookup {

    @Test
    @DisplayName("存在的 key 返回完整行，所有列正确映射")
    void lookupMapsAllColumns() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);
      var row = repo.getSession("cc:s1").orElseThrow();

      assertThat(row.sessionKey()).isEqualTo("cc:s1");
      assertThat(row.agent()).isEqualTo("claude_code");
      assertThat(row.sessionId()).isEqualTo("s1");
      assertThat(row.title()).isEqualTo("会话 Alpha");
      assertThat(row.projectKey()).isEqualTo("pk1");
      assertThat(row.projectName()).isEqualTo("项目一");
      assertThat(row.cwd()).isEqualTo("/a");
      assertThat(row.startedAt()).isEqualTo("2024-01-01T00:00:00Z");
      assertThat(row.endedAt()).isEqualTo("2024-01-01T01:00:00Z");
      assertThat(row.durationSeconds()).isEqualTo(3600.0);
      assertThat(row.modelExecutionSeconds()).isEqualTo(3000.0);
      assertThat(row.toolExecutionSeconds()).isEqualTo(600.0);
      assertThat(row.model()).isEqualTo("claude-3-opus");
      assertThat(row.gitBranch()).isEqualTo("main");
      assertThat(row.source()).isEqualTo("cli");
      assertThat(row.userMessageCount()).isEqualTo(5);
      assertThat(row.assistantMessageCount()).isEqualTo(10);
      assertThat(row.toolCallCount()).isEqualTo(20);
      assertThat(row.outputTokens()).isEqualTo(50000);
      assertThat(row.freshInputTokens()).isEqualTo(25000);
      assertThat(row.cacheReadTokens()).isEqualTo(15000);
      assertThat(row.cacheWriteTokens()).isEqualTo(10000);
      assertThat(row.totalTokens()).isEqualTo(100000);
      assertThat(row.failedToolCount()).isEqualTo(0);
      assertThat(row.subagentInstanceCount()).isEqualTo(0);
    }

    @Test
    @DisplayName("不存在的 key 返回 empty")
    void lookupMissing() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);
      assertThat(repo.getSession("nonexistent")).isEmpty();
    }
  }

  @Nested
  @DisplayName("List：过滤与排序契约")
  class ListContract {

    @Test
    @DisplayName("无过滤器返回全部行，默认 ended_at DESC")
    void noFilterDefaultSort() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);
      PageResult<SessionRow> result = repo.listSessions(SessionListFilter.defaults());

      assertThat(result.size()).isEqualTo(3);
      assertThat(result.totalCount()).isEqualTo(3);
      assertThat(result.items().get(0).sessionKey()).isEqualTo("cx:s3");
      assertThat(result.items().get(2).sessionKey()).isEqualTo("cc:s1");
    }

    @Test
    @DisplayName("排序白名单生效：total_tokens ASC")
    void sortAllowlist() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);
      SessionListFilter filter =
          SessionListFilter.defaults()
              .withSort(Sort.ofSession(SessionSortField.TOTAL_TOKENS, SortOrder.ASC));
      PageResult<SessionRow> result = repo.listSessions(filter);

      assertThat(result.items().get(0).totalTokens()).isEqualTo(100000);
      assertThat(result.items().get(2).totalTokens()).isEqualTo(300000);
    }

    @Test
    @DisplayName("标题搜索同时匹配 title 和 session_id")
    void titleSearchAcrossColumns() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);

      // 搜索 title
      var byTitle =
          repo.listSessions(SessionListFilter.defaults().withTitle(TitleFilter.of("Alpha")));
      assertThat(byTitle.size()).isEqualTo(1);
      assertThat(byTitle.items().get(0).title()).isEqualTo("会话 Alpha");

      // 搜索 session_id
      var bySessionId =
          repo.listSessions(SessionListFilter.defaults().withTitle(TitleFilter.of("s2")));
      assertThat(bySessionId.size()).isEqualTo(1);
      assertThat(bySessionId.items().get(0).sessionKey()).isEqualTo("cc:s2");
    }

    @Test
    @DisplayName("搜索不区分大小写")
    void caseInsensitiveSearch() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);
      var result =
          repo.listSessions(SessionListFilter.defaults().withTitle(TitleFilter.of("alpha")));
      assertThat(result.size()).isEqualTo(1);
    }
  }

  @Nested
  @DisplayName("Pagination：分页契约")
  class PaginationContract {

    @Test
    @DisplayName("limit 限制返回行数，totalCount 反映过滤后总数")
    void limitWithTotalCount() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);
      SessionListFilter filter = SessionListFilter.defaults().withPage(PageRequest.ofOffset(0, 2));
      PageResult<SessionRow> result = repo.listSessions(filter);

      assertThat(result.size()).isEqualTo(2);
      assertThat(result.totalCount()).isEqualTo(3);
    }

    @Test
    @DisplayName("offset 跳过行，保持排序一致性")
    void offsetSkipConsistent() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);
      PageResult<SessionRow> page1 =
          repo.listSessions(SessionListFilter.defaults().withPage(PageRequest.ofOffset(0, 2)));
      PageResult<SessionRow> page2 =
          repo.listSessions(SessionListFilter.defaults().withPage(PageRequest.ofOffset(2, 2)));

      // 两页之间不应有重复
      List<String> keys1 = page1.items().stream().map(SessionRow::sessionKey).toList();
      List<String> keys2 = page2.items().stream().map(SessionRow::sessionKey).toList();
      assertThat(keys1).doesNotContainAnyElementsOf(keys2);
      assertThat(page1.size() + page2.size()).isEqualTo(3);
    }

    @Test
    @DisplayName("offset 超出范围返回空列表")
    void offsetBeyondRange() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);
      PageResult<SessionRow> result =
          repo.listSessions(SessionListFilter.defaults().withPage(PageRequest.ofOffset(100, 50)));
      assertThat(result.isEmpty()).isTrue();
      assertThat(result.totalCount()).isEqualTo(3);
    }
  }

  @Nested
  @DisplayName("Count：计数契约")
  class CountContract {

    @Test
    @DisplayName("计数与 list 总数一致")
    void countMatchesListTotal() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);

      SessionListFilter[] filters = {
        SessionListFilter.defaults(),
        SessionListFilter.defaults().withAgent(AgentFilter.of("claude_code")),
        SessionListFilter.defaults().withProject(ProjectFilter.of("pk2")),
        SessionListFilter.defaults().withFailureStatus(FailureStatus.FAILED_ONLY),
        SessionListFilter.defaults().withTitle(TitleFilter.of("会话")),
      };

      for (SessionListFilter filter : filters) {
        long count = repo.countSessions(filter);
        PageResult<SessionRow> list = repo.listSessions(filter);
        assertThat(count).as("过滤器 %s 的计数应与 list 总数一致", filter).isEqualTo(list.totalCount());
      }
    }
  }

  @Nested
  @DisplayName("Aggregate：聚合契约")
  class AggregateContract {

    @Test
    @DisplayName("全量聚合：会话数、项目数和 token 总量")
    void fullAggregate() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);
      SessionListAggregate agg = repo.listAggregate(SessionListFilter.defaults());

      assertThat(agg.sessionCount()).isEqualTo(3);
      assertThat(agg.projectCount()).isEqualTo(2);
      assertThat(agg.totalTokens()).isEqualTo(600000);
    }

    @Test
    @DisplayName("过滤后聚合与全量一致")
    void filteredAggregateConsistent() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);
      SessionListFilter filter =
          SessionListFilter.defaults().withAgent(AgentFilter.of("claude_code"));
      SessionListAggregate agg = repo.listAggregate(filter);

      assertThat(agg.sessionCount()).isEqualTo(2);
      assertThat(agg.projectCount()).isEqualTo(1);
      assertThat(agg.totalTokens()).isEqualTo(300000);
    }

    @Test
    @DisplayName("聚合计数与 countSessions 一致")
    void aggregateCountConsistent() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);
      SessionListFilter filter =
          SessionListFilter.defaults().withFailureStatus(FailureStatus.SUCCESS_ONLY);

      long count = repo.countSessions(filter);
      SessionListAggregate agg = repo.listAggregate(filter);
      assertThat(agg.sessionCount()).isEqualTo(count);
    }
  }

  @Nested
  @DisplayName("只读保证")
  class ReadOnlyGuarantee {

    @Test
    @DisplayName("查询方法不修改数据库")
    void queriesAreReadOnly() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);

      // 执行所有查询
      repo.getSession("cc:s1");
      repo.listSessions(SessionListFilter.defaults());
      repo.countSessions(SessionListFilter.defaults());
      repo.listAggregate(SessionListFilter.defaults());

      // 验证数据未被修改：仍为 3 行
      try (var stmt = ic.writerConnection().createStatement();
          var rs = stmt.executeQuery("SELECT COUNT(*) FROM sessions")) {
        rs.next();
        assertThat(rs.getLong(1)).isEqualTo(3);
      }
    }
  }
}
