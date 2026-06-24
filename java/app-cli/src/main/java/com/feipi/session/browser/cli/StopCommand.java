package com.feipi.session.browser.cli;

import java.io.IOException;
import java.net.ConnectException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Optional;
import java.util.concurrent.Callable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;

/**
 * stop 子命令实现：安全终止运行中的 serve 进程。
 *
 * <p>终止策略：
 *
 * <ol>
 *   <li>优先读取 PID 文件（{@code {indexDir}/server.pid}），获取 PID、端口、主机等元数据
 *   <li>验证 PID 存活（{@link ProcessHandle#of}）
 *   <li>通过 health endpoint（{@code /healthz}）验证 PID 归属 session-browser
 *   <li>发送 TERM 信号（{@link ProcessHandle#destroy}），等待最多 10 秒
 *   <li>超时后发送 KILL 信号（{@link ProcessHandle#destroyForcibly}）
 *   <li>清理 PID 文件
 * </ol>
 *
 * <p>跨平台兼容：使用 {@link ProcessHandle} API，不依赖 {@code lsof}、{@code /proc} 等 Unix 特定路径。 Windows 下
 * {@code destroy()} 调用 TerminateProcess，行为等同 force kill。
 *
 * <p>退出码：
 *
 * <ul>
 *   <li>0 — 进程已停止或已经不在运行
 *   <li>1 — 停止失败或无法识别进程
 * </ul>
 *
 * <p>校验放置：PID 文件解析在 {@link PidFile#read} 边界执行一次；进程存活性和归属验证在本类执行一次； 信号发送和等待在 JVM OS 层完成，不再重复校验。
 */
@Command(
    name = "stop",
    mixinStandardHelpOptions = true,
    description = "停止本地服务进程",
    sortOptions = false)
final class StopCommand implements Callable<Integer> {

  private static final Logger LOG = LoggerFactory.getLogger(StopCommand.class);

  /** 默认端口，与 serve 命令一致。 */
  private static final int DEFAULT_PORT = 8848;

  /** TERM 信号后的最大等待时间（秒）。 */
  private static final int GRACEFUL_TIMEOUT_SECONDS = 10;

  /** health endpoint 验证超时（毫秒）。 */
  private static final int HEALTH_TIMEOUT_MS = 2000;

  /** 默认索引目录环境变量名。 */
  private static final String INDEX_DIR_ENV = "INDEX_DIR";

  @Option(
      names = {"--port", "-p"},
      description = "服务端口（默认 ${DEFAULT-VALUE}），用于辅助验证",
      defaultValue = "" + DEFAULT_PORT)
  private int port;

  @Option(
      names = {"--index-dir"},
      description = "索引目录（默认与 serve 相同）")
  private String indexDirOption;

  @Option(
      names = {"--force", "-f"},
      description = "跳过进程归属验证，强制终止")
  private boolean force;

  @Override
  public Integer call() {
    Path indexDir = resolveIndexDir();

    try {
      return executeStop(indexDir);
    } catch (IOException e) {
      System.err.println("错误：" + e.getMessage());
      return 1;
    }
  }

  /**
   * 执行 stop 流程。
   *
   * @param indexDir 索引目录
   * @return 退出码
   * @throws IOException 当 PID 文件读取失败或进程归属验证失败时
   */
  private int executeStop(Path indexDir) throws IOException {
    // 阶段 1：读取 PID 文件
    PidFile.Metadata meta = PidFile.read(indexDir);

    if (meta == null) {
      return handleMissingPidFile(indexDir);
    }

    long pid = meta.pid();

    // 阶段 2：验证 PID 存活
    Optional<ProcessHandle> processOpt = ProcessHandle.of(pid);
    if (processOpt.isEmpty() || !processOpt.get().isAlive()) {
      PidFile.delete(indexDir);
      System.out.println("PID " + pid + " 对应的进程已不在运行（stale PID 文件已清理）");
      return 0;
    }

    ProcessHandle process = processOpt.get();

    // 阶段 3：验证进程归属（通过 health endpoint）
    if (!force) {
      boolean identityOk = verifyIdentity(meta, pid);
      if (!identityOk) {
        return 1;
      }
    }

    // 阶段 4：终止进程（TERM → bounded wait → KILL）
    terminateProcess(process, pid);

    // 阶段 5：清理 PID 文件
    PidFile.delete(indexDir);

    System.out.println("serve 进程已停止 (PID " + pid + ")");
    return 0;
  }

  /**
   * 处理 PID 文件缺失的情况。
   *
   * <p>检查端口是否仍有进程监听，提供诊断信息帮助用户手动处理。
   *
   * @param indexDir 索引目录
   * @return 退出码
   * @throws IOException 当端口检查失败时
   */
  private int handleMissingPidFile(Path indexDir) throws IOException {
    if (isPortListening(port)) {
      System.err.println("端口 " + port + " 有进程在监听，但未找到 PID 文件。");
      System.err.println("  可能 serve 使用了其他索引目录，请使用 --index-dir 指定正确的索引目录。");
      return 1;
    }
    System.out.println("serve 未在运行（未找到 PID 文件且端口 " + port + " 无监听）");
    return 0;
  }

