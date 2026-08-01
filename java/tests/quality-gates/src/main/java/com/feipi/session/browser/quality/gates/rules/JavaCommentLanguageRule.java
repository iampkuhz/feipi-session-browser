package com.feipi.session.browser.quality.gates.rules;

import com.feipi.session.browser.quality.gates.core.QualityContext;
import com.feipi.session.browser.quality.gates.core.QualityRule;
import com.feipi.session.browser.quality.gates.core.QualityViolation;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Pattern;

/** 检查 Java、Kotlin 与 Gradle Kotlin 注释是否以中文说明为主体。 */
public final class JavaCommentLanguageRule implements QualityRule {

  private static final String ID = "java-comment-language";
  private static final Pattern DIRECTIVE =
      Pattern.compile(
          "^(?:SPDX-|Copyright|noinspection|language=|region|endregion|spotless:|formatter:|"
              + "CHECKSTYLE|PMD|ktlint|generated|shellcheck\\b|noqa\\b|type:\\s*ignore\\b|"
              + "pragma:|pylint:|ruff:|fmt:|pyright:|mypy:|isort:|flake8:|coding[:=]|"
              + "-\\*-\\s*coding)",
          Pattern.CASE_INSENSITIVE);
  private static final Pattern LOW_INFORMATION =
      Pattern.compile(
          "\\b(?:TODO|TBD|FIXME|XXX)\\b|待补充|以后补|稍后处理|临时注释|此处保留必要英文术语", Pattern.CASE_INSENSITIVE);
  private static final Pattern URL = Pattern.compile("https?://\\S+");
  private static final Pattern HTML = Pattern.compile("</?[A-Za-z][^>]*>");
  private static final Pattern TAG =
      Pattern.compile(
          "\\{@(?:code|link|linkplain|literal|value)\\s+[^}]*}|"
              + "@(?:param|return|throws|exception|since|see|deprecated)\\b");
  private static final Pattern IDENTIFIER =
      Pattern.compile("`[^`]+`|\\b(?:[A-Za-z_$][\\w$]*\\.)+[A-Za-z_$][\\w$]*\\b");
  private static final Pattern LEADING_MARKER = Pattern.compile("^\\s*\\*?\\s?");
  private static final Pattern WHITESPACE = Pattern.compile("\\s+");

  @Override
  public String id() {
    return ID;
  }

  @Override
  public boolean supportsPath(String relativePath) {
    return relativePath.endsWith(".java")
        || relativePath.endsWith(".kt")
        || relativePath.endsWith(".kts");
  }

  @Override
  public boolean usesChangedFiles() {
    return false;
  }

  @Override
  public List<QualityViolation> check(QualityContext context) throws Exception {
    var policy =
        TechnicalTermsPolicy.load(
            context.repoRoot().resolve("config/technical-terms.json").normalize());
    var violations = new ArrayList<QualityViolation>();
    for (var source : context.repositorySources().sources()) {
      for (var comment : JvmCommentLexer.extract(source.text())) {
        violations.addAll(checkComment(source.relativePath(), comment, policy));
      }
    }
    return List.copyOf(violations);
  }

