package com.feipi.session.browser.application.sessiondetail;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.query.api.SensitiveFieldPolicy;
import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Pattern;

/** 仅重放请求调用所属作用域的历史，保持原始载荷不变。 */
public final class CallReadingEvidence {
  private static final String PREFIX = "codex_context_";
  private static final Pattern HOST_SKILLS =
      Pattern.compile(
          "(?m)^<skills_instructions>[ \\t]*\\R(?:(?:[ \\t]*\\R)*## Host skills[ \\t]*\\R)?"
              + "(?:[ \\t]*\\R)*## Skills[ \\t]*\\R[\\s\\S]*?^</skills_instructions>[ \\t]*$");
  private static final Pattern BASE_SKILLS =
      Pattern.compile("(?m)^#{1,3} (?:Host skills|Skills)[ \\t]*$");
  private static final Pattern LIST = Pattern.compile("(?m)^#{2,4} Available skills[ \\t]*$");

  private static final Pattern REGISTRATION =
      Pattern.compile(
          "(?m)^- ([A-Za-z0-9][A-Za-z0-9_-]*(?::[A-Za-z0-9][A-Za-z0-9_-]*)*): [^\\r\\n]* \\(file: [^\\r\\n]+\\)[ \\t]*$");

  private static final Pattern LOADED_SKILL =
      Pattern.compile(
          "\\A<skill>\\R<name>([A-Za-z0-9][A-Za-z0-9_-]*(?::[A-Za-z0-9][A-Za-z0-9_-]*)*)</name>\\R"
              + "<path>[^<>\\r\\n]+</path>\\R([\\s\\S]+)\\R</skill>\\z");

  private CallReadingEvidence() {}

  /** 判断调用是否具有逐响应计量证据，即使其可见助手正文缺失。 */
  public static boolean hasObservedResponse(NormalizedCall call) {
    return call.sourceUnits().stream()
        .anyMatch(unit -> (PREFIX + "response_usage").equals(unit.get("type")));
  }

  /**
   * 仅对可确认调用和载荷方向的内容返回阅读证据。
   *
   * @param content 不可变会话内容
   * @param entry 已校验的载荷标识与当前文本
   * @param visibility 源文本遮蔽策略
   * @return 可定位到一个 Codex 调用时返回该调用的阅读投影
   * @throws IOException 会话内容重放失败
   */
  public static Optional<View> read(
      NormalizedSessionContent content,
      PayloadLookup.PayloadEntry entry,
      PayloadVisibility visibility)
      throws IOException {
    String id = entry.payloadId();
    if (content.header().agent() != NormalizedAgent.CODEX) return Optional.empty();
    String[] parts = id.split(":", 3);
    if (parts.length != 3 || !List.of("req", "resp").contains(parts[1])) return Optional.empty();
    boolean request = "req".equals(parts[1]);
    NormalizedCall selected =
        switch (parts[0]) {
          case "main", "sa" -> find(content, entry.callId());
          case "round" -> uniqueRoundCall(content, parts[2]);
          default -> null;
        };
    if (selected == null) return Optional.empty();
    String target = selected.callId();
    var replay = new Replay(request, SensitiveFieldPolicy.fromVisibility(visibility));
    try (var cursor = content.openCursor()) {
      seek:
      while (cursor.hasNext()) {
        for (var call : cursor.next().calls()) {
          boolean matched = target.equals(call.callId());
          if (call.scope() == selected.scope() && call.subagentId().equals(selected.subagentId())) {
            replay.accept(call, matched);
          }
          if (matched) break seek;
        }
      }
    }
    if (!request || !replay.currentUserRecorded) {
      for (var text : entry.reading()) {
        replay.blocks.add(new Block("conversation", text.label(), "current", text.text()));
      }
    }
    if (request) {
      replay.configuration();
      replay.tokens.putAll(replay.forkMeasurements);
    } else {
      replay.declarations(selected, "current");
      replay.observedResponse();
    }
    return Optional.of(
        new View(replay.blocks, replay.protocol, replay.tokens, replay.skillNames()));
  }

  private static NormalizedCall uniqueRoundCall(NormalizedSessionContent content, String number)
      throws IOException {
    // PayloadLookup 已校验标识；不把多调用轮次归给单个调用。
    int round = Integer.parseInt(number);
    var reader = new SessionContentReader(content, 0);
    if (round < 1 || round > reader.roundIndex().roundCount()) return null;
    var window = reader.calls(round, 0, 2, call -> call);
    return window.total() == 1 ? window.items().getFirst() : null;
  }

