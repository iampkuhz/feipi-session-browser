package com.feipi.session.browser.arch;

import com.sun.source.doctree.DocCommentTree;
import com.sun.source.doctree.DocTree;
import com.sun.source.doctree.ParamTree;
import com.sun.source.doctree.TextTree;
import com.sun.source.tree.AnnotationTree;
import com.sun.source.tree.ClassTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.MethodTree;
import com.sun.source.tree.ModifiersTree;
import com.sun.source.tree.Tree;
import com.sun.source.tree.VariableTree;
import com.sun.source.util.DocTrees;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePath;
import com.sun.source.util.TreeScanner;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.regex.Pattern;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

/**
 * 中文 Javadoc 源码验证器。
 *
 * <p>使用 JDK {@code compiler} API 解析 Java 源文件，验证所有显式类型、方法、构造器、 record 组件、枚举常量和注解元素均有包含中文语义的 Javadoc
 * 文档。
 */
final class ChineseJavadocVerifier {

  /** 已知的既有文件排除列表（J1-010 已修复，保留空列表供后续使用）。 */
  private static final List<String> PRE_EXISTING_EXCLUSIONS = List.of();

  private static final Pattern HAN_PATTERN = Pattern.compile("\\p{IsHan}");

  private final Path sourceRoot;
  private final List<String> failures = new ArrayList<>();

  /**
   * 创建验证器实例。
   *
   * @param sourceRoot 要扫描的 Java 源码根目录
   */
  ChineseJavadocVerifier(Path sourceRoot) {
    this.sourceRoot = sourceRoot;
  }

  /**
   * 执行验证并返回结果。
   *
   * @return 包含所有违规信息的验证结果
   * @throws IOException 如果读取源文件失败
   */
  VerificationResult verify() throws IOException {
    List<Path> javaFiles = findJavaFiles(sourceRoot);
    if (javaFiles.isEmpty()) {
      return VerificationResult.success();
    }

    JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
    StandardJavaFileManager fileManager =
        compiler.getStandardFileManager(null, null, StandardCharsets.UTF_8);
    Iterable<? extends JavaFileObject> compilationUnits =
        fileManager.getJavaFileObjectsFromPaths(javaFiles);

    JavacTask task =
        (JavacTask)
            compiler.getTask(
                null, fileManager, null, List.of("-proc:none"), null, compilationUnits);

    Iterable<? extends CompilationUnitTree> trees = task.parse();
    task.analyze();
    DocTrees docTrees = DocTrees.instance(task);

    for (CompilationUnitTree cu : trees) {
      String filePath = cu.getSourceFile().getName();
      String fileName = filePath.substring(filePath.lastIndexOf('/') + 1);
      if (PRE_EXISTING_EXCLUSIONS.contains(fileName)) {
        continue;
      }
      String sourceContent = readSourceContent(filePath, javaFiles, cu);
      new DocScanner(docTrees, cu, filePath, sourceContent).scan(cu, null);
    }

    if (failures.isEmpty()) {
      return VerificationResult.success();
    }
    return VerificationResult.violations(List.copyOf(failures));
  }

  /** 读取源文件内容，通过 {@code CompilationUnitTree} 的 URI 或文件名匹配。 */
  private static String readSourceContent(
      String filePath, List<Path> javaFiles, CompilationUnitTree cu) {
    // 通过路径匹配（最可靠的方式）
    for (Path p : javaFiles) {
      if (p.toString().equals(filePath)
          || p.toAbsolutePath().toString().equals(filePath)
          || p.getFileName().toString().equals(filePath)) {
        return readStringQuietly(p);
      }
    }
    // 回退：通过 URI 读取
    return readStringQuietly(Path.of(cu.getSourceFile().toUri()));
  }

  private static String readStringQuietly(Path path) {
    try {
      return Files.readString(path, StandardCharsets.UTF_8);
    } catch (IOException e) {
      return "";
    }
  }

  /** 语法树扫描器，遍历所有类型和成员并收集验证失败。 */
  private class DocScanner extends TreeScanner<Void, Void> {

    private final DocTrees docTrees;
    private final CompilationUnitTree compilationUnit;
    private final String filePath;
    private final String sourceContent;

    DocScanner(
        DocTrees docTrees,
        CompilationUnitTree compilationUnit,
        String filePath,
        String sourceContent) {
      this.docTrees = docTrees;
      this.compilationUnit = compilationUnit;
      this.filePath = filePath;
      this.sourceContent = sourceContent;
    }

