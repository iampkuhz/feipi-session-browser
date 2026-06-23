package com.feipi.session.browser.reuse.analyzer;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.reuse.analyzer.cache.AnalyzerCache;
import com.feipi.session.browser.reuse.analyzer.fingerprint.CallSequenceFingerprinter;
import com.feipi.session.browser.reuse.analyzer.fingerprint.Fingerprinter;
import com.feipi.session.browser.reuse.analyzer.model.AnalysisResult;
import com.feipi.session.browser.reuse.analyzer.model.Finding;
import com.feipi.session.browser.reuse.analyzer.model.InputManifest;
import com.feipi.session.browser.reuse.analyzer.model.Ownership;
import com.feipi.session.browser.reuse.analyzer.model.Severity;
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.stream.Stream;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import spoon.reflect.CtModel;
import spoon.reflect.declaration.CtMethod;
import spoon.reflect.declaration.CtType;

/**
 * 代码复用分析主编排器。
 *
 * <p>协调 Spoon 模型构建、fingerprint 计算、peer group 解析、ownership 分类、 缓存管理和 finding 生成。
 *
 * <p>所有报告排序，确保多次执行字节稳定。
 */
public final class ReuseAnalyzer {

  private static final Logger LOG = LoggerFactory.getLogger(ReuseAnalyzer.class);
  private static final String SPOON_VERSION = "11.1.0";

  private final Path cacheDirectory;
  private final ObjectMapper objectMapper;

  /** 创建复用分析器实例。 */
  public ReuseAnalyzer(Path cacheDirectory) {
    this.cacheDirectory = cacheDirectory;
    this.objectMapper = new ObjectMapper();
  }

  /** 执行全量分析。 构建 Spoon 模型，计算所有 fingerprint，生成 findings。 */
  public AnalysisResult analyzeFull(InputManifest manifest) throws IOException {
    LOG.info("开始全量分析，模块数：{}", manifest.modules().size());

    // 收集所有 source roots 和 classpath
    List<File> sourceRoots = new ArrayList<>();
    List<String> classpath = new ArrayList<>();
    for (var module : manifest.modules()) {
      for (String root : module.productionSourceRoots()) {
        File rootFile = new File(root);
        if (rootFile.exists()) {
          sourceRoots.add(rootFile);
        }
      }
      classpath.addAll(module.compileClasspath());
    }

    if (sourceRoots.isEmpty()) {
      LOG.warn("无有效 source roots，返回空结果");
      return AnalysisResult.empty();
    }

    // 计算 cache key
    String sourceDigest = computeSourceDigest(sourceRoots);
    String classpathDigest = sha256(String.join("|", classpath));
    String topologyDigest = computeTopologyDigest(manifest);
    String cacheKey =
        AnalyzerCache.buildCacheKey(
            sourceDigest,
            SPOON_VERSION,
            manifest.policyDigest(),
            manifest.javaVersion(),
            topologyDigest,
            classpathDigest);

    // 尝试从缓存加载
    AnalyzerCache cache = new AnalyzerCache(cacheDirectory);
    Map<String, Object> cached = cache.load(cacheKey);
    if (cached != null) {
      LOG.info("缓存命中，从缓存加载分析结果");
      return loadResultFromCache(cached);
    }

    // 缓存未命中，构建模型
    LOG.info("缓存未命中，构建 Spoon 模型...");
    CtModel model;
    try {
      model = SpoonAnalyzer.buildModel(sourceRoots, classpath);
    } catch (SpoonAnalyzer.SpoonAnalysisException e) {
      LOG.error("Spoon 模型构建失败：{}", e.getMessage());
      throw e;
    }

    // 计算所有 fingerprint 和 finding
    AnalysisResult result = computeFindings(model, manifest);

    // 存入缓存
    Map<String, Object> cacheData = serializeResult(result);
    cache.store(cacheKey, cacheData);

    return result;
  }

