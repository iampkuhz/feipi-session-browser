package com.feipi.session.browser.cli.diagnose;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSourceFile;
import com.feipi.session.browser.domain.normalized.SourceFileRole;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.source.claude.ClaudeSourceAdapter;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceResult;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * 诊断管道编排器。
 *
 * <p>按 source → raw → normalization → projection → divergence 顺序执行， 每个阶段记录耗时，共享解析结果。
 */
public final class DiagnosePipeline {

  private static final Logger LOG = Logger.getLogger(DiagnosePipeline.class.getName());

  private DiagnosePipeline() {}

  /**
   * 执行诊断管道。
   *
   * @param agent agent 类型字符串（如 "claude_code"）
   * @param sessionId 目标 session ID
   * @param sourceRoot 源数据根目录
   * @return 诊断输出
   */
  public static DiagnoseOutputModel.DiagnoseOutput run(
      String agent, String sessionId, Path sourceRoot) {
    long totalStart = System.currentTimeMillis();
    List<String> warnings = new ArrayList<>();

    // 1. Source 定位
    long sourceStart = System.currentTimeMillis();
    SourceInfo sourceResult = findSource(agent, sessionId, sourceRoot, warnings);
    long sourceMs = System.currentTimeMillis() - sourceStart;

    // 2. Raw 解析
    long rawStart = System.currentTimeMillis();
    RawResult rawResult = parseRaw(agent, sessionId, sourceResult, sourceRoot, warnings);
    long rawMs = System.currentTimeMillis() - rawStart;

    // 3. 归一化
    long normStart = System.currentTimeMillis();
    NormalizationResult normResult = runNormalization(agent, rawResult, warnings);
    long normalizationMs = System.currentTimeMillis() - normStart;

    // 4. 投影
    long projStart = System.currentTimeMillis();
    DiagnoseOutputModel.ProjectionInfo projection = runProjection(normResult);
    long projectionMs = System.currentTimeMillis() - projStart;

    long totalMs = System.currentTimeMillis() - totalStart;

    // 5. 分歧检测
    DiagnoseOutputModel.DivergenceInfo divergence =
        DivergenceDetector.detect(
            rawResult.rawInfo(),
            normResult.normInfo(),
            projection,
            sourceResult.sourceInfo().subagentFileCount());

    return new DiagnoseOutputModel.DiagnoseOutput(
        DiagnoseOutputModel.SCHEMA_VERSION,
        new DiagnoseOutputModel.RequestInfo(
            agent, sessionId, sourceRoot.toAbsolutePath().toString()),
        sourceResult.sourceInfo(),
        rawResult.rawInfo(),
        normResult.normInfo(),
        projection,
        divergence,
        new DiagnoseOutputModel.TimingInfo(totalMs, sourceMs, rawMs, normalizationMs, projectionMs),
        List.copyOf(warnings));
  }

  // ===== 源定位层 =====

  /**
   * Source 层内部结果：对外输出的 SourceInfo 加上 transcript 路径。
   *
   * @param sourceInfo 对外输出的源信息
   * @param transcriptPath transcript 文件路径
   */
  private record SourceInfo(DiagnoseOutputModel.SourceInfo sourceInfo, Path transcriptPath) {}