    @Override
    public Void visitCompilationUnit(CompilationUnitTree node, Void p) {
      for (Tree typeDecl : node.getTypeDecls()) {
        scan(typeDecl, p);
      }
      return null;
    }

    @Override
    public Void visitClass(ClassTree node, Void p) {
      Tree.Kind kind = node.getKind();
      if (kind == Tree.Kind.ANNOTATION_TYPE) {
        scanAnnotationType(node);
        return null;
      }
      if (kind == Tree.Kind.CLASS
          || kind == Tree.Kind.INTERFACE
          || kind == Tree.Kind.ENUM
          || kind == Tree.Kind.RECORD) {
        scanProductionType(node);
      }
      return null;
    }

    private void scanProductionType(ClassTree classTree) {
      String typeName = classTree.getSimpleName().toString();
      checkTypeHasChineseJavadoc(classTree, typeName);

      boolean isEnum = classTree.getKind() == Tree.Kind.ENUM;
      boolean isRecord = classTree.getKind() == Tree.Kind.RECORD;

      DocCommentTree recordDoc = null;
      if (isRecord) {
        recordDoc = getDoc(classTree);
      }

      for (Tree member : classTree.getMembers()) {
        Tree.Kind memberKind = member.getKind();
        if (memberKind == Tree.Kind.CLASS
            || memberKind == Tree.Kind.INTERFACE
            || memberKind == Tree.Kind.ENUM
            || memberKind == Tree.Kind.RECORD
            || memberKind == Tree.Kind.ANNOTATION_TYPE) {
          scan(member, null);
        } else if (memberKind == Tree.Kind.METHOD) {
          MethodTree method = (MethodTree) member;
          if (isStaticMethod(method)) {
            // 静态方法不是构造器，按普通方法检查
            checkMethod(method);
          } else if (isConstructor(method)) {
            if (!isImplicitConstructor(method, classTree)) {
              checkConstructor(method);
            }
          } else {
            checkMethod(method);
          }
        } else if (memberKind == Tree.Kind.VARIABLE) {
          VariableTree var = (VariableTree) member;
          if (isEnum) {
            // 只检查枚举常量，跳过 private 实例字段
            if (var.getModifiers() != null
                && var.getModifiers()
                    .getFlags()
                    .contains(javax.lang.model.element.Modifier.PRIVATE)) {
              continue;
            }
            checkEnumConstantHasChineseJavadoc(var);
          } else if (isRecord) {
            checkRecordComponentParam(var, recordDoc);
          }
        }
      }
    }

    private void scanAnnotationType(ClassTree annotationTree) {
      String typeName = annotationTree.getSimpleName().toString();
      checkTypeHasChineseJavadoc(annotationTree, typeName);

      for (Tree member : annotationTree.getMembers()) {
        if (member.getKind() == Tree.Kind.METHOD) {
          MethodTree method = (MethodTree) member;
          checkAnnotationElementHasChineseJavadoc(method);
        }
      }
    }

    // ---- 验证方法 ----

    private void checkTypeHasChineseJavadoc(ClassTree tree, String name) {
      DocCommentTree doc = getDoc(tree);
      if (doc == null) {
        addFailure("Missing Javadoc for type '%s'", name);
        return;
      }
      String text = fullDocText(doc);
      if (isPlaceholder(text)) {
        addFailure("Placeholder Javadoc for type '%s'", name);
        return;
      }
      if (!containsChinese(text)) {
        addFailure("English-only Javadoc for type '%s'", name);
      }
    }

    private void checkMethod(MethodTree method) {
      String methodName = method.getName().toString();
      DocCommentTree doc = getDoc(method);
      if (doc == null) {
        addFailure("Missing Javadoc for method '%s'", methodName);
        return;
      }
      String text = fullDocText(doc);
      if (isPlaceholder(text)) {
        addFailure("Placeholder Javadoc for method '%s'", methodName);
        return;
      }
      if (hasOverrideAnnotation(method) && isInheritDocOnly(text)) {
        addFailure("{@inheritDoc}-only Javadoc for override method '%s'", methodName);
        return;
      }
      if (!containsChinese(text)) {
        addFailure("English-only Javadoc for method '%s'", methodName);
      }
    }

    private void checkConstructor(MethodTree constructor) {
      String constructorName = constructor.getName().toString();
      DocCommentTree doc = getDoc(constructor);
      if (doc == null) {
        addFailure("Missing Javadoc for constructor '%s'", constructorName);
        return;
      }
      String text = fullDocText(doc);
      if (isPlaceholder(text)) {
        addFailure("Placeholder Javadoc for constructor '%s'", constructorName);
        return;
      }
      if (!containsChinese(text)) {
        addFailure("English-only Javadoc for constructor '%s'", constructorName);
      }
    }

