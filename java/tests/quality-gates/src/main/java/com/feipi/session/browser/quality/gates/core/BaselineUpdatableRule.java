package com.feipi.session.browser.quality.gates.core;

import java.nio.file.Path;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** 只有显式支持 baseline 维护的规则才实现本接口。 */
public interface BaselineUpdatableRule extends QualityRule {

  /**
   * 生成当前完整 baseline section；规则只返回内容，不直接修改文件。
   *
   * @param context 当前规则收到的全量候选上下文。
   * @return baseline 文件与该规则完整 section。
   * @throws Exception 扫描失败。
   */
  BaselineUpdate baselineUpdate(QualityContext context) throws Exception;

  /**
   * 一条规则生成的 baseline 替换内容。
   *
   * @param path 待维护的仓库内 baseline 文件。
   * @param section 该规则完整 category/entry section。
   */
  record BaselineUpdate(Path path, Map<String, List<String>> section) {

    /** 校验内容并按声明顺序做深层防御性复制。 */
    public BaselineUpdate {
      path = Objects.requireNonNull(path, "path");
      Objects.requireNonNull(section, "section");
      var copied = new LinkedHashMap<String, List<String>>();
      for (var entry : section.entrySet()) {
        if (entry.getKey() == null || entry.getKey().isBlank()) {
          throw new IllegalArgumentException("baseline category must not be blank");
        }
        var values = List.copyOf(Objects.requireNonNull(entry.getValue(), "baseline entries"));
        if (values.stream().anyMatch(Objects::isNull)) {
          throw new IllegalArgumentException("baseline entry must not be null");
        }
        copied.put(entry.getKey(), values);
      }
      section = Collections.unmodifiableMap(copied);
    }
  }
}
