package com.feipi.session.browser.cli;

import com.feipi.session.browser.data.batch.service.NormalizedBatchRunner;
import java.nio.file.Path;
import java.util.concurrent.Callable;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;

/**
 * 隐藏的批量归一化子命令。
 *
 * <p>本类只负责 Picocli 参数解析和 CLI 进程 I/O 绑定；stdin NDJSON 协议解析、源根处理、归一化和制品写入由 {@link
 * NormalizedBatchRunner} 执行。
 */
@Command(
    name = "normalized-batch",
    description = "隐藏命令：批量归一化 session 并写入 artifact",
    hidden = true,
    mixinStandardHelpOptions = true)
final class NormalizedBatchCommand implements Callable<Integer> {

  @Option(
      names = {"--output-dir"},
      description = "artifact 输出目录",
      required = true)
  private Path outputDir;

  /** 执行批量归一化 CLI shell。 */
  @Override
  public Integer call() throws Exception {
    return new NormalizedBatchRunner()
        .run(System.in, System.out, outputDir, SourceAdapterRegistry::forSourceId);
  }
}