  private static NormalizedCall find(NormalizedSessionContent content, String id)
      throws IOException {
    try (var cursor = content.openCursor()) {
      while (cursor.hasNext()) {
        for (var call : cursor.next().calls()) {
          if (id.equals(call.callId())) return call;
        }
      }
    }
    return null;
  }

  /** 收集同一作用域的证据，并在压缩处清除历史对话。 */
  private static final class Replay {
    private final boolean request;
    private final SensitiveFieldPolicy policy;
    private final ArrayList<Block> blocks = new ArrayList<>();
    private final Map<String, String> protocol = new LinkedHashMap<>();
    private final Map<String, Long> tokens = new LinkedHashMap<>();
    private final LinkedHashSet<String> dedup = new LinkedHashSet<>();
    private final LinkedHashSet<Block> stable = new LinkedHashSet<>();
    private final LinkedHashSet<String> toolResults = new LinkedHashSet<>();
    private final LinkedHashSet<String> toolDeclarations = new LinkedHashSet<>();
    private boolean currentUserRecorded;
    private boolean responseUsage;
    private String responseCompaction = "";
    private final Map<String, Long> forkMeasurements = new LinkedHashMap<>();
    private String latestConfiguration = "";
    private String configurationSource = "";

    private Replay(boolean request, SensitiveFieldPolicy policy) {
      this.request = request;
      this.policy = policy;
    }

    private void accept(NormalizedCall call, boolean target) {
      var resultIds = Set.copyOf(call.request().toolResultIds());
      int sideContextChars = 0;
      for (var unit : call.sourceUnits()) {
        String type = String.valueOf(unit.get("type"));
        String role = String.valueOf(unit.get("role"));
        String text = PayloadCallContentExtractor.extractTextValue(unit);
        if ((PREFIX + "side_context_chars").equals(type)) {
          if (request) sideContextChars = sideContextLength(text);
          continue;
        }
        if (sideContextChars > 0 && !type.startsWith(PREFIX)) {
          if ("user".equals(role)
              && Boolean.TRUE.equals(unit.get("isMeta"))
              && sideContextChars <= text.length()) {
            add(
                "side_context",
                "Side Chat 启动上下文",
                target ? "current" : "reconstructed",
                text.substring(0, sideContextChars));
          }
          sideContextChars = 0;
        }
        if (type.startsWith(PREFIX)) {
          context(type.substring(PREFIX.length()), text, target);
        } else if (request && !Boolean.TRUE.equals(unit.get("isMeta"))) {
          String source = target ? "current" : "reconstructed";
          if ("user".equals(role) && PayloadCallContentExtractor.isToolResult(type)) {
            String id = PayloadCallContentExtractor.toolResultId(unit);
            if (!id.isEmpty() && resultIds.contains(id) && toolResults.add(id)) {
              addTool("tool_result", id, source, text, id);
            }
          } else if ("user".equals(role)
              || (!target
                  && "assistant".equals(role)
                  && List.of("assistant", "response_item").contains(type))) {
            currentUserRecorded |= target && "user".equals(role);
            String agents =
                "user".equals(role) ? PayloadCallContentExtractor.projectInstructions(text) : "";
            add("agents", "AGENTS.md", source, agents);
            var visible = new PayloadCallContentExtractor.ReadingText("user".equals(role));
            visible.add(text);
            add("conversation", "user".equals(role) ? "User" : "Assistant", source, visible.text());
          }
        }
      }
      if (request && !target) declarations(call, "reconstructed");
    }

    private static int sideContextLength(String text) {
      try {
        return Math.max(0, Integer.parseInt(text));
      } catch (NumberFormatException invalid) {
        return 0;
      }
    }

    private void declarations(NormalizedCall call, String source) {
      var declared = Set.copyOf(call.response().toolCallIds());
      for (var input : ToolInputContents.inline(call).values()) {
        if (declared.contains(input.id()) && toolDeclarations.add(input.id())) {
          String args = input.input().isBlank() ? "参数未记录" : input.input();
          addTool("tool_call", input.name(), source, args, input.id());
        }
      }
    }