    private void checkRecordComponentParam(VariableTree component, DocCommentTree recordDoc) {
      String componentName = component.getName().toString();
      if (recordDoc == null) {
        addFailure("Record component '%s' missing Chinese @param", componentName);
        return;
      }
      String paramText = getParamText(recordDoc, componentName);
      if (paramText.isEmpty()) {
        addFailure("Record component '%s' missing Chinese @param", componentName);
        return;
      }
      if (!containsChinese(paramText)) {
        addFailure("Record component '%s' has English-only @param", componentName);
      }
    }

    private void checkEnumConstantHasChineseJavadoc(VariableTree enumConstant) {
      String constName = enumConstant.getName().toString();
      DocCommentTree doc = getDoc(enumConstant);
      if (doc == null) {
        addFailure("Missing Javadoc for enum constant '%s'", constName);
        return;
      }
      String text = fullDocText(doc);
      if (isPlaceholder(text)) {
        addFailure("Placeholder Javadoc for enum constant '%s'", constName);
        return;
      }
      if (!containsChinese(text)) {
        addFailure("English-only Javadoc for enum constant '%s'", constName);
      }
    }

    private void checkAnnotationElementHasChineseJavadoc(MethodTree element) {
      String elementName = element.getName().toString();
      DocCommentTree doc = getDoc(element);
      if (doc == null) {
        addFailure("Missing Javadoc for annotation element '%s'", elementName);
        return;
      }
      String text = fullDocText(doc);
      if (isPlaceholder(text)) {
        addFailure("Placeholder Javadoc for annotation element '%s'", elementName);
        return;
      }
      if (!containsChinese(text)) {
        addFailure("English-only Javadoc for annotation element '%s'", elementName);
      }
    }

    // ---- 辅助方法 ----

    private DocCommentTree getDoc(Tree tree) {
      TreePath path = docTrees.getPath(compilationUnit, tree);
      if (path == null) {
        return null;
      }
      return docTrees.getDocCommentTree(path);
    }

    private void addFailure(String format, Object... args) {
      String symbol = String.format(format, args);
      failures.add("FAIL: " + symbol + " in file " + filePath);
    }

    /** 获取 Javadoc 的完整文本（正文与块标签），递归提取 {@code TextTree} 内容。 */
    private static String fullDocText(DocCommentTree doc) {
      StringBuilder sb = new StringBuilder();
      for (DocTree bodyPart : doc.getFullBody()) {
        extractText(sb, bodyPart);
      }
      for (DocTree tag : doc.getBlockTags()) {
        sb.append(' ');
        extractText(sb, tag);
      }
      return sb.toString();
    }

    /** 递归提取 {@code DocTree} 中的文本内容。 */
    private static void extractText(StringBuilder sb, DocTree tree) {
      if (tree instanceof TextTree text) {
        sb.append(text.getBody());
      } else {
        // 非文本节点：通过 toString 获取文本表示并递归处理子节点
        String raw = tree.toString();
        if (raw != null && !raw.isEmpty()) {
          sb.append(raw);
        }
      }
    }

    /** 检测文本是否包含中文字符。 */
    static boolean containsChinese(String text) {
      // 移除行内标签后检查是否包含汉字
      String cleaned = text.replaceAll("\\{@[^}]*\\}", "");
      return HAN_PATTERN.matcher(cleaned).find();
    }

    /** 检测是否为占位内容。 */
    static boolean isPlaceholder(String text) {
      String trimmed = text.strip();
      return trimmed.equals("TODO")
          || trimmed.equals("TBD")
          || trimmed.equals("待补充")
          || trimmed.equals("以后补")
          || trimmed.equalsIgnoreCase("getter")
          || trimmed.equalsIgnoreCase("setter");
    }

    /** 检测文档文本是否只包含继承文档标记，不含任何中文语义。 */
    static boolean isInheritDocOnly(String text) {
      String cleaned = text.replaceAll("\\s+", " ").strip();
      return cleaned.equals("{@inheritDoc}") || cleaned.equals("{@inheritdoc}");
    }

    private static boolean isConstructor(MethodTree method) {
      // 构造器的名称为 <init>，或者名称与外层类同名
      // 使用名称匹配比返回类型为空检查更可靠
      return "<init>".equals(method.getName().toString());
    }

