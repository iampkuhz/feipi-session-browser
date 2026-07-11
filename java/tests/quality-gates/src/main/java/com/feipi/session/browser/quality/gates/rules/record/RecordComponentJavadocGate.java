package com.feipi.session.browser.quality.gates.rules.record;

import com.feipi.session.browser.quality.gates.core.QualityGate;
import com.feipi.session.browser.quality.gates.core.QualityGateContext;
import com.feipi.session.browser.quality.gates.core.QualityViolation;
import java.util.List;

/**
 * record component Javadoc 门禁。
 *
 * <p>检查 Java record 是否满足：
 *
 * <ul>
 *   <li>record 有类型 Javadoc。
 *   <li>每个 component 在 Javadoc 中有同名 {@code @param}。
 *   <li>{@code @param} 描述包含中文。
 * </ul>
 *
 * <p>迁移自 {@code scripts/quality/check_java_record_component_javadocs.py}。
 */
public final class RecordComponentJavadocGate implements QualityGate {

  @Override
  public String id() {
    return "record-component-javadocs";
  }

  @Override
  public List<QualityViolation> check(QualityGateContext context) throws Exception {
    return RecordComponentJavadocChecker.check(context);
  }
}