    private void context(String type, String text, boolean current) {
      if (type.startsWith("fork_")) {
        if (request) forkMeasurement(type.substring(5), text);
        return;
      }
      String field =
          switch (type) {
            case "model_provider" -> "modelProvider";
            case "source" -> "source";
            case "originator" -> "originator";
            case "cli_version" -> "cliVersion";
            default -> "";
          };
      if (!field.isEmpty()) {
        protocol.put(field, policy.applyMasking(text));
        return;
      }
      if (List.of(
              "total_tokens",
              "reasoning_tokens",
              "input_tokens",
              "output_tokens",
              "turn_total_tokens")
          .contains(type)) {
        if (current) {
          try {
            long amount = Long.parseLong(text);
            if (amount >= 0) {
              String fieldName =
                  "turn_total_tokens".equals(type)
                      ? "turnTotal"
                      : type.substring(0, type.indexOf('_'));
              tokens.put(fieldName, amount);
            }
          } catch (NumberFormatException ignored) {
            // 不从正文或不完整的快照估算。
          }
        }
        return;
      }
      if (!request) {
        if (current && "response_usage".equals(type)) responseUsage = true;
        if (current && "response_compaction".equals(type)) responseCompaction = text;
        return;
      }
      String source = current ? "current" : "reconstructed";
      if ("boundary".equals(type)) {
        forkMeasurements.clear();
        blocks.removeIf(block -> !stable.contains(block));
        dedup.clear();
        stable.forEach(block -> dedup.add(dedupKey(block.kind(), block.text())));
        toolResults.clear();
        toolDeclarations.clear();
        if (current) {
          String snapshot =
              "replacement_history".equals(text)
                  ? "源记录含 replacement_history 字段；替换快照未展开。"
                  : "此记录未提供 replacement_history 字段。";
          add(
              "context_snapshot",
              "上下文压缩边界",
              source,
              "源记录包含 Codex 上下文压缩边界（compacted）。压缩前的对话不再拼接。" + snapshot);
        }
        return;
      }
      switch (type) {
        case "collaboration_instructions", "collaboration_clear" -> {
          latestConfiguration = "collaboration_clear".equals(type) ? "" : text;
          configurationSource = source;
        }
        case "base" -> instructions("Base instructions", text, source, true);
        case "session" -> instructions("Session instructions", text, source, true);
        case "developer" -> developerInstructions(text, source);
        case "system" -> instructions("System instructions", text, source, false);
        case "session_dynamic_tools" -> sessionTools("Dynamic tools", source, text);
        case "session_additional_tools" -> sessionTools("Additional tools", source, text);
        case "dynamic_tools" -> add("tools", "Dynamic tools", source, text);
        case "additional_tools" -> add("tools", "Additional tools", source, text);
        default -> {}
      }
    }

    private void forkMeasurement(String category, String evidence) {
      if (!List.of(
                  "instructions",
                  "user",
                  "assistant",
                  "tool_input",
                  "tool_result",
                  "tool_definitions")
              .contains(category)
          || !evidence.matches("[0-9]{1,9}:[0-9]{1,9}:[0-9]{1,9}")) return;
      String key = "fork_" + category;
      String[] fields = evidence.split(":");
      forkMeasurements.put(key + "_items", Long.parseLong(fields[0]));
      forkMeasurements.put(key + "_chars", Long.parseLong(fields[1]));
      forkMeasurements.put(key, Long.parseLong(fields[2]));
    }

    private void observedResponse() {
      if (responseUsage && blocks.isEmpty()) {
        add(
            "response_evidence",
            "响应计量证据",
            "current",
            "源记录含当前逐响应 token 用量（token_usage_record），但未记录可见的助手正文或工具声明。");
      }
      if (!responseCompaction.isEmpty()) {
        boolean identity = "identity".equals(responseCompaction);
        if (identity
            && blocks.stream().allMatch(block -> "response_evidence".equals(block.kind()))) {
          Long output = tokens.get("output");
          long reasoning = tokens.getOrDefault("reasoning", 0L);
          if (output != null && output > reasoning)
            tokens.put("compactionOutput", output - reasoning);
        }
        add(
            "response_compaction",
            identity ? "上下文压缩响应" : "相邻压缩事件",
            "current",
            identity
                ? "压缩记录与本次模型响应的 ID 完全一致。这次返回的是上下文压缩产物，不是助手对话正文。"
                : "此响应的用量记录后，下一个解析到的事件是压缩（compacted）。相邻不等于已确认该快照是模型响应正文。");
      }
    }

