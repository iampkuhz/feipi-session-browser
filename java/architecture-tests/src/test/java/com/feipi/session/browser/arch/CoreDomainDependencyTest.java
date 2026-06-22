package com.feipi.session.browser.arch;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

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

  /** {@code core-domain} 不得依赖 {@code Lombok}。 */
  @ArchTest
  static final ArchRule coreDomainMustNotDependOnLombok =
      noClasses()
          .that()
          .resideInAPackage("..domain..")
          .should()
          .dependOnClassesThat()
          .resideInAPackage("lombok..")
          .as("core-domain must not depend on Lombok")
          .allowEmptyShould(true);
}
