package com.feipi.session.browser.arch;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes;

import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;
import org.junit.jupiter.api.DisplayName;

/**
 * 验证领域注解放置位置的架构测试。
 *
 * <p>{@code @DomainModel} 和 {@code @CoreField} 必须位于 {@code ..annotation..} 包中，
 * 确保领域注解的命名空间清晰且与业务类型分离。
 */
@AnalyzeClasses(
    packages = "com.feipi.session.browser",
    importOptions = ImportOption.DoNotIncludeTests.class)
@DisplayName("Domain annotation placement rules")
final class DomainAnnotationRulesTest {

  private DomainAnnotationRulesTest() {}

  /**
   * {@code @DomainModel} 和 {@code @CoreField} 注解类型本身必须位于 {@code ..annotation..} 包中。
   *
   * <p>通过全限定名匹配注解类型本身，确保注解定义位置正确。
   */
  @ArchTest
  static final ArchRule domainAnnotationsMustBeInAnnotationPackage =
      classes()
          .that()
          .haveFullyQualifiedName("com.feipi.session.browser.domain.annotation.DomainModel")
          .or()
          .haveFullyQualifiedName("com.feipi.session.browser.domain.annotation.CoreField")
          .should()
          .resideInAPackage("..annotation..")
          .as("Domain annotations must reside in ..annotation.. package")
          .allowEmptyShould(true);
}
