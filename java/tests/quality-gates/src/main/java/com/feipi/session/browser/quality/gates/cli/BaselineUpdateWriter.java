package com.feipi.session.browser.quality.gates.cli;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.util.DefaultIndenter;
import com.fasterxml.jackson.core.util.DefaultPrettyPrinter;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/** 严格合并同一 JSON baseline 的多个 rule section，并以稳定字节原子替换。 */
final class BaselineUpdateWriter {

  private static final ObjectMapper MAPPER =
      new ObjectMapper()
          .enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION)
          .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

  private BaselineUpdateWriter() {}

  /** 合并完整 rule sections；共享文件损坏时拒绝覆盖。 */
  static void mergeAndWrite(Path path, Map<String, Map<String, List<String>>> replacements)
      throws IOException {
    mergeAndWrite(path, replacements, BaselineUpdateWriter::moveAtomically);
  }

  /** 允许测试注入原子移动失败结果；生产路径始终要求原子替换。 */
  static void mergeAndWrite(
      Path path, Map<String, Map<String, List<String>>> replacements, AtomicMover atomicMover)
      throws IOException {
    var existingRules = readRules(path);
    var merged = new LinkedHashMap<String, JsonNode>();
    var fields = existingRules.fields();
    while (fields.hasNext()) {
      var field = fields.next();
      validateSection(field.getKey(), field.getValue());
      merged.put(field.getKey(), field.getValue().deepCopy());
    }
    for (var replacement : new TreeMap<>(replacements).entrySet()) {
      merged.put(replacement.getKey(), sectionNode(replacement.getValue()));
    }

    var normalizedRoot = MAPPER.createObjectNode();
    normalizedRoot.put("version", 1);
    var normalizedRules = normalizedRoot.putObject("rules");
    merged.forEach(normalizedRules::set);
    atomicWrite(path, stableJson(normalizedRoot), atomicMover);
  }

  private static ObjectNode readRules(Path path) throws IOException {
    if (!Files.exists(path)) {
      return MAPPER.createObjectNode();
    }
    var root = MAPPER.readTree(path.toFile());
    if (root == null || !root.isObject()) {
      throw new IOException("baseline root must be an object: " + path);
    }
    var rootFields = root.fieldNames();
    while (rootFields.hasNext()) {
      var field = rootFields.next();
      if (!"version".equals(field) && !"rules".equals(field)) {
        throw new IOException("unexpected baseline root field: " + field);
      }
    }
    var version = root.get("version");
    var rules = root.get("rules");
    if (version == null || !version.isInt() || version.intValue() != 1) {
      throw new IOException("baseline version must be 1: " + path);
    }
    if (rules == null || !rules.isObject()) {
      throw new IOException("baseline rules must be an object: " + path);
    }
    return (ObjectNode) rules;
  }

  private static void validateSection(String ruleId, JsonNode section) throws IOException {
    if (!section.isObject()) {
      throw new IOException("baseline rule section must be an object: " + ruleId);
    }
    var categories = section.fields();
    while (categories.hasNext()) {
      var category = categories.next();
      if (!category.getValue().isArray()) {
        throw new IOException(
            "baseline category must be an array: " + ruleId + "/" + category.getKey());
      }
      for (var entry : category.getValue()) {
        if (!entry.isTextual()) {
          throw new IOException(
              "baseline category entry must be text: " + ruleId + "/" + category.getKey());
        }
      }
    }
  }

  private static ObjectNode sectionNode(Map<String, List<String>> section) {
    var result = MAPPER.createObjectNode();
    new TreeMap<>(section)
        .forEach(
            (category, entries) -> {
              var values = result.putArray(category);
              new LinkedHashSet<>(entries).forEach(values::add);
            });
    return result;
  }

  private static String stableJson(ObjectNode root) throws IOException {
    var printer = new DefaultPrettyPrinter();
    var indenter = new DefaultIndenter("  ", "\n");
    printer.indentObjectsWith(indenter);
    printer.indentArraysWith(indenter);
    return MAPPER.writer(printer).writeValueAsString(root);
  }

  private static void atomicWrite(Path path, String content, AtomicMover atomicMover)
      throws IOException {
    var absolute = path.toAbsolutePath().normalize();
    var parent = absolute.getParent();
    if (parent == null) {
      throw new IOException("baseline path has no parent: " + path);
    }
    Files.createDirectories(parent);
    var temporary = Files.createTempFile(parent, "." + absolute.getFileName(), ".tmp");
    try {
      Files.writeString(temporary, content, StandardCharsets.UTF_8);
      atomicMover.move(temporary, absolute);
    } finally {
      Files.deleteIfExists(temporary);
    }
  }

  private static void moveAtomically(Path source, Path target) throws IOException {
    Files.move(source, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
  }

  /** 原子移动边界；失败时必须把异常返回给 CLI，禁止降级为普通替换。 */
  @FunctionalInterface
  interface AtomicMover {
    void move(Path source, Path target) throws IOException;
  }
}
