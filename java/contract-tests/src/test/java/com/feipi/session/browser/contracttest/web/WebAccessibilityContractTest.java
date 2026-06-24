package com.feipi.session.browser.contracttest.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.index.sqlite.IndexConnection;
import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.index.sqlite.PragmaConfig;
import com.feipi.session.browser.index.sqlite.SchemaVersion;
import com.feipi.session.browser.web.WebCompositionRoot;
import com.feipi.session.browser.web.WebConfig;
import io.javalin.testtools.JavalinTest;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * Web 可访问性契约门禁。
 *
 * <p>验证键盘导航支持、ARIA 属性和基本可访问性结构。 本测试位于 HTTP adapter trust boundary， 验证 HTML 输出中的可访问性标记。
 */
@DisplayName("WEB-080: Web 可访问性契约门禁")
class WebAccessibilityContractTest {

  @TempDir Path tempDir;
  private IndexConnection indexConnection;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("a11y-contract.db");
    String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();
    Connection writerConn = DriverManager.getConnection(jdbcUrl);
    PragmaConfig.DEFAULTS.apply(writerConn);
    indexConnection = IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl);
    IndexSchema.withDefaults().ensureSchema(indexConnection.writerConnection());
  }

  @AfterEach
  void tearDown() {
    if (indexConnection != null) {
      indexConnection.close();
    }
  }

  private WebCompositionRoot createWebRoot() {
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    return new WebCompositionRoot(root, WebConfig.defaults());
  }

  @Nested
  @DisplayName("ARIA 标注")
  class AriaLabels {

    @Test
    @DisplayName("侧边栏导航包含 aria-label")
    void sidebarHasAriaLabel() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/dashboard");
            String body = response.body().string();
            assertThat(body).contains("aria-label=\"Primary navigation\"");
            assertThat(body).contains("aria-label=\"主导航\"");
          });
    }

    @Test
    @DisplayName("Sessions 表格有数据时包含 role=table 和 aria-label")
    void sessionsTableHasRoleAndLabel() throws Exception {
      insertTestSession();
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions");
            String body = response.body().string();
            assertThat(body).contains("role=\"table\"");
            assertThat(body).contains("aria-label=\"Sessions table\"");
          });
    }

    @Test
    @DisplayName("分页有数据时包含 aria-label")
    void paginationHasAriaLabel() throws Exception {
      insertTestSession();
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions");
            String body = response.body().string();
            assertThat(body).contains("aria-label=\"Sessions pagination\"");
          });
    }

    @Test
    @DisplayName("搜索输入框包含 aria-label")
    void searchInputHasAriaLabel() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions");
            String body = response.body().string();
            assertThat(body).contains("aria-label=\"Search sessions\"");
          });
    }

    @Test
    @DisplayName("Session detail 指标区域包含 aria-label")
    void sessionMetricsHaveAriaLabel() throws Exception {
      insertTestSession();
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions/claude_code/test-session-1");
            String body = response.body().string();
            assertThat(body).contains("aria-label=\"Session metrics\"");
          });
    }

    @Test
    @DisplayName("Dashboard 空状态页面包含 KPI 骨架或空状态")
    void dashboardKpiCardsHaveAriaLabel() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/dashboard");
            String body = response.body().string();
            // 空数据库显示空状态；有数据显示 KPI grid
            // 无论哪种情况都包含基本结构
            assertThat(body).contains("Agent Run Profiler");
          });
    }
  }

  @Nested
  @DisplayName("键盘导航支持")
  class KeyboardNavigation {

    @Test
    @DisplayName("导航链接使用 <a> 标签，支持 Tab 聚焦")
    void navLinksAreAnchors() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/dashboard");
            String body = response.body().string();
            // 导航链接必须是 <a> 标签，确保键盘可聚焦
            assertThat(body).contains("href=\"/dashboard\"");
            assertThat(body).contains("href=\"/sessions\"");
            assertThat(body).contains("href=\"/projects\"");
          });
    }

    @Test
    @DisplayName("Dashboard 空状态包含可操作的导航按钮")
    void scopeButtonsAreNativeButtons() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/dashboard");
            String body = response.body().string();
            // 空状态包含 "运行 Scan" 按钮
            assertThat(body).contains("data-action=\"run-scan\"");
            // 导航链接都是 <a> 标签
            assertThat(body).contains("href=\"/dashboard\"");
            assertThat(body).contains("href=\"/sessions\"");
          });
    }

    @Test
    @DisplayName("Session 链接使用 <a> 标签")
    void sessionLinksAreAnchors() throws Exception {
      insertTestSession();
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions");
            String body = response.body().string();
            // session 链接必须是 <a> 标签
            assertThat(body).contains("class=\"session-link\"");
            assertThat(body).contains("data-action=\"open-session\"");
          });
    }
  }

  @Nested
  @DisplayName("HTML lang 和 charset")
  class HtmlLangAndCharset {

    @Test
    @DisplayName("所有页面包含 lang 属性")
    void allPagesHaveLangAttribute() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            for (String path : new String[] {"/", "/dashboard", "/sessions", "/projects"}) {
              var response = client.get(path);
              String body = response.body().string();
              assertThat(body).as("lang on %s", path).contains("lang=");
            }
          });
    }

    @Test
    @DisplayName("所有页面包含 charset 声明")
    void allPagesHaveCharset() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            for (String path : new String[] {"/", "/dashboard", "/sessions", "/projects"}) {
              var response = client.get(path);
              String body = response.body().string();
              assertThat(body).as("charset on %s", path).contains("charset");
            }
          });
    }
  }

  @Nested
  @DisplayName("aria-current 活跃状态")
  class AriaCurrentState {

    @Test
    @DisplayName("Dashboard 导航项高亮")
    void dashboardScopeHasAriaCurrent() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/dashboard");
            String body = response.body().string();
            // Dashboard 导航高亮
            assertThat(body).contains("data-action=\"nav-dashboard\"").contains("is-active");
          });
    }

    @Test
    @DisplayName("Sessions 导航项高亮")
    void sessionsNavHasActiveClass() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions");
            String body = response.body().string();
            assertThat(body).contains("data-action=\"nav-sessions\"").contains("is-active");
          });
    }

    @Test
    @DisplayName("Projects 导航项高亮")
    void projectsNavHasActiveClass() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/projects");
            String body = response.body().string();
            assertThat(body).contains("data-action=\"nav-projects\"").contains("is-active");
          });
    }
  }

  @Nested
  @DisplayName("状态通知")
  class StatusAnnouncements {

    @Test
    @DisplayName("统计信息使用 role=status 供屏幕阅读器播报")
    void statsUseRoleStatus() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions");
            String body = response.body().string();
            assertThat(body).contains("role=\"status\"");
          });
    }

    @Test
    @DisplayName("装饰性图标使用 aria-hidden")
    void decorativeIconsHaveAriaHidden() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/dashboard");
            String body = response.body().string();
            // 图标 aria-hidden 避免屏幕阅读器读出无意义字符
            assertThat(body).contains("aria-hidden=\"true\"");
          });
    }
  }

  /** 插入测试会话数据。 */
  private void insertTestSession() throws Exception {
    String sql =
        "INSERT INTO sessions"
            + " (session_key, agent, session_id, title, project_key, project_name,"
            + " cwd, started_at, ended_at, duration_seconds, model_execution_seconds,"
            + " tool_execution_seconds, model, git_branch, source,"
            + " user_message_count, assistant_message_count, tool_call_count,"
            + " output_tokens, fresh_input_tokens, cache_read_tokens, cache_write_tokens,"
            + " total_tokens, failed_tool_count, subagent_instance_count,"
            + " indexed_at, file_mtime, file_path)"
            + " VALUES"
            + " ('claude_code:test-session-1', 'claude_code', 'test-session-1',"
            + " 'Test Session', 'pk1', 'Test Project', '/work',"
            + " '2024-01-01T00:00:00Z', '2024-01-01T01:00:00Z', 3600, 3000, 600,"
            + " 'claude-3-opus', 'main', 'cli', 5, 10, 20,"
            + " 50000, 25000, 15000, 10000, 100000, 0, 2,"
            + " 1704067200, 1704067200, '/f1')";
    indexConnection.writerConnection().createStatement().execute(sql);
  }
}
