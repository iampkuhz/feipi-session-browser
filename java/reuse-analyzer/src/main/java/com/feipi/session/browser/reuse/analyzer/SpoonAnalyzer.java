package com.feipi.session.browser.reuse.analyzer;

import java.io.File;
import java.util.Collection;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import spoon.Launcher;
import spoon.reflect.CtModel;
import spoon.reflect.declaration.CtMethod;
import spoon.reflect.declaration.CtType;
import spoon.support.compiler.VirtualFile;

/**
 * 基于 Spoon 的 AST 模型构建器。
 *
 * <p>配置约束（required 模式）：
 *
 * <ul>
 *   <li>complianceLevel = 21（Spoon 11.x 支持的最大 Java 合规级别；仓库代码不使用 Java 22+ 特有语法）
 *   <li>noClasspath = true（Spoon 11.x 的 JDT 前端不运行注解处理器，无法解析 Lombok 编译期生成的 构造器和访问器；放宽到 noClasspath
 *       模式以容忍这些生成代码）
 *   <li>commentsEnabled = false
 *   <li>仅 buildModel()，不调用 launcher.run() 或 prettyprint()
 *   <li>不做 source output
 * </ul>
 */
public final class SpoonAnalyzer {

  private static final Logger LOG = LoggerFactory.getLogger(SpoonAnalyzer.class);

  /**
   * Spoon 支持的最大 Java 合规级别。
   *
   * <p>Spoon 11.x 底层使用 Eclipse JDT，当前最高支持到 Java 21。 仓库源码不使用 Java 22+ 特有语法（如 string template、module
   * import）， 因此降级到 21 不影响 AST 分析正确性。
   */
  private static final int COMPLIANCE_LEVEL = 21;

  private SpoonAnalyzer() {}

  /**
   * 构建 Spoon 模型。
   *
   * @param sourceRoots production source 目录列表
   * @param classpath compile classpath 元素列表
   * @return 构建后的 CtModel
   */
  public static CtModel buildModel(List<File> sourceRoots, List<String> classpath) {
    Launcher launcher = new Launcher();
    launcher.getEnvironment().setComplianceLevel(COMPLIANCE_LEVEL);
    launcher.getEnvironment().setNoClasspath(true);
    launcher.getEnvironment().setCommentEnabled(false);
    launcher.getEnvironment().setShouldCompile(false);

    for (File sourceRoot : sourceRoots) {
      if (sourceRoot.exists() && sourceRoot.isDirectory()) {
        launcher.addInputResource(sourceRoot.getAbsolutePath());
      }
    }

    if (classpath != null && !classpath.isEmpty()) {
      launcher.getEnvironment().setSourceClasspath(classpath.toArray(new String[0]));
    }

    launcher.buildModel();

    LOG.info("Spoon 模型构建完成：{} 个类型", launcher.getModel().getAllTypes().size());
    return launcher.getModel();
  }

  /**
   * 从内存中的源码字符串构建模型（用于测试和自测）。
   *
   * @param sources 源码名称和内容的映射
   * @param classpath compile classpath
   * @return 构建后的 CtModel
   */
  public static CtModel buildModelFromSources(List<VirtualFile> sources, List<String> classpath) {
    Launcher launcher = new Launcher();
    launcher.getEnvironment().setComplianceLevel(COMPLIANCE_LEVEL);
    launcher.getEnvironment().setNoClasspath(true);
    launcher.getEnvironment().setCommentEnabled(false);
    launcher.getEnvironment().setShouldCompile(false);

    for (VirtualFile source : sources) {
      launcher.addInputResource(source);
    }

    if (classpath != null && !classpath.isEmpty()) {
      launcher.getEnvironment().setSourceClasspath(classpath.toArray(new String[0]));
    }

    launcher.buildModel();

    return launcher.getModel();
  }

  /** 获取模型中所有类型。 */
  public static Collection<CtType<?>> getAllTypes(CtModel model) {
    return model.getAllTypes();
  }

  /** 获取类型中所有方法（包括嵌套类的）。 */
  public static List<CtMethod<?>> getAllMethods(CtType<?> type) {
    return type.getMethods().stream().toList();
  }

  /** Spoon 分析异常。 当模型构建失败时抛出。 */
  public static final class SpoonAnalysisException extends RuntimeException {
    private static final long serialVersionUID = 1L;

    /** 创建 Spoon 分析异常（仅含消息）。 */
    public SpoonAnalysisException(String message) {
      super(message);
    }

    /** 创建 Spoon 分析异常（含消息和原因）。 */
    public SpoonAnalysisException(String message, Throwable cause) {
      super(message, cause);
    }
  }
}
