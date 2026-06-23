package com.feipi.session.browser.reuse.analyzer;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.reuse.analyzer.model.Ownership;
import org.junit.jupiter.api.Test;
import spoon.Launcher;
import spoon.reflect.declaration.CtMethod;
import spoon.reflect.declaration.CtType;
import spoon.support.compiler.VirtualFile;

/** 验证方法的归属分类器，覆盖六种分类模式。 包括：所有者绑定、独立行为、简单委托、工厂方法等。 */
class OwnershipClassifierTest {

  @Test
  void classifyOwnerBoundAccessesInstanceField() {
    String source =
        """
                package test;
                public class Owner {
                    private int counter;
                    public int getCount() {
                        return this.counter;
                    }
                }
                """;
    CtMethod<?> method = buildMethod(source, "getCount");
    Ownership result = OwnershipClassifier.classify(method);
    // 访问 instance field → OWNER_BOUND（虽然是 getter 但访问了 field）
    assertThat(result).isEqualTo(Ownership.OWNER_BOUND);
  }

  @Test
  void classifyDetachedBehaviorUsesOnlyParams() {
    String source =
        """
                package test;
                public class Detached {
                    public int add(int a, int b) {
                        return a + b;
                    }
                }
                """;
    CtMethod<?> method = buildMethod(source, "add");
    Ownership result = OwnershipClassifier.classify(method);
    assertThat(result).isEqualTo(Ownership.DETACHED_BEHAVIOR);
  }

  @Test
  void classifyTrivialDelegationSingleReturn() {
    String source =
        """
                package test;
                import java.util.List;
                public class Delegator {
                    private List<String> items;
                    public int size() {
                        return items.size();
                    }
                }
                """;
    CtMethod<?> method = buildMethod(source, "size");
    Ownership result = OwnershipClassifier.classify(method);
    assertThat(result).isEqualTo(Ownership.TRIVIAL_DELEGATION);
  }

  @Test
  void classifyFactoryOrConstructorReturnsOwnerType() {
    String source =
        """
                package test;
                public class MyFactory {
                    public static MyFactory create() {
                        return new MyFactory();
                    }
                }
                """;
    CtMethod<?> method = buildMethod(source, "create");
    Ownership result = OwnershipClassifier.classify(method);
    assertThat(result).isEqualTo(Ownership.FACTORY_OR_CONSTRUCTOR);
  }

  @Test
  void classifyProviderSpecificUsesExternalApi() {
    String source =
        """
                package test;
                public class Provider {
                    public String format(Object obj) {
                        return java.util.Objects.toString(obj);
                    }
                }
                """;
    CtMethod<?> method = buildMethod(source, "format");
    Ownership result = OwnershipClassifier.classify(method);
    // Objects.toString 是 JDK API，不使用 owner field → DETACHED_BEHAVIOR
    assertThat(result).isEqualTo(Ownership.DETACHED_BEHAVIOR);
  }

  private CtMethod<?> buildMethod(String source, String methodName) {
    Launcher launcher = new Launcher();
    launcher.getEnvironment().setComplianceLevel(21);
    launcher.getEnvironment().setNoClasspath(true);
    launcher.getEnvironment().setCommentEnabled(false);
    launcher.getEnvironment().setShouldCompile(false);
    launcher.addInputResource(new VirtualFile(source, "Test.java"));
    launcher.buildModel();
    CtType<?> type = launcher.getModel().getAllTypes().stream().findFirst().orElseThrow();
    return type.getMethods().stream()
        .filter(m -> m.getSimpleName().equals(methodName))
        .findFirst()
        .orElseThrow(() -> new AssertionError("Method not found: " + methodName));
  }
}
