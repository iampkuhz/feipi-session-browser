package com.feipi.session.browser.arch;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

import com.tngtech.archunit.base.DescribedPredicate;
import com.tngtech.archunit.core.domain.JavaClass;
import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;
import org.junit.jupiter.api.DisplayName;

/**
 * 验证模块依赖边界的架构测试。
 *
 * <p>确保 {@code core-domain} 不依赖基础设施和展示层关注点。
 */
@AnalyzeClasses(
    packages = "com.feipi.session.browser",
    importOptions = ImportOption.DoNotIncludeTests.class)
@DisplayName("Architecture dependency rules")
final class CoreDomainDependencyTest {

  private CoreDomainDependencyTest() {}

  /** {@code core-domain} 不得依赖 CLI 实现。 */
  @ArchTest
  static final ArchRule coreDomainMustNotDependOnCli =
      noClasses()
          .that()
          .resideInAPackage("..domain..")
          .should()
          .dependOnClassesThat()
          .resideInAPackage("..cli..")
          .as("core-domain must not depend on CLI")
          .allowEmptyShould(true);

  /** 项目内不得存在 {@code package} 循环依赖。 */
  @ArchTest
  static final ArchRule noPackageCycles =
      slices()
          .matching("..(+)..")
          .should()
          .beFreeOfCycles()
          .as("No package cycles should exist")
          .allowEmptyShould(true);

  /** {@code core-domain} 不得依赖 Jackson。 */
  @ArchTest
  static final ArchRule coreDomainMustNotDependOnJackson =
      noClasses()
          .that()
          .resideInAPackage("..domain..")
          .should()
          .dependOnClassesThat()
          .resideInAPackage("com.fasterxml.jackson..")
          .as("core-domain must not depend on Jackson")
          .allowEmptyShould(true);

  /** {@code core-domain} 不得依赖 {@code Gson}。 */
  @ArchTest
  static final ArchRule coreDomainMustNotDependOnGson =
      noClasses()
          .that()
          .resideInAPackage("..domain..")
          .should()
          .dependOnClassesThat()
          .resideInAPackage("com.google.gson..")
          .as("core-domain must not depend on Gson")
          .allowEmptyShould(true);

  /** {@code core-domain} 不得依赖 SQLite。 */
  @ArchTest
  static final ArchRule coreDomainMustNotDependOnSqlite =
      noClasses()
          .that()
          .resideInAPackage("..domain..")
          .should()
          .dependOnClassesThat()
          .resideInAPackage("org.sqlite..")
          .as("core-domain must not depend on SQLite")
          .allowEmptyShould(true);

  /** {@code core-domain} 不得依赖 {@code Web} 框架。 */
  @ArchTest
  static final ArchRule coreDomainMustNotDependOnWeb =
      noClasses()
          .that()
          .resideInAPackage("..domain..")
          .should()
          .dependOnClassesThat()
          .resideInAnyPackage("..web..", "..javalin..", "..pebble..")
          .as("core-domain must not depend on web frameworks")
          .allowEmptyShould(true);

  /** {@code core-domain} 不得依赖 {@code Spring} 或 {@code Jakarta}。 */
  @ArchTest
  static final ArchRule coreDomainMustNotDependOnSpring =
      noClasses()
          .that()
          .resideInAPackage("..domain..")
          .should()
          .dependOnClassesThat()
          .resideInAnyPackage("org.springframework..", "jakarta..")
          .as("core-domain must not depend on Spring or Jakarta")
          .allowEmptyShould(true);

  /** {@code core-domain} 不得依赖 source {@code adapter}（{@code domain} 自身除外）。 */
  @ArchTest
  static final ArchRule coreDomainMustNotDependOnSourceAdapters =
      noClasses()
          .that()
          .resideInAPackage("..domain..")
          .should()
          .dependOnClassesThat()
          .resideInAnyPackage("..adapter..", "..source..")
          .as("core-domain must not depend on source adapters")
          .allowEmptyShould(true);

  /** {@code core-domain} 不得依赖 {@code test} {@code support} 工具。 */
  @ArchTest
  static final ArchRule coreDomainMustNotDependOnTestSupport =
      noClasses()
          .that()
          .resideInAPackage("..domain..")
          .should()
          .dependOnClassesThat()
          .resideInAPackage("..testsupport..")
          .as("core-domain must not depend on test support")
          .allowEmptyShould(true);

  /**
   * {@code core-domain} 不得依赖未经批准的 {@code Lombok} 注解。
   *
   * <p>仅允许编译期注解 {@code @Getter} 和 {@code @RequiredArgsConstructor}。 其他 Lombok 注解由 {@code
   * lombok.config} 和 PMD 规则阻止。
   */
  @ArchTest
  static final ArchRule coreDomainMustNotDependOnUnapprovedLombok =
      noClasses()
          .that()
          .resideInAPackage("..domain..")
          .should()
          .dependOnClassesThat(unapprovedLombokAnnotation())
          .as("core-domain must not depend on Lombok except @Getter and @RequiredArgsConstructor")
          .allowEmptyShould(true);

  /**
   * 返回匹配未批准 Lombok 类的谓词。
   *
   * <p>匹配 {@code lombok..} 包中除 {@code lombok.Getter} 和 {@code lombok.RequiredArgsConstructor}
   * 之外的所有类。
   */
  private static DescribedPredicate<JavaClass> unapprovedLombokAnnotation() {
    return new DescribedPredicate<>("unapproved Lombok annotation") {
      @Override
      public boolean test(JavaClass input) {
        if (!input.getPackageName().startsWith("lombok")) {
          return false;
        }
        String fullName = input.getFullName();
        return !"lombok.Getter".equals(fullName)
            && !"lombok.RequiredArgsConstructor".equals(fullName);
      }
    };
  }
}
