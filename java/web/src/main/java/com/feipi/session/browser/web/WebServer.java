package com.feipi.session.browser.web;

import io.javalin.Javalin;
import io.javalin.http.Context;
import java.util.Objects;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Javalin Web 服务器生命周期管理。
 *
 * <p>封装 Javalin 实例的创建、启动和停止。不引入 DI framework 或运行时反射， 所有路由和 handler 通过显式注册。
 *
 * <p>服务器支持随机端口（配置 port=0），适用于测试和动态端口分配场景。
 */
public final class WebServer {

  private static final Logger LOG = LoggerFactory.getLogger(WebServer.class);

  private final Javalin app;
  private final WebConfig config;
  private volatile boolean running;

  /**
   * 创建 Web 服务器实例。
   *
   * @param app 已配置路由的 Javalin 实例
   * @param config 服务器配置
   */
  public WebServer(Javalin app, WebConfig config) {
    this.app = Objects.requireNonNull(app, "app 不得为 null");
    this.config = Objects.requireNonNull(config, "config 不得为 null");
    this.running = false;
  }

  /**
   * 启动服务器并阻塞等待就绪。
   *
   * <p>启动完成后日志输出实际监听端口（随机端口时有意义）。
   *
   * @return 当前实例，支持链式调用
   */
  public WebServer start() {
    app.start(config.host(), config.port());
    running = true;
    LOG.info("Web 服务器已启动: {}:{}", config.host(), actualPort());
    return this;
  }

  /**
   * 停止服务器。
   *
   * <p>幂等操作，重复调用无副作用。
   */
  public void stop() {
    if (!running) {
      return;
    }
    app.stop();
    running = false;
    LOG.info("Web 服务器已停止");
  }

  /**
   * 返回服务器实际监听端口。
   *
   * <p>配置为随机端口时返回操作系统分配的端口；未启动时返回 -1。
   *
   * @return 实际监听端口，未启动时返回 -1
   */
  public int actualPort() {
    if (!running) {
      return -1;
    }
    return app.port();
  }

  /**
   * 返回服务器是否正在运行。
   *
   * @return 运行中时返回 true
   */
  public boolean isRunning() {
    return running;
  }

  /**
   * 返回底层 Javalin 实例。
   *
   * <p>供测试或高级配置使用，生产代码应避免直接访问。
   *
   * @return Javalin 实例
   */
  public Javalin javalin() {
    return app;
  }

  /**
   * 注册健康检查路由。
   *
   * <p>GET /healthz 返回 200 和 JSON 状态，用于服务器 smoke 验证和进程存活检测。
   *
   * @param ctx Javalin 上下文
   */
  static void healthHandler(Context ctx) {
    ctx.json(new HealthResponse("ok"));
  }

  /** 健康检查 JSON 响应载体。 */
  record HealthResponse(String status) {}
}