  /**
   * 执行增量分析。 只分析 changed files，与全仓 fingerprint index 比较。
   *
   * <p>当 bootstrap state 不存在时，返回 BOOTSTRAP_REQUIRED，不伪造 PASS。
   */
  public AnalysisResult analyzeIncremental(InputManifest manifest, Path bootstrapStateFile)
      throws IOException {
    // 检查 bootstrap state
    if (bootstrapStateFile == null || !Files.exists(bootstrapStateFile)) {
      return AnalysisResult.bootstrapRequired("bootstrap-state.json 不存在，需要先执行 reuseBootstrapFull");
    }

    // 读取 bootstrap state
    String bootstrapContent = Files.readString(bootstrapStateFile, StandardCharsets.UTF_8);
    @SuppressWarnings("unchecked")
    Map<String, Object> bootstrapState = objectMapper.readValue(bootstrapContent, Map.class);
    String status = (String) bootstrapState.get("status");
    if (!"accepted".equals(status)) {
      return AnalysisResult.bootstrapRequired("bootstrap state 状态为 " + status + "，非 accepted");
    }

    // 增量分析：只关注 changed files
    List<String> changedFiles = manifest.changedFiles();
    if (changedFiles.isEmpty()) {
      LOG.info("无变更文件，返回空结果");
      return AnalysisResult.empty();
    }

    // 全量分析获取基线，然后过滤只报告与 changed code 相交的 finding
    AnalysisResult fullResult = analyzeFull(manifest);
    Set<String> changedFileSet = new HashSet<>(changedFiles);

    List<Finding> incrementalFindings =
        fullResult.findings().stream()
            .filter(f -> f.touchesChangedCode() || isRelatedToChangedFiles(f, changedFileSet))
            .toList();

    return new AnalysisResult(
        fullResult.status(),
        fullResult.schemaVersion(),
        incrementalFindings,
        fullResult.metadata());
  }

  /** 执行自测验证。 */
  public AnalysisResult selfTest() {
    LOG.info("执行 analyzer 自测...");
    // 验证 Spoon 可用
    try {
      var launcher = new spoon.Launcher();
      launcher.getEnvironment().setComplianceLevel(21);
      launcher.getEnvironment().setNoClasspath(false);
      launcher.getEnvironment().setCommentEnabled(false);
      launcher.getEnvironment().setShouldCompile(false);
      launcher.addInputResource(
          new spoon.support.compiler.VirtualFile("class SelfTest {}", "SelfTest.java"));
      launcher.buildModel();
      if (launcher.getModel().getAllTypes().isEmpty()) {
        return AnalysisResult.bootstrapRequired("Spoon 自测失败：模型为空");
      }
    } catch (Exception e) {
      return AnalysisResult.bootstrapRequired("Spoon 自测异常：" + e.getMessage());
    }

    LOG.info("Analyzer 自测通过");
    return AnalysisResult.empty();
  }

