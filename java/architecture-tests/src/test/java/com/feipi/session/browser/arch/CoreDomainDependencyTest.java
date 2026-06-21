package com.feipi.session.browser.arch;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;
import org.junit.jupiter.api.DisplayName;

/**
 * Architecture tests enforcing module dependency boundaries.
 *
 * <p>These rules ensure that core-domain remains independent of infrastructure and presentation
 * concerns.
 */
@AnalyzeClasses(
    packages = "com.feipi.session.browser",
    importOptions = ImportOption.DoNotIncludeTests.class)
@DisplayName("Architecture dependency rules")
final class CoreDomainDependencyTest {

  private CoreDomainDependencyTest() {}

  /** core-domain must not depend on CLI implementation. */
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

  /** No package cycles within the project. */
  @ArchTest
  static final ArchRule noPackageCycles =
      slices()
          .matching("..(+)..")
          .should()
          .beFreeOfCycles()
          .as("No package cycles should exist")
          .allowEmptyShould(true);
}