  /**
   * 验证 PID 归属 session-browser。
   *
   * <p>通过 health endpoint（{@code /healthz}）确认目标端口由 session-browser 响应。 如果端口无效（&lt;=0）或不可达，根据 force
   * 标志决定是否继续。
   *
   * @param meta PID 文件元数据
   * @param pid 进程 ID
   * @return 验证是否通过
   * @throws IOException 当端口被非 session-browser 进程占用时
   */
  private boolean verifyIdentity(PidFile.Metadata meta, long pid) throws IOException {
    if (meta.port() > 0) {
      String healthUrl = "http://" + meta.host() + ":" + meta.port() + "/healthz";
      try {
        if (checkHealthEndpoint(healthUrl)) {
          return true;
        }
        // Health endpoint 未返回 ok
        if (isPortListening(meta.port())) {
          throw new IOException(
              "端口 "
                  + meta.port()
                  + " 的响应不是 session-browser，拒绝终止 PID "
                  + pid
                  + "（可能 PID 已被复用）。使用 --force 强制终止");
        }
        // 端口未监听，可能是 stale
        System.err.println("警告：PID " + pid + " 存活但端口 " + meta.port() + " 不可达，可能正在关闭中");
        return true;
      } catch (IOException e) {
        throw e;
      } catch (Exception e) {
        System.err.println("警告：无法验证进程归属: " + e.getMessage());
        // 无法验证时，如果端口仍被占用则拒绝终止
        if (isPortListening(meta.port())) {
          throw new IOException("无法确认 PID " + pid + " 属于 session-browser，拒绝终止。使用 --force 强制终止", e);
        }
        return true;
      }
    }
    // port <= 0 时跳过端口验证，信任 PID 文件
    return true;
  }

  /**
   * 终止进程：TERM → bounded wait → KILL。
   *
   * <p>先发送 TERM 信号（{@link ProcessHandle#destroy}），等待最多 {@value #GRACEFUL_TIMEOUT_SECONDS} 秒。
   * 若超时进程仍存活，发送 KILL 信号（{@link ProcessHandle#destroyForcibly}）。
   *
   * @param process 目标进程句柄
   * @param pid 进程 ID，仅用于日志输出
   */
  private static void terminateProcess(ProcessHandle process, long pid) {
    System.out.println("正在停止进程 " + pid + "（发送 TERM 信号）...");
    try {
      process.destroy();
    } catch (IllegalStateException e) {
      // 当前进程不允许通过 ProcessHandle.destroy() 终止自身（Java 安全限制）
      System.err.println("错误：无法终止当前进程自身 (PID " + pid + ")，请从其他进程执行 stop");
      return;
    }

    long deadline = System.currentTimeMillis() + (GRACEFUL_TIMEOUT_SECONDS * 1000L);
    while (process.isAlive() && System.currentTimeMillis() < deadline) {
      try {
        Thread.sleep(500);
      } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        break;
      }
    }

    if (process.isAlive()) {
      System.err.println("进程 " + pid + " 未在 " + GRACEFUL_TIMEOUT_SECONDS + " 秒内退出，发送 KILL 信号");
      try {
        process.destroyForcibly();
      } catch (IllegalStateException e) {
        System.err.println("错误：无法强制终止当前进程自身 (PID " + pid + ")");
        return;
      }
      // 等待强制终止完成
      try {
        process.onExit().get();
      } catch (Exception e) {
        LOG.debug("等待强制终止完成时出现异常", e);
      }
    }
  }

  /**
   * 检查 health endpoint 是否返回 200 + ok 状态。
   *
   * @param url health endpoint URL
   * @return 当 endpoint 返回 200 且响应包含 "ok" 时返回 true
   */
  static boolean checkHealthEndpoint(String url) {
    try (HttpClient client =
        HttpClient.newBuilder().connectTimeout(Duration.ofMillis(HEALTH_TIMEOUT_MS)).build()) {
      HttpRequest request =
          HttpRequest.newBuilder()
              .uri(URI.create(url))
              .timeout(Duration.ofMillis(HEALTH_TIMEOUT_MS))
              .GET()
              .build();
      HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
      return response.statusCode() == 200 && response.body().contains("ok");
    } catch (Exception e) {
      return false;
    }
  }

  /**
   * 检查指定端口是否有进程在监听。
   *
   * <p>通过尝试建立 TCP 连接判断端口是否活跃。
   *
   * @param port 要检查的端口号
   * @return 端口可连接时返回 true
   */
  static boolean isPortListening(int port) {
    if (port <= 0 || port > 65535) {
      return false;
    }
    try (java.net.Socket socket = new java.net.Socket()) {
      socket.connect(new java.net.InetSocketAddress("127.0.0.1", port), HEALTH_TIMEOUT_MS);
      return true;
    } catch (ConnectException e) {
      return false;
    } catch (IOException e) {
      return false;
    }
  }

  /**
   * 解析索引目录。
   *
   * <p>优先级：CLI 选项 > INDEX_DIR 环境变量 > XDG 平台默认值。
   *
   * @return 解析后的索引目录路径
   */
  private Path resolveIndexDir() {
    return PathResolver.resolveDataDir(indexDirOption, INDEX_DIR_ENV);
  }
}