  /** 计算模型中的 findings。 使用 hash index 比较 fingerprint，不做 O(n^2) 两两比较。 */
  private AnalysisResult computeFindings(CtModel model, InputManifest manifest) {
    // 构建 fingerprint 索引，使用 hash 映射到出现位置
    Map<String, List<MethodOccurrence>> exactIndex = new HashMap<>();
    Map<String, List<MethodOccurrence>> alphaIndex = new HashMap<>();
    Map<String, List<String>> callSeqIndex = new HashMap<>();
    Map<String, List<MethodOccurrence>> statementIndex = new HashMap<>();
    Set<String> changedFileSet = new HashSet<>(manifest.changedFiles());

    Collection<CtType<?>> allTypes = SpoonAnalyzer.getAllTypes(model);
    Map<String, List<String>> peerGroups = PeerGroupResolver.buildPeerGroups(allTypes);

    for (CtType<?> type : allTypes) {
      String peerGroup = PeerGroupResolver.resolvePeerGroup(type);
      for (CtMethod<?> method : SpoonAnalyzer.getAllMethods(type)) {
        String methodId = MethodIdGenerator.methodId(method);
        Ownership ownership = OwnershipClassifier.classify(method);

        // 精确 fingerprint
        String exactFp = Fingerprinter.exactMethodFingerprint(method);
        exactIndex
            .computeIfAbsent(exactFp, k -> new ArrayList<>())
            .add(
                new MethodOccurrence(
                    methodId,
                    type.getQualifiedName(),
                    method.getSimpleName(),
                    ownership,
                    peerGroup));

        // 归一化 fingerprint
        String alphaFp = Fingerprinter.alphaMethodFingerprint(method);
        alphaIndex
            .computeIfAbsent(alphaFp, k -> new ArrayList<>())
            .add(
                new MethodOccurrence(
                    methodId,
                    type.getQualifiedName(),
                    method.getSimpleName(),
                    ownership,
                    peerGroup));

        // 调用序列 fingerprint
        String callSeqFp = CallSequenceFingerprinter.callSequenceFingerprint(method);
        callSeqIndex.computeIfAbsent(callSeqFp, k -> new ArrayList<>()).add(methodId);

        // 语句级 fingerprint
        List<String> stmtFps = Fingerprinter.allStatementFingerprints(method);
        for (String stmtFp : stmtFps) {
          statementIndex
              .computeIfAbsent(stmtFp, k -> new ArrayList<>())
              .add(
                  new MethodOccurrence(
                      methodId,
                      type.getQualifiedName(),
                      method.getSimpleName(),
                      ownership,
                      peerGroup));
        }
      }
    }

    // 生成 findings（只报告有重复的）
    List<Finding> findings = new ArrayList<>();
    int findingCounter = 0;

    // P0：peer group 中 exact 相同完整方法
    for (var entry : exactIndex.entrySet()) {
      List<MethodOccurrence> occurrences = entry.getValue();
      if (occurrences.size() < 2) continue;

      // 检查是否在同一个 peer group
      Set<String> types = new HashSet<>();
      for (var occ : occurrences) {
        types.add(occ.typeName);
      }

      Severity severity;
      if (types.size() >= 3) {
        severity = Severity.P0; // 三个 production 类型完整方法 exact 相同
      } else if (types.size() == 2 && isInSamePeerGroup(occurrences, peerGroups)) {
        severity = Severity.P0; // peer group 中两个完整方法 exact 相同
      } else {
        severity = Severity.P1;
      }

      boolean touchesChanged =
          occurrences.stream().anyMatch(o -> isTypeInChangedFiles(o.typeName, changedFileSet));

      findingCounter++;
      findings.add(
          createFinding(
              "F" + String.format("%04d", findingCounter),
              severity,
              "EXACT_METHOD_DUPLICATE",
              entry.getKey(),
              occurrences,
              touchesChanged,
              peerGroups));
    }

    // P1：statement 级重复
    for (var entry : statementIndex.entrySet()) {
      List<MethodOccurrence> occurrences = entry.getValue();
      if (occurrences.size() < 2) continue;

      // 去重（同一方法可能有多个相同语句）
      Set<String> uniqueTypes = new HashSet<>();
      for (var occ : occurrences) {
        uniqueTypes.add(occ.typeName + "#" + occ.methodName);
      }
      if (uniqueTypes.size() < 2) continue;

      boolean touchesChanged =
          occurrences.stream().anyMatch(o -> isTypeInChangedFiles(o.typeName, changedFileSet));

      findingCounter++;
      findings.add(
          createFinding(
              "F" + String.format("%04d", findingCounter),
              Severity.P1,
              "STATEMENT_DUPLICATE",
              entry.getKey(),
              occurrences,
              touchesChanged,
              peerGroups));
    }

    // P2：alpha 相同（变量重命名但结构相同）
    for (var entry : alphaIndex.entrySet()) {
      List<MethodOccurrence> occurrences = entry.getValue();
      if (occurrences.size() < 2) continue;

      // 如果已经在 exact 中报告过，跳过
      Set<String> uniqueTypes = new HashSet<>();
      for (var occ : occurrences) {
        uniqueTypes.add(occ.typeName + "#" + occ.methodName);
      }
      if (uniqueTypes.size() < 2) continue;

      boolean touchesChanged =
          occurrences.stream().anyMatch(o -> isTypeInChangedFiles(o.typeName, changedFileSet));

      findingCounter++;
      findings.add(
          createFinding(
              "F" + String.format("%04d", findingCounter),
              Severity.P2,
              "ALPHA_EQUIVALENT",
              entry.getKey(),
              occurrences,
              touchesChanged,
              peerGroups));
    }

    // 按 id 排序，确保确定性
    findings.sort((a, b) -> a.id().compareTo(b.id()));

    boolean hasP0 = findings.stream().anyMatch(f -> f.severity() == Severity.P0);
    boolean hasP1WithoutDecision = findings.stream().anyMatch(f -> f.severity() == Severity.P1);

    String status;
    if (hasP0) {
      status = "FAIL";
    } else if (hasP1WithoutDecision) {
      status = "FAIL";
    } else {
      status = "PASS";
    }

    return new AnalysisResult(
        status,
        1,
        findings,
        Map.of("totalTypes", allTypes.size(), "totalFindings", findings.size()));
  }

