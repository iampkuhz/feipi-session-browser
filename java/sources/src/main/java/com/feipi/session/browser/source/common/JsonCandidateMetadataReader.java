package com.feipi.session.browser.source.common;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.Objects;
import java.util.function.Function;
import java.util.function.Predicate;

/** JSONL 候选文件基础元数据的共享扫描器。 */
public final class JsonCandidateMetadataReader {

  private JsonCandidateMetadataReader() {}

  /**
   * 从事件流中读取首个完整的 cwd、title、model 和 git branch 组合。
   *
   * @param events JSON 事件流
   * @param cwdExtractor cwd 提取器
   * @param titleEligible title 候选事件判断器
   * @param titleExtractor title 提取器
   * @param modelExtractor model 提取器
   * @param gitBranchExtractor git branch 提取器
   * @return 基础元数据
   */
  public static Metadata firstComplete(
      Iterable<JsonNode> events,
      Function<JsonNode, String> cwdExtractor,
      Predicate<JsonNode> titleEligible,
      Function<JsonNode, String> titleExtractor,
      Function<JsonNode, String> modelExtractor,
      Function<JsonNode, String> gitBranchExtractor) {
    Objects.requireNonNull(events, "events 不得为 null");
    Objects.requireNonNull(cwdExtractor, "cwdExtractor 不得为 null");
    Objects.requireNonNull(titleEligible, "titleEligible 不得为 null");
    Objects.requireNonNull(titleExtractor, "titleExtractor 不得为 null");
    Objects.requireNonNull(modelExtractor, "modelExtractor 不得为 null");
    Objects.requireNonNull(gitBranchExtractor, "gitBranchExtractor 不得为 null");

    String cwd = "";
    String title = "";
    String model = "";
    String gitBranch = "";
    for (JsonNode event : events) {
      if (cwd.isEmpty()) {
        cwd = value(cwdExtractor, event);
      }
      if (title.isEmpty() && titleEligible.test(event)) {
        title = value(titleExtractor, event);
      }
      if (model.isEmpty()) {
        model = value(modelExtractor, event);
      }
      if (gitBranch.isEmpty()) {
        gitBranch = value(gitBranchExtractor, event);
      }
      if (!cwd.isEmpty() && !title.isEmpty() && !model.isEmpty() && !gitBranch.isEmpty()) {
        break;
      }
    }
    return new Metadata(cwd, title, model, gitBranch);
  }

  private static String value(Function<JsonNode, String> extractor, JsonNode event) {
    String value = extractor.apply(event);
    return value == null ? "" : value;
  }

  /** 候选文件基础元数据。 */
  public static final class Metadata {
    private final String cwd;
    private final String title;
    private final String model;
    private final String gitBranch;

    private Metadata(String cwd, String title, String model, String gitBranch) {
      this.cwd = cwd;
      this.title = title;
      this.model = model;
      this.gitBranch = gitBranch;
    }

    /** 返回候选文件工作目录。 */
    public String cwd() {
      return cwd;
    }

    /** 返回候选文件展示标题。 */
    public String title() {
      return title;
    }

    /** 返回候选文件模型名称。 */
    public String model() {
      return model;
    }

    /** 返回候选文件 git branch。 */
    public String gitBranch() {
      return gitBranch;
    }
  }
}
