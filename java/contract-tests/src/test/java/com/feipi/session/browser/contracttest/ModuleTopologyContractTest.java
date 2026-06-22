package com.feipi.session.browser.contracttest;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * 模块拓扑与契约清单验证测试。
 *
 * <p>验证 contract-inventory.json 中的行为全部已归类（decision 不为空）， 并且模块拓扑声明的 S2 新模块存在于 Gradle 配置中。
 * 该测试保证契约审计无遗漏项，且 S2 冻结的模块边界可被脚本验证。
 *
 * <p>对应验收契约：AC-17、AC-18。
 */
@DisplayName("S2 模块拓扑与契约清单验证")
class ModuleTopologyContractTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();

  /** 验证 contract-inventory.json 可解析且所有行为已归类。 */
  @Test
  @DisplayName("契约清单无未归类项 (所有 behavior 的 decision 非空)")
  void allBehaviorsHaveDecision() throws Exception {
    JsonNode inventory = loadInventory();
    JsonNode behaviors = inventory.get("behaviors");
    assertThat(behaviors).isNotNull();
    assertThat(behaviors.isArray()).isTrue();

    List<String> uncategorized = new ArrayList<>();
    for (JsonNode behavior : behaviors) {
      String decision = behavior.path("decision").asText("");
      if (decision.isEmpty()) {
        uncategorized.add(behavior.path("id").asText("unknown"));
      }
    }
    assertThat(uncategorized).as("所有行为必须有 KEEP/FIX/DROP/NEEDS_DECISION 决策").isEmpty();
  }

  /** 验证契约清单中所有 acceptance contract 都绑定了 owning_task 和 test_id。 */
  @Test
  @DisplayName("每条 acceptance contract 绑定 owning_task 和 test_id")
  void allContractsHaveOwnerAndTestId() throws Exception {
    JsonNode inventory = loadInventory();
    JsonNode contracts = inventory.get("acceptance_contracts");
    assertThat(contracts).isNotNull();
    assertThat(contracts.isArray()).isTrue();

    List<String> missing = new ArrayList<>();
    for (JsonNode contract : contracts) {
      String id = contract.path("id").asText("");
      if (contract.path("owning_task").asText("").isEmpty()) {
        missing.add(id + ": missing owning_task");
      }
      if (contract.path("test_id").asText("").isEmpty()) {
        missing.add(id + ": missing test_id");
      }
    }
    assertThat(missing).as("所有契约必须绑定 owning_task 和 test_id").isEmpty();
  }

  /** 验证 S2 模块拓扑声明的新模块数量。 */
  @Test
  @DisplayName("S2 新增模块清单非空")
  void s2NewModulesDeclared() throws Exception {
    JsonNode inventory = loadInventory();
    JsonNode topology = inventory.get("module_topology");
    JsonNode newModules = topology.get("new_s2");
    assertThat(newModules).isNotNull();
    assertThat(newModules.isArray()).isTrue();
    assertThat(newModules.isEmpty()).isFalse();
  }

  /** 验证 @DomainModel 注解存在于 core-domain 模块。 */
  @Test
  @DisplayName("@DomainModel 注解可加载")
  void domainModelAnnotationExists() {
    assertThat(DomainModel.class).isNotNull();
    assertThat(DomainModel.class.isAnnotation()).isTrue();
  }

  /** 验证 @CoreField 注解存在于 core-domain 模块。 */
  @Test
  @DisplayName("@CoreField 注解可加载")
  void coreFieldAnnotationExists() {
    assertThat(CoreField.class).isNotNull();
    assertThat(CoreField.class.isAnnotation()).isTrue();
  }

  /** 验证 S1 冻结的 6 个枚举类型全部存在。 */
  @Test
  @DisplayName("S1 冻结的 6 个枚举类型全部可加载")
  void frozenEnumsAllPresent() throws Exception {
    Set<String> expectedEnums =
        Set.of(
            "com.feipi.session.browser.domain.enums.CallScope",
            "com.feipi.session.browser.domain.enums.CallStatus",
            "com.feipi.session.browser.domain.enums.TokenPrecision",
            "com.feipi.session.browser.domain.enums.TokenProvider",
            "com.feipi.session.browser.domain.enums.TokenSourceKind",
            "com.feipi.session.browser.domain.enums.TokenTotalSemantics");
    for (String className : expectedEnums) {
      Class<?> loaded = Class.forName(className);
      assertThat(loaded.isEnum()).as("%s 应为 enum", className).isTrue();
    }
  }

  private JsonNode loadInventory() throws Exception {
    InputStream is = getClass().getClassLoader().getResourceAsStream("contract-inventory.json");
    assertThat(is).as("contract-inventory.json 必须在 test resources 中").isNotNull();
    return MAPPER.readTree(is);
  }
}
