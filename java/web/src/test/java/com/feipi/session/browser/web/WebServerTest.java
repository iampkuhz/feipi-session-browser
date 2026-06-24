package com.feipi.session.browser.web;

import static org.assertj.core.api.Assertions.assertThat;

import io.javalin.Javalin;
import io.javalin.testtools.JavalinTest;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * {@link WebServer} 单元测试。
 *
 * <p>验证服务器启动、停止、随机端口分配和健康检查路由。
 */
@DisplayName("WebServer 生命周期测试")
class WebServerTest {

  @Test
  @DisplayName("启动后状态为运行中")
  void startSetsRunningState() {
    Javalin app = Javalin.create();
    WebServer server = new WebServer(app, WebConfig.defaults());

    try {
      server.start();
      assertThat(server.isRunning()).isTrue();
    } finally {
      server.stop();
    }
  }

  @Test
  @DisplayName("停止后状态为非运行")
  void stopClearsRunningState() {
    Javalin app = Javalin.create();
    WebServer server = new WebServer(app, WebConfig.defaults());

    server.start();
    server.stop();

    assertThat(server.isRunning()).isFalse();
  }

  @Test
  @DisplayName("随机端口启动后返回实际端口")
  void randomPortReturnsActualPort() {
    Javalin app = Javalin.create();
    WebServer server = new WebServer(app, WebConfig.defaults());

    try {
      server.start();
      int port = server.actualPort();
      assertThat(port).isGreaterThan(0);
      assertThat(port).isLessThanOrEqualTo(65535);
    } finally {
      server.stop();
    }
  }

  @Test
  @DisplayName("未启动时返回端口 -1")
  void notStartedReturnsNegativePort() {
    Javalin app = Javalin.create();
    WebServer server = new WebServer(app, WebConfig.defaults());

    assertThat(server.actualPort()).isEqualTo(-1);
  }

  @Test
  @DisplayName("重复停止幂等")
  void doubleStopIsIdempotent() {
    Javalin app = Javalin.create();
    WebServer server = new WebServer(app, WebConfig.defaults());

    server.start();
    server.stop();
    server.stop();

    assertThat(server.isRunning()).isFalse();
  }

  @Test
  @DisplayName("健康检查路由返回 200 和 ok 状态")
  void healthEndpointReturnsOk() {
    Javalin app =
        Javalin.create(
            config -> {
              config.routes.get("/healthz", WebServer::healthHandler);
            });

    JavalinTest.test(
        app,
        (testApp, client) -> {
          var response = client.get("/healthz");
          assertThat(response.code()).isEqualTo(200);
          assertThat(response.body().string()).contains("ok");
        });
  }

  @Test
  @DisplayName("start 返回当前实例支持链式调用")
  void startReturnsSelf() {
    Javalin app = Javalin.create();
    WebServer server = new WebServer(app, WebConfig.defaults());

    try {
      WebServer result = server.start();
      assertThat(result).isSameAs(server);
    } finally {
      server.stop();
    }
  }
}
