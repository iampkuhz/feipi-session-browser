package com.feipi.session.browser.arch;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.fields;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noMethods;

import com.feipi.session.browser.domain.annotation.DomainModel;
import com.tngtech.archunit.core.domain.JavaModifier;
import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;
import org.junit.jupiter.api.DisplayName;

/**
 * 验证领域模型不可变性约束的架构测试。
 *
 * <p>确保 {@code @DomainModel} 标注的类型遵循值语义： 不可变字段、无 setter、正确的类型修饰符。
 */
@AnalyzeClasses(
    packages = "com.feipi.session.browser",
    importOptions = ImportOption.DoNotIncludeTests.class)
@DisplayName("Domain model immutability rules")
final class DomainModelImmutabilityTest {

  private DomainModelImmutabilityTest() {}

  /**
   * 所有 {@code @DomainModel} 标注的类型必须是 record、enum 或不可变类。
   *
   * <p>这确保领域模型具备值语义，防止通过继承引入可变状态。
   */
  @ArchTest
  static final ArchRule domainModelMustBeImmutableType =
      classes()
          .that()
          .areAnnotatedWith(DomainModel.class)
          .should()
          .beRecords()
          .orShould()
          .beEnums()
          .orShould()
          .haveModifier(JavaModifier.FINAL)
          .as("@DomainModel types must be record, enum, or final class")
          .allowEmptyShould(true);

  /**
   * {@code @DomainModel} 类型不得暴露名称以 setter 模式开头的公开方法。
   *
   * <p>setter 方法违反不可变性约束。领域模型的状态变更应通过创建新实例实现。
   */
  @ArchTest
  static final ArchRule domainModelMustNotHaveSetters =
      noMethods()
          .that()
          .areDeclaredInClassesThat()
          .areAnnotatedWith(DomainModel.class)
          .and()
          .haveNameMatching("set.*")
          .should()
          .bePublic()
          .as("@DomainModel types must not have setter methods")
          .allowEmptyShould(true);

  /**
   * {@code @DomainModel} 类型的所有实例字段必须为不可变。
   *
   * <p>非不可变实例字段意味着可变状态，违反领域模型的不可变性约定。
   */
  @ArchTest
  static final ArchRule domainModelFieldsMustBeFinal =
      fields()
          .that()
          .areDeclaredInClassesThat()
          .areAnnotatedWith(DomainModel.class)
          .and()
          .areNotStatic()
          .should()
          .beFinal()
          .as("@DomainModel instance fields must be final")
          .allowEmptyShould(true);
}