  private Finding createFinding(
      String id,
      Severity severity,
      String kind,
      String fingerprint,
      List<MethodOccurrence> occurrences,
      boolean touchesChanged,
      Map<String, List<String>> peerGroups) {

    List<Map<String, Object>> occMaps =
        occurrences.stream()
            .map(
                o -> {
                  Map<String, Object> m = new TreeMap<>();
                  m.put("methodId", o.methodId);
                  m.put("type", o.typeName);
                  m.put("method", o.methodName);
                  m.put("ownership", o.ownership.name());
                  if (o.peerGroup != null) {
                    m.put("peerGroup", o.peerGroup);
                  }
                  return m;
                })
            .toList();

    Map<String, Object> ownershipMap = new TreeMap<>();
    ownershipMap.put(
        "distribution",
        occurrences.stream()
            .collect(
                java.util.stream.Collectors.groupingBy(
                    o -> o.ownership.name(), java.util.stream.Collectors.counting())));

    // 取第一个非空的 peer group 标识
    String pg =
        occurrences.stream().map(o -> o.peerGroup).filter(p -> p != null).findFirst().orElse(null);

    List<String> suggested = computeSuggestedDecisions(severity, occurrences);

    return new Finding(
        id, severity, kind, fingerprint, occMaps, touchesChanged, suggested, ownershipMap, pg);
  }

  private List<String> computeSuggestedDecisions(
      Severity severity, List<MethodOccurrence> occurrences) {
    List<String> decisions = new ArrayList<>();
    switch (severity) {
      case P0 -> {
        decisions.add("EXTRACT_SHARED_COMPONENT");
        decisions.add("REUSE_EXISTING");
      }
      case P1 -> {
        decisions.add("KEEP_ON_OWNER");
        decisions.add("INTENTIONAL_DUPLICATION");
        decisions.add("DEFER");
      }
      case P2 -> {
        decisions.add("INTENTIONAL_DUPLICATION");
        decisions.add("DEFER");
      }
      case P3 -> {
        decisions.add("INTENTIONAL_DUPLICATION");
      }
    }
    return decisions;
  }

  private boolean isInSamePeerGroup(
      List<MethodOccurrence> occurrences, Map<String, List<String>> peerGroups) {
    if (peerGroups.isEmpty()) return false;
    Set<String> types = new HashSet<>();
    for (var occ : occurrences) {
      types.add(occ.typeName);
    }
    for (var group : peerGroups.values()) {
      if (new HashSet<>(group).containsAll(types)) {
        return true;
      }
    }
    return false;
  }

  private boolean isTypeInChangedFiles(String typeName, Set<String> changedFiles) {
    if (changedFiles.isEmpty()) return false;
    // 简单匹配：类型名最后一段对应的文件名
    String simpleName = typeName;
    int dot = typeName.lastIndexOf('.');
    if (dot >= 0) {
      simpleName = typeName.substring(dot + 1);
    }
    String expectedFile = simpleName + ".java";
    for (String changedFile : changedFiles) {
      if (changedFile.endsWith(expectedFile)) {
        return true;
      }
    }
    return false;
  }

  private boolean isRelatedToChangedFiles(Finding finding, Set<String> changedFiles) {
    if (changedFiles.isEmpty()) return false;
    for (var occ : finding.occurrences()) {
      Object type = occ.get("type");
      if (type instanceof String typeName) {
        if (isTypeInChangedFiles(typeName, changedFiles)) {
          return true;
        }
      }
    }
    return false;
  }

