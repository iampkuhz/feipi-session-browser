# 质量门禁修复规约

## 原则

1. **质量门禁失败 = 必须阻断提交**，除非失败项已确认与本次变更无关且已有修复方案。
2. **人工确认优先**：任何质量门禁失败的修复方案，必须先呈现给用户，获得明确确认后方可执行。
3. **基线隔离**：修复前必须先验证失败项是否为预存问题（在变更前就已存在）。

## 修复流程

### Step 1: 分类失败项

对每个失败的 gate 执行基线对比：

```bash
# 1. 暂存当前变更
git stash

# 2. 运行质量门禁获取基线
python3 scripts/quality/run_quality_gate.py --target <target> --change-id baseline-<date>

# 3. 恢复变更
git stash pop

# 4. 对比基线与当前结果
```

- **预存失败**：基线与当前结果一致 → 非本次引入，可记录后处理
- **新增失败**：当前结果比基线更差 → 必须修复后才能继续

### Step 2: 制定修复方案

对每个预存失败项，列出：

| 字段 | 说明 |
|---|---|
| Gate 名称 | 如 `staticCssContract`、`browserLayout` |
| 失败原因 | 具体错误信息 |
| 根因 | 预存问题的根本原因 |
| 修复方案 | 具体要改的文件和改动 |
| 风险评估 | 修复可能带来的副作用 |
| 是否阻塞 | 该修复是否阻塞当前变更的提交 |

### Step 3: 用户确认

将修复方案呈现给用户，格式如下：

```
## 质量门禁修复方案

### Gate: staticCssContract
- 失败原因: ...
- 根因: ...
- 修复方案: ...
- 风险评估: ...
- 是否阻塞当前变更: 否
```

**用户未确认前，不得执行任何修复操作。**

### Step 4: 执行修复

用户确认后：

1. 按方案逐一修复
2. 每次修复后重新运行质量门禁
3. 确认修复项从 `blockingFailures` 中移除
4. 全部修复完成后，质量门禁必须 PASS

## 紧急绕过

极少数情况下需要紧急绕过质量门禁：

```bash
FEIPI_SKIP_STOP_HOOK=1
```

**使用条件**：
- 质量门禁基础设施本身有问题（如依赖缺失、环境异常）
- 预存失败项过多，短期内无法全部修复
- 必须记录为什么使用绕过，并在后续补修

## Gate 分类速查

### session-detail target

| Gate | 类型 | 失败常见原因 |
|---|---|---|
| pythonCompile | 编译 | Python 语法错误 |
| templateContract | 模板 | Jinja2 语法/引用错误 |
| staticCssContract | 静态 | `!important`、`position: fixed`、`eval()`、`innerHTML` |
| browserLayout | 浏览器 | Playwright 测试失败 |
| pytest | 单元 | 测试用例失败或缺失 |
