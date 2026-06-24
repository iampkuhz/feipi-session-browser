package com.feipi.session.browser.web;

/**
 * Web 服务器不可变配置。
 *
 * <p>封装 HTTP 服务器所需的全部配置参数：监听地址、端口、静态资源路径。 所有校验在构造器完成，下游信任已验证的值。
 *
 * <p>校验放置：端口范围在 HTTP adapter 入口校验一次，下游 Javalin 配置直接使用 int 值。
 *
 * @param host 监听地址，非空
 * @param port 监听端口，0 表示随机端口，范围 [0, 65535]
 * @param staticPath 静态资源 classpath 路径，null 表示不挂载静态资源
 */
public record WebConfig(String host, int port, String staticPath) {

  /** 默认监听地址。 */
  public static final String DEFAULT_HOST = "127.0.0.1";

  /** 默认端口（0 表示随机端口）。 */
  public static final int DEFAULT_PORT = 0;

  /**
   * 紧凑构造器，执行参数校验。
   *
   * @throws IllegalArgumentException host 为空或端口超出范围
   */
  public WebConfig {
    if (host == null || host.isBlank()) {
      throw new IllegalArgumentException("host 不得为空");
    }
    if (port < 0 || port > 65535) {
      throw new IllegalArgumentException("端口超出有效范围: " + port);
    }
  }

  /**
   * 创建默认配置（本地回环地址、随机端口、无静态资源）。
   *
   * @return 默认配置实例
   */
  public static WebConfig defaults() {
    return new WebConfig(DEFAULT_HOST, DEFAULT_PORT, null);
  }

  /**
   * 创建指定端口的配置。
   *
   * @param port 监听端口
   * @return 指定端口的配置实例
   */
  public static WebConfig withPort(int port) {
    return new WebConfig(DEFAULT_HOST, port, null);
  }
}