    /**
     * 判断构造器是否为编译器隐式生成的默认构造器。 对于 record，canonical 构造器（与 record header 签名相同）视为隐式。 对于普通
     * class，通过源码中是否包含 "类名(" 来判断。 对于 enum，隐式构造器参数数为 0。
     */
    private boolean isImplicitConstructor(MethodTree ctor, ClassTree enclosingClass) {
      boolean isEnum = enclosingClass.getKind() == Tree.Kind.ENUM;
      boolean isRecord = enclosingClass.getKind() == Tree.Kind.RECORD;

      if (isEnum) {
        // 枚举隐式构造器：无参数、private。显式声明的构造器至少有 1 个参数。
        return ctor.getParameters().isEmpty();
      }

      if (isRecord) {
        // Record 的规范构造器是隐式的，除非显式重新声明
        // 通过比较参数数量：规范构造器参数数 = record 组件数
        int componentCount = 0;
        for (Tree member : enclosingClass.getMembers()) {
          if (member.getKind() == Tree.Kind.VARIABLE) {
            VariableTree v = (VariableTree) member;
            if (v.getModifiers() != null
                && v.getModifiers().getFlags().contains(javax.lang.model.element.Modifier.FINAL)
                && !v.getModifiers()
                    .getFlags()
                    .contains(javax.lang.model.element.Modifier.STATIC)) {
              componentCount++;
            }
          }
        }
        int ctorParamCount = ctor.getParameters().size();
        // 如果参数数不匹配 record 组件数，则是显式自定义构造器
        if (ctorParamCount != componentCount) {
          return false;
        }
        // 参数数匹配，检查 record 头后是否有紧凑构造器声明。
        // 紧凑构造器特征：类名 + 可选空白 + "{"（而非 "("）。
        String className = enclosingClass.getSimpleName().toString();
        String recordHeaderPattern = "record\\s+" + className + "\\s*\\([^)]*\\)";
        String sourceAfterHeader = sourceContent.replaceFirst(recordHeaderPattern, "");
        java.util.regex.Pattern compactCtorPattern =
            java.util.regex.Pattern.compile(
                "\\b" + java.util.regex.Pattern.quote(className) + "\\s*\\{");
        return !compactCtorPattern.matcher(sourceAfterHeader).find();
      }

      String className = enclosingClass.getSimpleName().toString();
      return !sourceContent.contains(className + "(");
    }

    private static boolean hasOverrideAnnotation(MethodTree method) {
      ModifiersTree mods = method.getModifiers();
      if (mods == null) {
        return false;
      }
      for (AnnotationTree ann : mods.getAnnotations()) {
        if (ann.getAnnotationType().getKind() == Tree.Kind.IDENTIFIER) {
          String name = ann.getAnnotationType().toString();
          if ("Override".equals(name)) {
            return true;
          }
        }
      }
      return false;
    }

    /** 判断方法是否为 static 方法（用于区分工厂方法与构造器）。 */
    private static boolean isStaticMethod(MethodTree method) {
      ModifiersTree mods = method.getModifiers();
      if (mods == null) {
        return false;
      }
      return mods.getFlags().contains(javax.lang.model.element.Modifier.STATIC);
    }

    private static String getParamText(DocCommentTree doc, String paramName) {
      StringBuilder sb = new StringBuilder();
      for (DocTree tag : doc.getBlockTags()) {
        if (tag.getKind() == DocTree.Kind.PARAM) {
          ParamTree param = (ParamTree) tag;
          if (param.getName().getName().contentEquals(paramName)) {
            for (DocTree desc : param.getDescription()) {
              extractText(sb, desc);
            }
          }
        }
      }
      return sb.toString();
    }
  }

  private static List<Path> findJavaFiles(Path root) throws IOException {
    if (!Files.isDirectory(root)) {
      return Collections.emptyList();
    }
    List<Path> result = new ArrayList<>();
    Files.walkFileTree(
        root,
        new SimpleFileVisitor<>() {
          @Override
          public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
            if (file.getFileName().toString().endsWith(".java")) {
              result.add(file);
            }
            return FileVisitResult.CONTINUE;
          }
        });
    return result;
  }

  record VerificationResult(boolean passed, List<String> failures) {

    static VerificationResult success() {
      return new VerificationResult(true, Collections.emptyList());
    }

    static VerificationResult violations(List<String> failures) {
      return new VerificationResult(false, List.copyOf(failures));
    }
  }
}