  private static SourceInfo findSource(
      String agent, String sessionId, Path sourceRoot, List<String> warnings) {
    if (!"claude_code".equalsIgnoreCase(agent)) {
      warnings.add("agent '" + agent + "' 目前仅支持 claude_code 的完整诊断");
      DiagnoseOutputModel.SourceInfo unavailable =
          new DiagnoseOutputModel.SourceInfo(
              "UNAVAILABLE", "", 0, "", 0, List.of(), "UNAVAILABLE", Map.of());
      return new SourceInfo(unavailable, null);
    }

    Optional<SourceFinder.ClaudeSessionLocation> location =
        SourceFinder.findClaudeSession(sourceRoot, sessionId);

    if (location.isEmpty()) {
      DiagnoseOutputModel.SourceInfo notFound =
          new DiagnoseOutputModel.SourceInfo(
              "ERROR", "", 0, "", 0, List.of(), "UNAVAILABLE", Map.of());
      return new SourceInfo(notFound, null);
    }

    SourceFinder.ClaudeSessionLocation loc = location.get();

    // subagent 文件信息
    List<DiagnoseOutputModel.SubagentFileInfo> subagentFiles = new ArrayList<>();
    for (Path saFile : loc.subagentJsonlFiles()) {
      long size = 0;
      try {
        size = java.nio.file.Files.size(saFile);
      } catch (Exception e) {
        warnings.add("无法读取 subagent 文件大小: " + saFile.getFileName());
      }
      // 检查对应 .meta.json
      String metaName = saFile.getFileName().toString().replace(".jsonl", ".meta.json");
      Path metaPath = saFile.resolveSibling(metaName);
      String metaStatus = java.nio.file.Files.isRegularFile(metaPath) ? "OBSERVED" : "UNAVAILABLE";
      subagentFiles.add(
          new DiagnoseOutputModel.SubagentFileInfo(
              saFile.getFileName().toString(), size, metaStatus));
    }

    DiagnoseOutputModel.SourceInfo sourceInfo =
        new DiagnoseOutputModel.SourceInfo(
            loc.transcriptExists() ? "OBSERVED" : "ERROR",
            loc.transcriptExists() ? loc.transcriptPath().toAbsolutePath().toString() : "",
            loc.transcriptSizeBytes(),
            loc.subagentsDirExists() ? loc.subagentsDir().toAbsolutePath().toString() : "",
            loc.subagentJsonlFiles().size(),
            List.copyOf(subagentFiles),
            loc.metaFromHistory().isEmpty() ? "UNAVAILABLE" : "OBSERVED",
            loc.metaFromHistory());

    return new SourceInfo(sourceInfo, loc.transcriptExists() ? loc.transcriptPath() : null);
  }

  // ===== 原始解析层 =====

  /**
   * Raw 层内部结果：原始统计、解析记录、诊断和底层 SourceResult。
   *
   * @param rawInfo 原始统计信息
   * @param records 解析后的源记录列表
   * @param diagnostics 解析诊断信息列表
   * @param result 底层源解析结果
   */
  private record RawResult(
      DiagnoseOutputModel.RawInfo rawInfo,
      List<SourceRecord> records,
      List<SourceDiagnostic> diagnostics,
      SourceResult result) {}

  private static RawResult parseRaw(
      String agent,
      String sessionId,
      SourceInfo sourceInfo,
      Path sourceRoot,
      List<String> warnings) {
    if (sourceInfo.transcriptPath() == null) {
      return new RawResult(
          new DiagnoseOutputModel.RawInfo("UNAVAILABLE", 0, Map.of(), 0, 0, 0, 0, 0, List.of()),
          List.of(),
          List.of(),
          null);
    }

    try {
      SourceAdapter adapter = new ClaudeSourceAdapter();

      // 构建 Candidate
      SourceFingerprint fp = adapter.fingerprint(sourceInfo.transcriptPath());
      String sessionKey = "claude_code:" + sessionId;
      Candidate candidate = new Candidate(fp, sessionKey, "", Map.of());

      SourceResult result = adapter.parse(candidate, null);

      if (result instanceof SourceResult.Success success) {
        List<SourceRecord> records = success.records();
        List<SourceDiagnostic> diags = success.diagnostics();
        List<String> errors = new ArrayList<>();
        for (SourceDiagnostic diag : diags) {
          if (diag.severity().name().equals("ERROR")) {
            errors.add(diag.message());
          }
        }
        DiagnoseOutputModel.RawInfo rawInfo = RawSummarizer.summarize(records, errors);
        return new RawResult(rawInfo, records, diags, result);
      } else if (result instanceof SourceResult.Skipped skipped) {
        warnings.add("解析跳过: " + skipped.message());
        return new RawResult(
            new DiagnoseOutputModel.RawInfo("UNAVAILABLE", 0, Map.of(), 0, 0, 0, 0, 0, List.of()),
            List.of(),
            List.of(),
            result);
      } else if (result instanceof SourceResult.Fatal fatal) {
        List<String> errors = List.of(fatal.errorDetail());
        return new RawResult(
            new DiagnoseOutputModel.RawInfo("ERROR", 0, Map.of(), 0, 0, 0, 0, 0, errors),
            List.of(),
            fatal.diagnostics(),
            result);
      }
    } catch (Exception e) {
      LOG.log(Level.FINE, "源解析异常", e);
      warnings.add("源解析异常: " + e.getMessage());
    }

    return new RawResult(
        new DiagnoseOutputModel.RawInfo("ERROR", 0, Map.of(), 0, 0, 0, 0, 0, List.of("解析失败")),
        List.of(),
        List.of(),
        null);
  }