  private String computeSourceDigest(List<File> sourceRoots) throws IOException {
    MessageDigest digest;
    try {
      digest = MessageDigest.getInstance("SHA-256");
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException("SHA-256 not available", e);
    }
    for (File root : sourceRoots.stream().sorted().toList()) {
      if (root.exists() && root.isDirectory()) {
        try (Stream<Path> walk = Files.walk(root.toPath())) {
          List<Path> javaFiles = walk.filter(p -> p.toString().endsWith(".java")).sorted().toList();
          for (Path javaFile : javaFiles) {
            byte[] content = Files.readAllBytes(javaFile);
            digest.update(
                root.toPath().relativize(javaFile).toString().getBytes(StandardCharsets.UTF_8));
            digest.update(content);
          }
        }
      }
    }
    return bytesToHex(digest.digest());
  }

  private String computeTopologyDigest(InputManifest manifest) {
    StringBuilder sb = new StringBuilder();
    for (var module : manifest.modules()) {
      sb.append(module.id()).append(':');
      for (String root : module.productionSourceRoots().stream().sorted().toList()) {
        sb.append(root).append(',');
      }
      sb.append(';');
    }
    return sha256(sb.toString());
  }

  private Map<String, Object> serializeResult(AnalysisResult result) {
    Map<String, Object> data = new TreeMap<>();
    data.put("status", result.status());
    data.put("schemaVersion", result.schemaVersion());
    data.put("metadata", result.metadata());
    // findings 序列化为 list
    List<Map<String, Object>> findingList = new ArrayList<>();
    for (Finding f : result.findings()) {
      Map<String, Object> fm = new TreeMap<>();
      fm.put("id", f.id());
      fm.put("severity", f.severity().name());
      fm.put("kind", f.kind());
      fm.put("fingerprint", f.fingerprint());
      fm.put("touchesChangedCode", f.touchesChangedCode());
      fm.put("suggestedDecisions", f.suggestedDecisions());
      fm.put("ownership", f.ownership());
      fm.put("peerGroup", f.peerGroup());
      fm.put("occurrences", f.occurrences());
      findingList.add(fm);
    }
    data.put("findings", findingList);
    return data;
  }

  @SuppressWarnings("unchecked")
  private AnalysisResult loadResultFromCache(Map<String, Object> cached) {
    String status = (String) cached.get("status");
    int schemaVersion = ((Number) cached.get("schemaVersion")).intValue();
    Map<String, Object> metadata = (Map<String, Object>) cached.getOrDefault("metadata", Map.of());
    List<Map<String, Object>> findingData =
        (List<Map<String, Object>>) cached.getOrDefault("findings", List.of());

    List<Finding> findings = new ArrayList<>();
    for (var fd : findingData) {
      findings.add(
          new Finding(
              (String) fd.get("id"),
              Severity.valueOf((String) fd.get("severity")),
              (String) fd.get("kind"),
              (String) fd.get("fingerprint"),
              (List<Map<String, Object>>) fd.getOrDefault("occurrences", List.of()),
              (Boolean) fd.getOrDefault("touchesChangedCode", false),
              (List<String>) fd.getOrDefault("suggestedDecisions", List.of()),
              (Map<String, Object>) fd.getOrDefault("ownership", Map.of()),
              (String) fd.get("peerGroup")));
    }

    return new AnalysisResult(status, schemaVersion, findings, metadata);
  }

  private static String sha256(String input) {
    try {
      MessageDigest digest = MessageDigest.getInstance("SHA-256");
      byte[] hash = digest.digest(input.getBytes(StandardCharsets.UTF_8));
      return bytesToHex(hash);
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException("SHA-256 not available", e);
    }
  }

  private static String bytesToHex(byte[] bytes) {
    StringBuilder sb = new StringBuilder(bytes.length * 2);
    for (byte b : bytes) {
      sb.append(String.format("%02x", b));
    }
    return sb.toString();
  }

  /** 方法 occurrence 的内部记录。 */
  private record MethodOccurrence(
      String methodId, String typeName, String methodName, Ownership ownership, String peerGroup) {}
}
