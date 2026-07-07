package com.feipi.session.browser.source.spi;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedSourceFile;
import com.feipi.session.browser.domain.normalized.SourceFileRole;
import java.nio.file.Path;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/** 源候选项进入归一化阶段前的共享输入构造器。 */
public final class SourceNormalizationInputs {

  private SourceNormalizationInputs() {}

  /** 返回候选项指向的物理 transcript 路径。 */
  public static Path transcriptPath(Candidate candidate) {
    Objects.requireNonNull(candidate, "candidate 不得为 null");
    return Path.of(candidate.fingerprint().locator());
  }

  /** 返回候选项对应的 transcript 源文件元数据列表。 */
  public static List<NormalizedSourceFile> transcriptFiles(Candidate candidate) {
    Path filePath = transcriptPath(candidate);
    return List.of(
        new NormalizedSourceFile(
            SourceFileRole.TRANSCRIPT,
            filePath.toAbsolutePath(),
            Optional.empty(),
            Optional.empty()));
  }

  /** 根据源适配器标识返回归一化 agent 枚举。 */
  public static NormalizedAgent normalizedAgent(SourceAdapter adapter) {
    Objects.requireNonNull(adapter, "adapter 不得为 null");
    return NormalizedAgent.fromValue(adapter.sourceId().getValue());
  }
}
