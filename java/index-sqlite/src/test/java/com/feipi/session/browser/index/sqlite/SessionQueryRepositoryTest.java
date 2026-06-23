package com.feipi.session.browser.index.sqlite;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.query.api.AgentFilter;
import com.feipi.session.browser.query.api.FailureStatus;
import com.feipi.session.browser.query.api.ModelFilter;
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
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * {@link SessionQueryRepository} 测试。
 *
 * <p>覆盖会话查询四个方法的正确性、过滤组合、排序、分页、空值和 Unicode 边界。
 */
@DisplayName("SessionQueryRepository 测试")
class SessionQueryRepositoryTest {

  @TempDir Path tempDir;

  private IndexConnection indexConnection;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("test-qa030.db");
    String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();
    Connection writerConn = DriverManager.getConnection(jdbcUrl);
    PragmaConfig.DEFAULTS.apply(writerConn);
    indexConnection = IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl);
    // 初始化 schema
    IndexSchema.withDefaults().ensureSchema(indexConnection.writerConnection());
    // 插入测试数据
    insertTestData();
  }

  private void insertTestData() throws Exception {
    String sql =
        "INSERT INTO sessions"
            + " (session_key, agent, session_id, title, project_key, project_name, cwd,"
            + " started_at, ended_at, duration_seconds, model_execution_seconds,"
            + " tool_execution_seconds, model, git_branch, source,"
            + " user_message_count, assistant_message_count, tool_call_count,"
            + " output_tokens, fresh_input_tokens, cache_read_tokens, cache_write_tokens,"
            + " total_tokens, failed_tool_count, subagent_instance_count,"
            + " indexed_at, file_mtime, file_path)"
            + " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,"
            + " ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)";

    // 测试会话 1：claude_code，有失败工具
    indexConnection
        .writeQueue()
        .submit(
            c -> {
              try (var ps = c.prepareStatement(sql)) {
                ps.setString(1, "claude_code:sess-001");
                ps.setString(2, "claude_code");
                ps.setString(3, "sess-001");
                ps.setString(4, "实现登录功能");
                ps.setString(5, "proj-alpha");
                ps.setString(6, "Alpha 项目");
                ps.setString(7, "/home/user/alpha");
                ps.setString(8, "2024-06-01T10:00:00Z");
                ps.setString(9, "2024-06-01T11:00:00Z");
                ps.setDouble(10, 3600.0);
                ps.setDouble(11, 3000.0);
                ps.setDouble(12, 500.0);
                ps.setString(13, "claude-3-opus");
                ps.setString(14, "main");
                ps.setString(15, "cli");
                ps.setLong(16, 10);
                ps.setLong(17, 20);
                ps.setLong(18, 50);
                ps.setLong(19, 100000);
                ps.setLong(20, 50000);
                ps.setLong(21, 30000);
                ps.setLong(22, 20000);
                ps.setLong(23, 200000);
                ps.setLong(24, 3);
                ps.setLong(25, 2);
                ps.setDouble(26, 1717200000.0);
                ps.setDouble(27, 1717200000.0);
                ps.setString(28, "/path/to/sess-001.json");
                ps.executeUpdate();
              }
            })
        .get();

    // 测试会话 2：codex，无失败
    indexConnection
        .writeQueue()
        .submit(
            c -> {
              try (var ps = c.prepareStatement(sql)) {
                ps.setString(1, "codex:sess-002");
                ps.setString(2, "codex");
                ps.setString(3, "sess-002");
                ps.setString(4, "修复 bug 和优化性能");
                ps.setString(5, "proj-beta");
                ps.setString(6, "Beta 项目");
                ps.setString(7, "/home/user/beta");
                ps.setString(8, "2024-06-02T09:00:00Z");
                ps.setString(9, "2024-06-02T10:00:00Z");
                ps.setDouble(10, 3600.0);
                ps.setDouble(11, 2500.0);
                ps.setDouble(12, 800.0);
                ps.setString(13, "gpt-4");
                ps.setString(14, "develop");
                ps.setString(15, "vscode");
                ps.setLong(16, 5);
                ps.setLong(17, 10);
                ps.setLong(18, 30);
                ps.setLong(19, 80000);
                ps.setLong(20, 40000);
                ps.setLong(21, 20000);
                ps.setLong(22, 10000);
                ps.setLong(23, 150000);
                ps.setLong(24, 0);
                ps.setLong(25, 0);
                ps.setDouble(26, 1717300000.0);
                ps.setDouble(27, 1717300000.0);
                ps.setString(28, "/path/to/sess-002.json");
                ps.executeUpdate();
              }
            })
        .get();

    // 测试会话 3：claude_code，同项目 proj-alpha，无失败
    indexConnection
        .writeQueue()
        .submit(
            c -> {
              try (var ps = c.prepareStatement(sql)) {
                ps.setString(1, "claude_code:sess-003");
                ps.setString(2, "claude_code");
                ps.setString(3, "sess-003");
                ps.setString(4, "Unicode 测试：日本語テスト");
                ps.setString(5, "proj-alpha");
                ps.setString(6, "Alpha 项目");
                ps.setString(7, "/home/user/alpha");
                ps.setString(8, "2024-06-03T08:00:00Z");
                ps.setString(9, "2024-06-03T09:30:00Z");
                ps.setDouble(10, 5400.0);
                ps.setDouble(11, 4000.0);
                ps.setDouble(12, 1200.0);
                ps.setString(13, "claude-3-sonnet");
                ps.setString(14, "main");
                ps.setString(15, "cli");
                ps.setLong(16, 15);
                ps.setLong(17, 30);
                ps.setLong(18, 80);
                ps.setLong(19, 200000);
                ps.setLong(20, 100000);
                ps.setLong(21, 50000);
                ps.setLong(22, 40000);
                ps.setLong(23, 390000);
                ps.setLong(24, 0);
                ps.setLong(25, 1);
                ps.setDouble(26, 1717400000.0);
                ps.setDouble(27, 1717400000.0);
                ps.setString(28, "/path/to/sess-003.json");
                ps.executeUpdate();
              }
            })
        .get();
  }

  @Nested
  @DisplayName("getSession：按主键查找")
  class GetSession {

    @Test
    @DisplayName("存在的 key 返回完整行")
    void existingKeyReturnsRow() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      Optional<SessionRow> result = repo.getSession("claude_code:sess-001");

      assertThat(result).isPresent();
      SessionRow row = result.get();
      assertThat(row.sessionKey()).isEqualTo("claude_code:sess-001");
      assertThat(row.agent()).isEqualTo("claude_code");
      assertThat(row.sessionId()).isEqualTo("sess-001");
      assertThat(row.title()).isEqualTo("实现登录功能");
      assertThat(row.projectKey()).isEqualTo("proj-alpha");
      assertThat(row.model()).isEqualTo("claude-3-opus");
      assertThat(row.totalTokens()).isEqualTo(200000);
      assertThat(row.failedToolCount()).isEqualTo(3);
    }

    @Test
    @DisplayName("不存在的 key 返回 empty")
    void missingKeyReturnsEmpty() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      Optional<SessionRow> result = repo.getSession("nonexistent:key");
      assertThat(result).isEmpty();
    }

    @Test
    @DisplayName("null key 抛 NullPointerException")
    void nullKeyThrows() {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      assertThatThrownBy(() -> repo.getSession(null)).isInstanceOf(NullPointerException.class);
    }
  }

  @Nested
  @DisplayName("listSessions：过滤、排序、分页")
  class ListSessions {

    @Test
    @DisplayName("默认过滤器返回全部会话，按 ended_at DESC 排序")
    void defaultFilterReturnsAll() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      PageResult<SessionRow> result = repo.listSessions(SessionListFilter.defaults());

      assertThat(result.size()).isEqualTo(3);
      assertThat(result.totalCount()).isEqualTo(3);
      // 默认按 ended_at DESC：sess-003 > sess-002 > sess-001
      assertThat(result.items().get(0).sessionKey()).isEqualTo("claude_code:sess-003");
      assertThat(result.items().get(1).sessionKey()).isEqualTo("codex:sess-002");
      assertThat(result.items().get(2).sessionKey()).isEqualTo("claude_code:sess-001");
    }

    @Test
    @DisplayName("agent 过滤器只匹配指定 agent")
    void agentFilter() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter filter = SessionListFilter.defaults().withAgent(AgentFilter.of("codex"));
      PageResult<SessionRow> result = repo.listSessions(filter);

      assertThat(result.size()).isEqualTo(1);
      assertThat(result.totalCount()).isEqualTo(1);
      assertThat(result.items().get(0).agent()).isEqualTo("codex");
    }

    @Test
    @DisplayName("项目过滤器只匹配指定项目")
    void projectFilter() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter filter =
          SessionListFilter.defaults().withProject(ProjectFilter.of("proj-alpha"));
      PageResult<SessionRow> result = repo.listSessions(filter);

      assertThat(result.size()).isEqualTo(2);
      assertThat(result.items()).allMatch(r -> r.projectKey().equals("proj-alpha"));
    }

    @Test
    @DisplayName("模型过滤器只匹配指定模型")
    void modelFilter() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter filter = SessionListFilter.defaults().withModel(ModelFilter.of("gpt-4"));
      PageResult<SessionRow> result = repo.listSessions(filter);

      assertThat(result.size()).isEqualTo(1);
      assertThat(result.items().get(0).model()).isEqualTo("gpt-4");
    }

    @Test
    @DisplayName("标题搜索匹配 title 字段")
    void titleFilterMatchesTitle() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter filter = SessionListFilter.defaults().withTitle(TitleFilter.of("登录"));
      PageResult<SessionRow> result = repo.listSessions(filter);

      assertThat(result.size()).isEqualTo(1);
      assertThat(result.items().get(0).sessionKey()).isEqualTo("claude_code:sess-001");
    }

    @Test
    @DisplayName("标题搜索匹配 session_id 字段")
    void titleFilterMatchesSessionId() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter filter = SessionListFilter.defaults().withTitle(TitleFilter.of("sess-002"));
      PageResult<SessionRow> result = repo.listSessions(filter);

      assertThat(result.size()).isEqualTo(1);
      assertThat(result.items().get(0).sessionKey()).isEqualTo("codex:sess-002");
    }

    @Test
    @DisplayName("Unicode 搜索正常工作")
    void unicodeSearchWorks() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter filter = SessionListFilter.defaults().withTitle(TitleFilter.of("日本語"));
      PageResult<SessionRow> result = repo.listSessions(filter);

      assertThat(result.size()).isEqualTo(1);
      assertThat(result.items().get(0).sessionKey()).isEqualTo("claude_code:sess-003");
    }

    @Test
    @DisplayName("失败状态 FAILED_ONLY 只匹配有失败的会话")
    void failureStatusFailedOnly() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter filter =
          SessionListFilter.defaults().withFailureStatus(FailureStatus.FAILED_ONLY);
      PageResult<SessionRow> result = repo.listSessions(filter);

      assertThat(result.size()).isEqualTo(1);
      assertThat(result.items().get(0).sessionKey()).isEqualTo("claude_code:sess-001");
      assertThat(result.items().get(0).failedToolCount()).isGreaterThan(0);
    }

    @Test
    @DisplayName("失败状态 SUCCESS_ONLY 只匹配无失败的会话")
    void failureStatusSuccessOnly() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter filter =
          SessionListFilter.defaults().withFailureStatus(FailureStatus.SUCCESS_ONLY);
      PageResult<SessionRow> result = repo.listSessions(filter);

      assertThat(result.size()).isEqualTo(2);
      assertThat(result.items()).allMatch(r -> r.failedToolCount() == 0);
    }

    @Test
    @DisplayName("组合过滤器：agent + project")
    void combinedAgentAndProject() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter filter =
          SessionListFilter.defaults()
              .withAgent(AgentFilter.of("claude_code"))
              .withProject(ProjectFilter.of("proj-alpha"));
      PageResult<SessionRow> result = repo.listSessions(filter);

      assertThat(result.size()).isEqualTo(2);
    }

    @Test
    @DisplayName("组合过滤器：agent + project + failure + title")
    void combinedAllFilters() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter filter =
          SessionListFilter.defaults()
              .withAgent(AgentFilter.of("claude_code"))
              .withProject(ProjectFilter.of("proj-alpha"))
              .withFailureStatus(FailureStatus.SUCCESS_ONLY)
              .withTitle(TitleFilter.of("Unicode"));
      PageResult<SessionRow> result = repo.listSessions(filter);

      assertThat(result.size()).isEqualTo(1);
      assertThat(result.items().get(0).sessionKey()).isEqualTo("claude_code:sess-003");
    }

    @Test
    @DisplayName("排序：按 total_tokens ASC")
    void sortByTotalTokensAsc() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter filter =
          SessionListFilter.defaults()
              .withSort(Sort.ofSession(SessionSortField.TOTAL_TOKENS, SortOrder.ASC));
      PageResult<SessionRow> result = repo.listSessions(filter);

      assertThat(result.items().get(0).totalTokens()).isEqualTo(150000);
      assertThat(result.items().get(2).totalTokens()).isEqualTo(390000);
    }

    @Test
    @DisplayName("分页：limit=2 只返回两行")
    void paginationLimit() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter filter = SessionListFilter.defaults().withPage(PageRequest.ofOffset(0, 2));
      PageResult<SessionRow> result = repo.listSessions(filter);

      assertThat(result.size()).isEqualTo(2);
      assertThat(result.totalCount()).isEqualTo(3);
    }

    @Test
    @DisplayName("分页：offset=2 跳过前两行")
    void paginationOffset() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter filter = SessionListFilter.defaults().withPage(PageRequest.ofOffset(2, 50));
      PageResult<SessionRow> result = repo.listSessions(filter);

      assertThat(result.size()).isEqualTo(1);
    }

    @Test
    @DisplayName("分页：offset 超出范围返回空列表")
    void paginationBeyondRange() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter filter =
          SessionListFilter.defaults().withPage(PageRequest.ofOffset(100, 50));
      PageResult<SessionRow> result = repo.listSessions(filter);

      assertThat(result.isEmpty()).isTrue();
      assertThat(result.totalCount()).isEqualTo(3);
    }

    @Test
    @DisplayName("无匹配过滤器返回空列表但总数为 0")
    void noMatchReturnsEmpty() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter filter =
          SessionListFilter.defaults().withAgent(AgentFilter.of("unknown_agent"));
      PageResult<SessionRow> result = repo.listSessions(filter);

      assertThat(result.isEmpty()).isTrue();
      assertThat(result.totalCount()).isEqualTo(0);
    }

    @Test
    @DisplayName("null filter 抛 NullPointerException")
    void nullFilterThrows() {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      assertThatThrownBy(() -> repo.listSessions(null)).isInstanceOf(NullPointerException.class);
    }
  }

  @Nested
  @DisplayName("countSessions：过滤计数")
  class CountSessions {

    @Test
    @DisplayName("默认过滤器返回全部会话数")
    void defaultCount() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      long count = repo.countSessions(SessionListFilter.defaults());
      assertThat(count).isEqualTo(3);
    }

    @Test
    @DisplayName("agent 过滤器计数")
    void agentFilterCount() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter filter = SessionListFilter.defaults().withAgent(AgentFilter.of("codex"));
      assertThat(repo.countSessions(filter)).isEqualTo(1);
    }

    @Test
    @DisplayName("项目过滤器计数")
    void projectFilterCount() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter filter =
          SessionListFilter.defaults().withProject(ProjectFilter.of("proj-alpha"));
      assertThat(repo.countSessions(filter)).isEqualTo(2);
    }

    @Test
    @DisplayName("标题搜索计数：Unicode 关键字")
    void titleSearchCount() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter filter = SessionListFilter.defaults().withTitle(TitleFilter.of("日本語"));
      assertThat(repo.countSessions(filter)).isEqualTo(1);
    }

    @Test
    @DisplayName("失败状态计数")
    void failureStatusCount() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter failedFilter =
          SessionListFilter.defaults().withFailureStatus(FailureStatus.FAILED_ONLY);
      SessionListFilter successFilter =
          SessionListFilter.defaults().withFailureStatus(FailureStatus.SUCCESS_ONLY);
      assertThat(repo.countSessions(failedFilter)).isEqualTo(1);
      assertThat(repo.countSessions(successFilter)).isEqualTo(2);
    }

    @Test
    @DisplayName("无匹配返回 0")
    void noMatchReturnsZero() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter filter =
          SessionListFilter.defaults().withAgent(AgentFilter.of("nonexistent"));
      assertThat(repo.countSessions(filter)).isEqualTo(0);
    }

    @Test
    @DisplayName("组合过滤器计数与 listSessions 一致")
    void combinedCountMatchesList() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter filter =
          SessionListFilter.defaults()
              .withAgent(AgentFilter.of("claude_code"))
              .withFailureStatus(FailureStatus.SUCCESS_ONLY);

      long count = repo.countSessions(filter);
      PageResult<SessionRow> list = repo.listSessions(filter);
      assertThat(count).isEqualTo(list.totalCount());
    }
  }

  @Nested
  @DisplayName("listAggregate：过滤聚合")
  class ListAggregate {

    @Test
    @DisplayName("默认过滤器返回全部聚合")
    void defaultAggregate() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListAggregate agg = repo.listAggregate(SessionListFilter.defaults());

      assertThat(agg.sessionCount()).isEqualTo(3);
      assertThat(agg.projectCount()).isEqualTo(2);
      // 200000 + 150000 + 390000 = 740000
      assertThat(agg.totalTokens()).isEqualTo(740000);
    }

    @Test
    @DisplayName("项目过滤器聚合")
    void projectFilterAggregate() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter filter =
          SessionListFilter.defaults().withProject(ProjectFilter.of("proj-alpha"));
      SessionListAggregate agg = repo.listAggregate(filter);

      assertThat(agg.sessionCount()).isEqualTo(2);
      assertThat(agg.projectCount()).isEqualTo(1);
      // 200000 + 390000 = 590000
      assertThat(agg.totalTokens()).isEqualTo(590000);
    }

    @Test
    @DisplayName("无匹配返回全零")
    void noMatchReturnsZeros() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter filter =
          SessionListFilter.defaults().withAgent(AgentFilter.of("nonexistent"));
      SessionListAggregate agg = repo.listAggregate(filter);

      assertThat(agg.sessionCount()).isEqualTo(0);
      assertThat(agg.projectCount()).isEqualTo(0);
      assertThat(agg.totalTokens()).isEqualTo(0);
    }

    @Test
    @DisplayName("失败状态聚合：只计算有失败的会话")
    void failureStatusAggregate() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(indexConnection);
      SessionListFilter filter =
          SessionListFilter.defaults().withFailureStatus(FailureStatus.FAILED_ONLY);
      SessionListAggregate agg = repo.listAggregate(filter);

      assertThat(agg.sessionCount()).isEqualTo(1);
      assertThat(agg.totalTokens()).isEqualTo(200000);
    }
  }

  @Nested
  @DisplayName("空数据库边界")
  class EmptyDatabase {

    @Test
    @DisplayName("空库查询返回空结果")
    void emptyDbQueries() throws Exception {
      // 使用独立的空数据库
      Path emptyDb = tempDir.resolve("empty.db");
      String jdbcUrl = "jdbc:sqlite:" + emptyDb.toAbsolutePath();
      Connection writerConn = DriverManager.getConnection(jdbcUrl);
      PragmaConfig.DEFAULTS.apply(writerConn);
      try (IndexConnection emptyIc =
          IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl)) {
        IndexSchema.withDefaults().ensureSchema(emptyIc.writerConnection());
        SessionQueryRepository repo = new SessionQueryRepository(emptyIc);

        assertThat(repo.getSession("any:key")).isEmpty();
        assertThat(repo.listSessions(SessionListFilter.defaults()).isEmpty()).isTrue();
        assertThat(repo.countSessions(SessionListFilter.defaults())).isEqualTo(0);
        SessionListAggregate agg = repo.listAggregate(SessionListFilter.defaults());
        assertThat(agg.sessionCount()).isEqualTo(0);
        assertThat(agg.totalTokens()).isEqualTo(0);
      }
    }
  }
}
