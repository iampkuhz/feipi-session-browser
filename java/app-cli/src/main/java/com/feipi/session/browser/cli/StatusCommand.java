package com.feipi.session.browser.cli;

import java.io.IOException;
import java.nio.file.Path;
import java.util.concurrent.Callable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;

/**
 * status 子命令实现：查看服务运行状态。
 *
 * <p>通过 PID 文件和端口探测综合判断服务运行状态，输出 PID、端口、启动时间等信息。 不修改任何数据，仅做只读查询。
 *
 * <p>退出码：
 *
 * <ul>
 *   <li>0 — 服务运行中
 *   <li>1 — 服务未运行或状态未知
 * </ul>
 *
 * <p>校验放置：PID 文件解析在 {@link PidFile#read} 边界执行一次； 进程存活性和端口归属验证在本类执行一次； 下游不重复校验。
 */
@Command(
    name = "status",
    mixinStandardHelpOptions = true,
    description = "查看服务运行状态",
    sortOptions = false)
final class StatusCommand implements Callable<Integer> {

  private static final Logger LOG = LoggerFactory.getLogger(StatusCommand.class);

  /** 默认端口，与 serve 命令一致。 */
  private static final int DEFAULT_PORT = 8848;

  /** 默认索引目录环境变量名。 */
  private static final String INDEX_DIR_ENV = "INDEX_DIR";

  @Option(
      names = {"--port", "-p"},
      description = "服务端口（默认 ${DEFAULT-VALUE}），用于辅助探测",
      defaultValue = "" + DEFAULT_PORT)
  private int port;

  @Option(
      names = {"--index-dir"},
      description = "索引目录（默认与 serve 相同）")
  private String indexDirOption;

  @Override
  public Integer call() {
    Path indexDir = PathResolver.resolveDataDir(indexDirOption, INDEX_DIR_ENV);

    try {
      return reportStatus(indexDir);
    } catch (IOException e) {
      System.err.println("错误：状态查询失败: " + e.getMessage());
      return 1;
    }
  }

  /**
   * 查询并报告服务状态。
   *
   * <p>优先通过 PID 文件判断，回退到端口探测。
   *
   * @param indexDir 索引目录
   * @return 退出码
   * @throws IOException PID 文件读取失败时
   */
  private int reportStatus(Path indexDir) throws IOException {
    PidFile.ProcessCheck check = PidFile.checkProcess(indexDir);

    if (check.meta() != null) {
      return reportFromProcessCheck(check, indexDir);
    }

    // PID 文件不存在，回退到端口探测
    return reportFromPortProbe();
  }

  /**
   * 通过进程检查结果报告状态。
   *
   * @param check 进程检查结果
   * @param indexDir 索引目录
   * @return 退出码
   */
  private static int reportFromProcessCheck(PidFile.ProcessCheck check, Path indexDir) {
    PidFile.Metadata meta = check.meta();

    if (check.processAlive()) {
      System.out.println("服务状态：运行中");
      System.out.println("  PID:    " + meta.pid());
      if (meta.port() > 0) {
        System.out.println("  端口:   " + meta.port());
        System.out.println("  地址:   " + meta.host() + ":" + meta.port());
      }
      System.out.println("  索引:   " + meta.indexDir().toAbsolutePath());
      if (!meta.startedAt().isEmpty()) {
        System.out.println("  启动于: " + meta.startedAt());
      }
      return 0;
    }

    // PID 文件存在但进程不在运行
    System.out.println("服务状态：未运行（stale PID 文件）");
    System.out.println("  PID 文件: " + PidFile.path(indexDir).toAbsolutePath());
    System.out.println("  记录 PID: " + meta.pid() + "（进程已不在运行）");
    return 1;
  }

  /**
   * 通过端口探测报告状态。
   *
   * <p>PID 文件缺失时的回退策略：尝试连接默认端口判断是否有服务运行。
   *
   * @return 退出码
   */
  private int reportFromPortProbe() {
    if (port > 0 && port <= 65535 && StopCommand.isPortListening(port)) {
      System.out.println("服务状态：运行中（端口探测）");
      System.out.println("  端口:   " + port);
      System.out.println("  注意:   PID 文件缺失，无法确认进程归属");
      return 0;
    }

    System.out.println("服务状态：未运行");
    return 1;
  }
}
