package com.feipi.session.browser.quality.gates.rules;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

/**
 * 读取中文注释规则共用的集中术语策略；不负责解释或修改源码。
 *
 * @param canonicalTerms 允许原样保留的规范技术术语。
 * @param forbiddenTranslations 禁止使用的非规范翻译。
 */
record TechnicalTermsPolicy(Set<String> canonicalTerms, List<String> forbiddenTranslations) {

  private static final ObjectMapper MAPPER =
      new ObjectMapper().enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);

  // 对术语集合做防御性复制，保持策略文件中的稳定顺序。
  TechnicalTermsPolicy {
    canonicalTerms = Set.copyOf(new LinkedHashSet<>(canonicalTerms));
    forbiddenTranslations = List.copyOf(forbiddenTranslations);
  }

  /**
   * 加载并校验策略；文件缺失、JSON 错误或字段类型错误都会向上抛出并让 Gate fail-closed。
   *
   * @param path 集中策略 JSON 路径。
   * @return 已校验的不可变策略。
   * @throws IOException 文件读取或 JSON 解析失败。
   */
  static TechnicalTermsPolicy load(Path path) throws IOException {
    var root = MAPPER.readTree(path.toFile());
    if (root == null || !root.isObject()) {
      throw new IOException("technical terms policy must be a JSON object: " + path);
    }
    var canonical = strings(root.get("canonical_terms"), "canonical_terms", true, path);
    var forbidden =
        strings(root.get("forbidden_translations"), "forbidden_translations", false, path);
    return new TechnicalTermsPolicy(new LinkedHashSet<>(canonical), forbidden);
  }

  private static List<String> strings(JsonNode node, String field, boolean required, Path path)
      throws IOException {
    if (node == null && !required) {
      return List.of();
    }
    if (node == null || !node.isArray() || (required && node.isEmpty())) {
      throw new IOException(
          field + " must be " + (required ? "a non-empty " : "an ") + "array of strings: " + path);
    }
    var values = new ArrayList<String>();
    for (var value : node) {
      if (!value.isTextual() || value.textValue().isBlank()) {
        throw new IOException(field + " must contain non-blank strings: " + path);
      }
      values.add(value.textValue());
    }
    return List.copyOf(values);
  }
}