  private static List<QualityViolation> checkComment(
      String path, JvmCommentLexer.SourceComment comment, TechnicalTermsPolicy policy) {
    var raw = comment.text().strip();
    var first = firstLine(raw);
    if (raw.isEmpty() || DIRECTIVE.matcher(first).find()) {
      return List.of();
    }
    for (var word : policy.forbiddenTranslations()) {
      if (raw.contains(word)) {
        return List.of(
            violation(
                path,
                comment,
                "TECH_TERM_NOT_CANONICAL",
                "技术术语必须使用集中策略中的规范写法，发现“" + word + "”",
                "替换为 config/technical-terms.json 中的 canonical_terms 写法",
                first,
                Map.of("term", word)));
      }
    }
    if (LOW_INFORMATION.matcher(raw).find()) {
      return List.of(
          violation(
              path,
              comment,
              "COMMENT_LOW_INFORMATION",
              "说明包含参数复述、占位语或机械模板",
              "删除简单 helper 的废话；核心接口改写为职责、边界或失败语义",
              first,
              Map.of()));
    }
    var normalized = normalize(raw, policy);
    var hanCount = countHan(normalized);
    var latinCount = countLatin(normalized);
    if (normalized.isEmpty() || hanCount + latinCount == 0) {
      return List.of();
    }
    var ratio = hanCount / (double) Math.max(1, hanCount + latinCount);
    var minHan = comment.kind() == JvmCommentLexer.CommentKind.LINE ? 2 : 4;
    var minRatio = comment.kind() == JvmCommentLexer.CommentKind.LINE ? 0.08 : 0.12;
    var violations = new ArrayList<QualityViolation>();
    if (hanCount < minHan || ratio < minRatio) {
      violations.add(
          violation(
              path,
              comment,
              "COMMENT_NOT_CHINESE_DOMINANT",
              "中文不是说明主体（Han="
                  + hanCount
                  + ", Latin="
                  + latinCount
                  + ", ratio="
                  + String.format(Locale.ROOT, "%.3f", ratio)
                  + "）",
              "使用中文解释职责或约束；仅保留 allowlist 中必要技术术语",
              first,
              Map.of(
                  "hanCount",
                  Integer.toString(hanCount),
                  "latinCount",
                  Integer.toString(latinCount),
                  "ratio",
                  String.format(Locale.ROOT, "%.3f", ratio))));
    }
    if (raw.contains("{@inheritDoc}") && hanCount < 4) {
      violations.add(
          violation(
              path,
              comment,
              "INHERITDOC_WITHOUT_CHINESE",
              "不能只用 inheritDoc 代替中文说明",
              "补充实现边界或失败语义的中文说明",
              first,
              Map.of()));
    }
    return List.copyOf(violations);
  }

  private static QualityViolation violation(
      String path,
      JvmCommentLexer.SourceComment comment,
      String code,
      String message,
      String suggestion,
      String first,
      Map<String, String> details) {
    var attributes = new LinkedHashMap<String, String>();
    attributes.put("kind", comment.kind().name().toLowerCase(Locale.ROOT));
    attributes.put("suggestion", suggestion);
    attributes.put("preview", preview(first));
    attributes.putAll(details);
    return new QualityViolation(ID, path, comment.line(), code, message, attributes);
  }

  private static String normalize(String raw, TechnicalTermsPolicy policy) {
    var lines = new ArrayList<String>();
    for (var line : raw.split("\\R", -1)) {
      var value = LEADING_MARKER.matcher(line).replaceFirst("").strip();
      if (!value.isEmpty() && !DIRECTIVE.matcher(value).find()) {
        lines.add(value);
      }
    }
    var value = String.join(" ", lines);
    value = URL.matcher(value).replaceAll(" ");
    value = HTML.matcher(value).replaceAll(" ");
    value = TAG.matcher(value).replaceAll(" ");
    value = IDENTIFIER.matcher(value).replaceAll(" ");
    var terms =
        policy.canonicalTerms().stream()
            .sorted(
                Comparator.comparingInt(String::length)
                    .reversed()
                    .thenComparing(Comparator.naturalOrder()))
            .toList();
    for (var term : terms) {
      var pattern =
          Pattern.compile(
              "(?<![A-Za-z0-9_])" + Pattern.quote(term) + "(?![A-Za-z0-9_])",
              Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);
      value = pattern.matcher(value).replaceAll(" ");
    }
    return WHITESPACE.matcher(value).replaceAll(" ").strip();
  }

  private static String firstLine(String raw) {
    if (raw.isEmpty()) {
      return "";
    }
    var lines = raw.split("\\R", 2);
    return LEADING_MARKER.matcher(lines[0]).replaceFirst("").strip();
  }

  private static String preview(String value) {
    return value.length() <= 160 ? value : value.substring(0, 160);
  }

  private static int countHan(String value) {
    var count = 0;
    for (var index = 0; index < value.length(); index++) {
      var character = value.charAt(index);
      if ((character >= '\u3400' && character <= '\u4DBF')
          || (character >= '\u4E00' && character <= '\u9FFF')
          || (character >= '\uF900' && character <= '\uFAFF')) {
        count++;
      }
    }
    return count;
  }

  private static int countLatin(String value) {
    var count = 0;
    for (var index = 0; index < value.length(); index++) {
      var character = value.charAt(index);
      if ((character >= 'A' && character <= 'Z') || (character >= 'a' && character <= 'z')) {
        count++;
      }
    }
    return count;
  }
}