  // ===== 归一化层 =====

  /**
   * Normalization 层内部结果：归一化统计和制品。
   *
   * @param normInfo 归一化统计信息
   * @param artifact 归一化制品
   */
  private record NormalizationResult(
      DiagnoseOutputModel.NormalizationInfo normInfo, NormalizedSessionArtifact artifact) {}

  private static NormalizationResult runNormalization(
      String agent, RawResult rawResult, List<String> warnings) {
    if (rawResult.records().isEmpty()) {
      return new NormalizationResult(
          new DiagnoseOutputModel.NormalizationInfo("UNAVAILABLE", "", 0, 0, 0, 0, 0, 0, 0), null);
    }

    try {
      NormalizedAgent normalizedAgent = NormalizedAgent.fromValue(agent.toLowerCase());
      List<NormalizedSourceFile> sourceFiles = buildSourceFiles(rawResult);
      NormalizationEngine engine = new NormalizationEngine();
      NormalizedSessionArtifact artifact =
          engine.normalize(
              normalizedAgent, rawResult.records(), rawResult.diagnostics(), sourceFiles);

      DiagnoseOutputModel.NormalizationInfo normInfo = NormalizationSummarizer.summarize(artifact);
      return new NormalizationResult(normInfo, artifact);
    } catch (Exception e) {
      LOG.log(Level.FINE, "归一化异常", e);
      warnings.add("归一化异常: " + e.getMessage());
      return new NormalizationResult(
          new DiagnoseOutputModel.NormalizationInfo("ERROR", "", 0, 0, 0, 0, 0, 0, 0), null);
    }
  }

  private static List<NormalizedSourceFile> buildSourceFiles(RawResult rawResult) {
    List<NormalizedSourceFile> files = new ArrayList<>();
    if (rawResult.result() instanceof SourceResult.Success success) {
      // 主 transcript 文件
      String locator = success.locator() != null ? success.locator() : "transcript";
      files.add(
          new NormalizedSourceFile(
              SourceFileRole.TRANSCRIPT, Path.of(locator), Optional.empty(), Optional.empty()));
    }
    // 为 subagent records 的 locator 添加额外 source files
    var subagentLocators =
        rawResult.records().stream()
            .filter(r -> r.locator().contains("/subagents/"))
            .map(SourceRecord::locator)
            .distinct()
            .toList();
    for (String loc : subagentLocators) {
      files.add(
          new NormalizedSourceFile(
              SourceFileRole.SUBAGENT_SESSION, Path.of(loc), Optional.empty(), Optional.empty()));
    }
    return files;
  }

  // ===== 投影层 =====

  private static DiagnoseOutputModel.ProjectionInfo runProjection(NormalizationResult normResult) {
    if (normResult.artifact() == null) {
      return new DiagnoseOutputModel.ProjectionInfo("UNAVAILABLE", 0, 0, 0, 0, 0);
    }
    return ProjectionSummarizer.summarize(normResult.artifact());
  }
}
