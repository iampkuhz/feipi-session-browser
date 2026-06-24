package com.feipi.session.browser.cli;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;
import java.util.concurrent.Callable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;

/**
 * serve 子命令实现。
 *
 * <p>把 Java scan/query/web 组合为前台 server，支持 startup/background scan 和 graceful shutdown。 启动顺序：config
 * → schema/query → optional scan → bind server → background scheduler。
 *
 * <p>退出码：
 *
 * <ul>
 *   <li>0 — 正常关闭
 *   <li>1 — 启动或运行失败
 * </ul>
 *
 * <p>校验放置：host/port 在 {@link com.feipi.session.browser.web.WebConfig} 紧凑构造器校验一次； 源目录存在性在 {@link
 * ServerLifecycle} 边界检查一次；CLI 参数由 Picocli 解析为 typed 选项后不再重复校验。
 */
@Command(
    name = "serve",
    mixinStandardHelpOptions = true,
    description = "启动本地 Web 服务",
    sortOptions = false)
final class ServeCommand implements Callable<Integer> {

  private static final Logger LOG = LoggerFactory.getLogger(ServeCommand.class);

  /** 默认监听地址。 */
  private static final String DEFAULT_HOST = "127.0.0.1";

  /** 默认端口。 */
  private static final int DEFAULT_PORT = 8848;

  /** 默认索引目录环境变量名。 */
  private static final String INDEX_DIR_ENV = "INDEX_DIR";

  /** 默认本地测试索引路径。 */
  private static final Path DEFAULT_INDEX_DIR =
      Path.of(
          System.getProperty("user.home"), ".local/share/feipi/session-browser/local-test-index");

  @Option(
      names = {"--host"},
      description = "监听地址（默认 ${DEFAULT-VALUE}）",
      defaultValue = DEFAULT_HOST)
  private String host;

  @Option(
      names = {"--port", "-p"},
      description = "监听端口（默认 ${DEFAULT-VALUE}，0 表示随机端口）",
      defaultValue = "" + DEFAULT_PORT)
  private int port;

  @Option(
      names = {"--allow-empty"},
      description = "允许无源目录时启动")
  private boolean allowEmpty;

  @Option(
      names = {"--no-scan"},
      description = "禁用启动扫描和后台扫描")
  private boolean noScan;

  @Override
  public Integer call() {
    Path indexDir = resolveIndexDir();

    try {
      Files.createDirectories(indexDir);
    } catch (Exception e) {
      System.err.println("错误：无法创建索引目录: " + indexDir + " (" + e.getMessage() + ")");
      return 1;
    }

    ServerLifecycle lifecycle =
        new ServerLifecycle(indexDir, host, port, noScan, allowEmpty, Set.of());

    try {
      int actualPort = lifecycle.start();
      LOG.info("serve 已就绪: http://{}:{}", host, actualPort);
      System.out.println("serve 已就绪: http://" + host + ":" + actualPort);
      lifecycle.awaitShutdown();
      return 0;
    } catch (java.net.BindException e) {
      System.err.println("错误：端口 " + port + " 已被占用");
      System.err.println("  " + e.getMessage());
      System.err.println("  请使用 --port 指定其他端口");
      return 1;
    } catch (Exception e) {
      String msg = e.getMessage();
      // 检测端口冲突的包装异常
      if (msg != null
          && (msg.contains("Failed to bind") || msg.contains("Address already in use"))) {
        System.err.println("错误：端口 " + port + " 已被占用");
        System.err.println("  请使用 --port 指定其他端口");
      } else {
        System.err.println("错误：serve 启动失败: " + msg);
      }
      LOG.debug("serve 启动失败", e);
      return 1;
    }
  }

  /** 解析索引目录。 */
  private static Path resolveIndexDir() {
    String envValue = System.getenv(INDEX_DIR_ENV);
    if (envValue != null && !envValue.isBlank()) {
      return Path.of(PathUtils.expandTilde(envValue));
    }
    return DEFAULT_INDEX_DIR;
  }
}