    private void configuration() {
      if (latestConfiguration.isBlank()) return;
      String masked = policy.applyMasking(latestConfiguration).strip();
      if (blocks.stream()
          .anyMatch(
              block ->
                  List.of("instructions", "base_instructions", "agents").contains(block.kind())
                      && block.text().contains(masked))) return;
      add("configuration", "协作模式 Instructions（配置）", configurationSource, latestConfiguration);
    }

    private void sessionTools(String label, String source, String text) {
      int begin = blocks.size();
      add("tools", label, source, text);
      stable.addAll(blocks.subList(begin, blocks.size()));
    }

    private void developerInstructions(String text, String source) {
      var envelope = LOADED_SKILL.matcher(text.strip());
      if (envelope.matches()
          && !envelope.group(2).contains("<skill>")
          && !envelope.group(2).contains("</skill>")) {
        add("loaded_skill", envelope.group(1), source, envelope.group(2));
      } else {
        instructions("Developer instructions", text, source, false);
      }
    }

    private void instructions(String label, String text, String source, boolean base) {
      int begin = blocks.size();
      String kind = "Base instructions".equals(label) ? "base_instructions" : "instructions";
      var wrapper = HOST_SKILLS.matcher(text);
      if (wrapper.find() && LIST.matcher(wrapper.group()).find()) {
        String captured = wrapper.group();
        add(
            "skills",
            "Skills",
            source,
            captured.substring(captured.indexOf('>') + 1, captured.lastIndexOf('<')).strip());
        add(
            kind,
            label,
            source,
            (text.substring(0, wrapper.start()) + text.substring(wrapper.end())).strip());
      } else {
        var heading = BASE_SKILLS.matcher(text);
        if (base && heading.find() && LIST.matcher(text.substring(heading.start())).find()) {
          add(kind, label, source, text.substring(0, heading.start()).stripTrailing());
          add("skills", "Skills", source, text.substring(heading.start()));
        } else {
          add(kind, label, source, text);
        }
      }
      if (base) stable.addAll(blocks.subList(begin, blocks.size()));
    }

    private void add(String kind, String label, String source, String text) {
      if (text.isBlank()) return;
      String masked = policy.applyMasking(text);
      if (List.of("instructions", "base_instructions", "agents", "skills", "tools").contains(kind)
          && !dedup.add(dedupKey(kind, masked))) return;
      if ("loaded_skill".equals(kind) && !dedup.add(dedupKey(kind, label + '\0' + masked))) return;
      blocks.add(new Block(kind, policy.applyMasking(label), source, masked));
    }

    private void addTool(String kind, String label, String source, String text, String id) {
      if (text.isBlank()) return;
      blocks.add(
          new Block(
              kind,
              policy.applyMasking(label),
              source,
              policy.applyMasking(text),
              policy.applyMasking(id)));
    }

    private static String dedupKey(String kind, String text) {
      return kind + '\0' + text.strip();
    }

    private List<String> skillNames() {
      var names = new LinkedHashSet<String>();
      for (var block : blocks) {
        if (!"skills".equals(block.kind())) continue;
        var heading = LIST.matcher(block.text());
        if (!heading.find()) continue;
        var entries =
            REGISTRATION.matcher(block.text()).region(heading.end(), block.text().length());
        while (entries.find()) names.add(entries.group(1));
      }
      return List.copyOf(names);
    }
  }

  /**
   * 带独立来源标记的阅读片段，不属于原始载荷。
   *
   * @param kind 正文类别
   * @param label 简短展示标签
   * @param source 当前或历史重建证据
   * @param text 已按策略遮蔽的正文
   * @param toolCallId 观测到的关联工具调用标识
   */
  public record Block(String kind, String label, String source, String text, String toolCallId) {
    /** 构造无关联工具调用的阅读片段。 */
    public Block(String kind, String label, String source, String text) {
      this(kind, label, source, text, "");
    }
  }

  /**
   * 单个调用的有序阅读证据与原始协议元数据。
   *
   * @param blocks 阅读片段
   * @param protocol 观测到的提供方、入口类型、客户端和版本
   * @param tokens 单独观测到的输入、输出、总量和推理 token 数
   * @param skillNames 已记录的可用技能名称
   */
  public record View(
      List<Block> blocks,
      Map<String, String> protocol,
      Map<String, Long> tokens,
      List<String> skillNames) {
    /** 保存完整投影的不可变副本。 */
    public View {
      blocks = List.copyOf(blocks);
      protocol = Map.copyOf(protocol);
      tokens = Map.copyOf(tokens);
      skillNames = List.copyOf(skillNames);
    }
  }
}
