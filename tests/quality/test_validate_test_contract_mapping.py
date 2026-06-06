"""测试契约映射校验脚本的单元测试。

针对 scripts/quality/validate_test_contract_mapping.py 中的核心解析和校验函数。
"""
import pytest
import sys
from pathlib import Path

pytestmark = pytest.mark.contract_case("HOOK-HARNESS-013")

# 导入脚本中的内部函数
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "quality"
sys.path.insert(0, str(SCRIPT_DIR))

from validate_test_contract_mapping import (
    _parse_md_features,
    _parse_pytest_markers,
    _parse_playwright_ids,
    _validate,
)


# ===========================================================================
# 场景 1：能解析 md 表格
# ===========================================================================

class TestParseMarkdownTable:
    """验证 _parse_md_features 能正确解析 Markdown 契约用例表格。"""

    def test_parse_single_case(self, tmp_path: Path):
        """单行用例表格应正确提取所有字段。"""
        md_content = """# 会话列表

| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |
|---|---|---|---|---|---|---|---|---|
| UI-SESSIONS-001 | P0 | UI | 正常加载会话列表 | 打开页面检查列表渲染 | 列表非空 | pytest, screenshot | snapshot 更新 | `src/session_browser/web/static/js/sessions.js` |
"""
        features_dir = tmp_path / "features"
        features_dir.mkdir()
        (features_dir / "sessions.md").write_text(md_content, encoding="utf-8")

        cases, duplicates = _parse_md_features(features_dir)

        assert len(cases) == 1
        case = cases["UI-SESSIONS-001"]
        assert case["priority"] == "P0"
        assert case["layer"] == "UI"
        assert "会话列表" in case["scenario"]
        assert case["test_type"] == "pytest, screenshot"
        assert "snapshot 更新" in case["related_check"]
        assert "sessions.js" in case["code_location"]
        assert duplicates == []

    def test_parse_multiple_files(self, tmp_path: Path):
        """多个 md 文件的用例应合并。"""
        features_dir = tmp_path / "features"
        features_dir.mkdir()

        (features_dir / "feature_a.md").write_text(
            "| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |\n"
            "|---|---|---|---|---|---|---|---|---|\n"
            "| FA-001 | P0 | API | 测试 A | 调用接口 | 状态码 200 | pytest | — | `tests/test_a.py` |\n",
            encoding="utf-8",
        )
        (features_dir / "feature_b.md").write_text(
            "| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |\n"
            "|---|---|---|---|---|---|---|---|---|\n"
            "| FB-001 | P1 | UI | 测试 B | 点击按钮 | 弹窗出现 | playwright | — | `tests/playwright/test_b.ts` |\n",
            encoding="utf-8",
        )

        cases, duplicates = _parse_md_features(features_dir)

        assert len(cases) == 2
        assert "FA-001" in cases
        assert "FB-001" in cases
        assert cases["FA-001"]["source_file"] == "feature_a.md"
        assert cases["FB-001"]["source_file"] == "feature_b.md"

    def test_parse_skips_non_table_lines(self, tmp_path: Path):
        """非表格行（标题、正文等）应被忽略。"""
        md_content = """# 验收契约

这是一段描述文本，不是表格。

下面是一个空表头但没有数据行：

| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |
|---|---|---|---|---|---|---|---|---|
"""
        features_dir = tmp_path / "features"
        features_dir.mkdir()
        (features_dir / "empty.md").write_text(md_content, encoding="utf-8")

        cases, duplicates = _parse_md_features(features_dir)

        assert len(cases) == 0


# ===========================================================================
# 场景 2：能解析 pytest marker
# ===========================================================================

class TestParsePytestMarker:
    """验证 _parse_pytest_markers 能正确提取 @pytest.mark.contract_case 中的契约 ID。"""

    def test_extract_single_id(self, tmp_path: Path):
        """单 ID marker（标记）应正确提取。"""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_session.py").write_text(
            'import pytest\n\n'
            '@pytest.mark.contract_case("UI-SESSIONS-001")\n'
            "def test_session_list():\n"
            "    pass\n",
            encoding="utf-8",
        )

        bindings = _parse_pytest_markers(tests_dir)

        assert "UI-SESSIONS-001" in bindings
        assert bindings["UI-SESSIONS-001"]["type"] == "pytest"
        assert len(bindings["UI-SESSIONS-001"]["files"]) == 1

    def test_extract_multiple_ids(self, tmp_path: Path):
        """一个标记含多个 ID 应全部提取。"""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_multi.py").write_text(
            'import pytest\n\n'
            '@pytest.mark.contract_case("FA-001", "FA-002", "FB-003")\n'
            "def test_multi():\n"
            "    pass\n",
            encoding="utf-8",
        )

        bindings = _parse_pytest_markers(tests_dir)

        assert len(bindings) == 3
        assert "FA-001" in bindings
        assert "FA-002" in bindings
        assert "FB-003" in bindings

    def test_multiple_files_same_id(self, tmp_path: Path):
        """同一 ID 在多个文件中绑定，文件列表应合并。"""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_a.py").write_text(
            '@pytest.mark.contract_case("SHARED-001")\n'
            "def test_a(): pass\n",
            encoding="utf-8",
        )
        (tests_dir / "test_b.py").write_text(
            '@pytest.mark.contract_case("SHARED-001")\n'
            "def test_b(): pass\n",
            encoding="utf-8",
        )

        bindings = _parse_pytest_markers(tests_dir)

        assert len(bindings["SHARED-001"]["files"]) == 2

    def test_extract_module_level_pytestmark(self, tmp_path: Path):
        """模块级 pytestmark 绑定应被识别，避免同一测试文件重复贴相同 ID。"""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_quality_gate.py").write_text(
            "import pytest\n\n"
            'pytestmark = pytest.mark.contract_case("HOOK-HARNESS-013")\n\n'
            "def test_quality_gate_contract():\n"
            "    pass\n",
            encoding="utf-8",
        )

        bindings = _parse_pytest_markers(tests_dir)

        assert "HOOK-HARNESS-013" in bindings
        assert bindings["HOOK-HARNESS-013"]["type"] == "pytest"
        assert bindings["HOOK-HARNESS-013"]["files"] == ["tests/test_quality_gate.py"]

    def test_skips_pycache(self, tmp_path: Path):
        """__pycache__ 目录下的 .py 文件应被跳过。"""
        tests_dir = tmp_path / "tests"
        pycache = tests_dir / "__pycache__"
        pycache.mkdir(parents=True)
        (pycache / "test_cached.cpython-312.pyc").write_text(
            '@pytest.mark.contract_case("SHOULD-NOT-APPEAR-001")\n',
            encoding="utf-8",
        )

        bindings = _parse_pytest_markers(tests_dir)

        assert "SHOULD-NOT-APPEAR-001" not in bindings

    def test_no_pytest_files(self, tmp_path: Path):
        """没有 .py 文件时返回空字典。"""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        bindings = _parse_pytest_markers(tests_dir)

        assert bindings == {}


# ===========================================================================
# 场景 3：能解析 Playwright 标题 ID
# ===========================================================================

class TestParsePlaywrightIds:
    """验证 _parse_playwright_ids 能正确提取 test('...') 标题中的契约 ID。"""

    def test_extract_single_id(self, tmp_path: Path):
        """单 ID 标题应正确提取。"""
        tests_dir = tmp_path / "tests"
        pw_dir = tests_dir / "playwright"
        pw_dir.mkdir(parents=True)
        (pw_dir / "sessions.spec.ts").write_text(
            "import { test } from '@playwright/test';\n\n"
            "test('[UI-SESSIONS-001] 正常加载会话列表', async ({ page }) => {\n"
            "    // ...\n"
            "});\n",
            encoding="utf-8",
        )

        bindings = _parse_playwright_ids(tests_dir)

        assert "UI-SESSIONS-001" in bindings
        assert bindings["UI-SESSIONS-001"]["type"] == "playwright"
        assert len(bindings["UI-SESSIONS-001"]["files"]) == 1

    def test_extract_js_file(self, tmp_path: Path):
        """JS 文件（非 TS）也应被解析。"""
        tests_dir = tmp_path / "tests"
        pw_dir = tests_dir / "playwright"
        pw_dir.mkdir(parents=True)
        (pw_dir / "login.spec.js").write_text(
            "test('[AUTH-LOGIN-001] 用户登录流程', async () => {\n"
            "    // ...\n"
            "});\n",
            encoding="utf-8",
        )

        bindings = _parse_playwright_ids(tests_dir)

        assert "AUTH-LOGIN-001" in bindings

    def test_non_js_ts_ignored(self, tmp_path: Path):
        """非 .js/.ts 文件应被忽略。"""
        tests_dir = tmp_path / "tests"
        pw_dir = tests_dir / "playwright"
        pw_dir.mkdir(parents=True)
        (pw_dir / "config.json").write_text(
            '{"testId": "[SHOULD-NOT-APPEAR-001]"}',
            encoding="utf-8",
        )

        bindings = _parse_playwright_ids(tests_dir)

        assert len(bindings) == 0

    def test_no_playwright_dir(self, tmp_path: Path):
        """不存在 playwright 子目录时返回空字典。"""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        bindings = _parse_playwright_ids(tests_dir)

        assert bindings == {}

    def test_multiple_ids_in_same_file(self, tmp_path: Path):
        """同一文件中多个 test 调用应全部提取。"""
        tests_dir = tmp_path / "tests"
        pw_dir = tests_dir / "playwright"
        pw_dir.mkdir(parents=True)
        (pw_dir / "multi.spec.ts").write_text(
            "test('[A-001] 第一个用例', async () => {});\n"
            "test('[A-002] 第二个用例', async () => {});\n",
            encoding="utf-8",
        )

        bindings = _parse_playwright_ids(tests_dir)

        assert len(bindings) == 2
        assert "A-001" in bindings
        assert "A-002" in bindings


# ===========================================================================
# 场景 4：能发现 md 有但代码无（missing_in_code）
# ===========================================================================

class TestMissingInCode:
    """验证 _validate 能报告 MD 中定义但代码中未绑定的 P0/P1 用例。"""

    def _make_helper(self, tmp_path: Path, md_cases: dict, code_bindings: dict, duplicates: list | None = None):
        """辅助方法：构建 repo_root 并调用 _validate。"""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        return _validate(md_cases, code_bindings, duplicates or [], repo_root)

    def test_p0_missing_in_code(self, tmp_path: Path):
        """P0 用例无代码绑定时应报告 代码中缺失。"""
        md_cases = {
            "UI-SESSIONS-001": {
                "priority": "P0",
                "layer": "UI",
                "scenario": "加载列表",
                "how": "打开页面",
                "assertions": "列表非空",
                "test_type": "pytest",
                "related_check": "—",
                "code_location": "—",
                "source_file": "sessions.md",
            }
        }
        code_bindings = {}

        errors = self._make_helper(tmp_path, md_cases, code_bindings)

        missing = [e for e in errors if e["type"] == "missing_in_code"]
        assert len(missing) == 1
        assert missing[0]["id"] == "UI-SESSIONS-001"
        assert missing[0]["priority"] == "P0"

    def test_p1_missing_in_code(self, tmp_path: Path):
        """P1 用例无代码绑定时也应报告 missing_in_code。"""
        md_cases = {
            "UI-SESSIONS-002": {
                "priority": "P1",
                "layer": "UI",
                "scenario": "过滤会话",
                "how": "输入过滤条件",
                "assertions": "列表已过滤",
                "test_type": "playwright",
                "related_check": "—",
                "code_location": "—",
                "source_file": "sessions.md",
            }
        }
        code_bindings = {}

        errors = self._make_helper(tmp_path, md_cases, code_bindings)

        missing = [e for e in errors if e["type"] == "missing_in_code"]
        assert len(missing) == 1
        assert missing[0]["id"] == "UI-SESSIONS-002"

    def test_p2_missing_not_reported(self, tmp_path: Path):
        """P2 用例无代码绑定时不应报告 missing_in_code。"""
        md_cases = {
            "UI-SESSIONS-099": {
                "priority": "P2",
                "layer": "UI",
                "scenario": "边缘场景",
                "how": "手动操作",
                "assertions": "正常",
                "test_type": "manual",
                "related_check": "—",
                "code_location": "—",
                "source_file": "sessions.md",
            }
        }
        code_bindings = {}

        errors = self._make_helper(tmp_path, md_cases, code_bindings)

        missing = [e for e in errors if e["type"] == "missing_in_code"]
        assert len(missing) == 0

    def test_p0_bound_no_error(self, tmp_path: Path):
        """P0 用例已绑定代码时不应报告 missing_in_code。"""
        md_cases = {
            "UI-SESSIONS-001": {
                "priority": "P0",
                "layer": "UI",
                "scenario": "加载列表",
                "how": "打开页面",
                "assertions": "列表非空",
                "test_type": "pytest",
                "related_check": "—",
                "code_location": "—",
                "source_file": "sessions.md",
            }
        }
        code_bindings = {
            "UI-SESSIONS-001": {"files": ["tests/test_sessions.py"], "type": "pytest"}
        }

        errors = self._make_helper(tmp_path, md_cases, code_bindings)

        missing = [e for e in errors if e["type"] == "missing_in_code"]
        assert len(missing) == 0


# ===========================================================================
# 场景 5：能发现代码有但 md 无（orphan_in_code）
# ===========================================================================

class TestOrphanInCode:
    """验证 _validate 能报告代码中绑定但 MD 中未定义的 ID。"""

    def _make_helper(self, tmp_path: Path, md_cases: dict, code_bindings: dict, duplicates: list | None = None):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        return _validate(md_cases, code_bindings, duplicates or [], repo_root)

    def test_orphan_pytest(self, tmp_path: Path):
        """代码中绑定了 MD 中没有的 ID 应报告 orphan_in_code。"""
        md_cases: dict = {}
        code_bindings = {
            "ORPHAN-001": {"files": ["tests/test_orphan.py"], "type": "pytest"}
        }

        errors = self._make_helper(tmp_path, md_cases, code_bindings)

        orphans = [e for e in errors if e["type"] == "orphan_in_code"]
        assert len(orphans) == 1
        assert orphans[0]["id"] == "ORPHAN-001"
        assert "test_orphan.py" in orphans[0]["message"]

    def test_orphan_playwright(self, tmp_path: Path):
        """Playwright 绑定的孤立 ID 也应报告。"""
        md_cases: dict = {}
        code_bindings = {
            "ORPHAN-PW-001": {"files": ["tests/playwright/orphan.spec.ts"], "type": "playwright"}
        }

        errors = self._make_helper(tmp_path, md_cases, code_bindings)

        orphans = [e for e in errors if e["type"] == "orphan_in_code"]
        assert len(orphans) == 1
        assert orphans[0]["id"] == "ORPHAN-PW-001"

    def test_no_orphan_when_defined(self, tmp_path: Path):
        """代码绑定的 ID 在 MD 中已定义时不应报告 orphan。"""
        md_cases = {
            "DEFINED-001": {
                "priority": "P0",
                "layer": "UI",
                "scenario": "测试",
                "how": "自动",
                "assertions": "通过",
                "test_type": "pytest",
                "related_check": "—",
                "code_location": "—",
                "source_file": "test.md",
            }
        }
        code_bindings = {
            "DEFINED-001": {"files": ["tests/test_defined.py"], "type": "pytest"}
        }

        errors = self._make_helper(tmp_path, md_cases, code_bindings)

        orphans = [e for e in errors if e["type"] == "orphan_in_code"]
        assert len(orphans) == 0


# ===========================================================================
# 场景 6：能发现重复 ID
# ===========================================================================

class TestDuplicateIds:
    """验证 _validate 能报告 MD 表格中重复的契约 ID。"""

    def _make_helper(self, tmp_path: Path, md_cases: dict, code_bindings: dict, duplicates: list):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        return _validate(md_cases, code_bindings, duplicates, repo_root)

    def test_duplicate_in_md(self, tmp_path: Path):
        """同一 ID 在 md 中出现两次应报告 duplicate_in_md。"""
        md_cases = {
            "DUP-001": {
                "priority": "P0",
                "layer": "UI",
                "scenario": "第一次定义",
                "how": "自动",
                "assertions": "通过",
                "test_type": "pytest",
                "related_check": "—",
                "code_location": "—",
                "source_file": "a.md",
            }
        }
        # _parse_md_features 遇到重复时保留后出现的，duplicates 记录重复的 ID
        duplicates = ["DUP-001"]
        code_bindings: dict = {}

        errors = self._make_helper(tmp_path, md_cases, code_bindings, duplicates)

        dups = [e for e in errors if e["type"] == "duplicate_in_md"]
        assert len(dups) == 1
        assert dups[0]["id"] == "DUP-001"
        assert "2 次" in dups[0]["message"]

    def test_no_duplicate_when_unique(self, tmp_path: Path):
        """所有 ID 唯一时不应报告重复。"""
        md_cases = {
            "UNI-001": {
                "priority": "P0",
                "layer": "UI",
                "scenario": "A",
                "how": "自动",
                "assertions": "通过",
                "test_type": "pytest",
                "related_check": "—",
                "code_location": "—",
                "source_file": "a.md",
            },
            "UNI-002": {
                "priority": "P1",
                "layer": "API",
                "scenario": "B",
                "how": "自动",
                "assertions": "通过",
                "test_type": "pytest",
                "related_check": "—",
                "code_location": "—",
                "source_file": "a.md",
            },
        }
        code_bindings: dict = {}

        errors = self._make_helper(tmp_path, md_cases, code_bindings, [])

        dups = [e for e in errors if e["type"] == "duplicate_in_md"]
        assert len(dups) == 0


# ===========================================================================
# 场景 7：能发现 P0/P1 manual-only
# ===========================================================================

class TestP0P1ManualOnly:
    """验证 P0/P1 用例测试类型仅为 manual 且无代码绑定时应报告 p0_p1_manual_only。"""

    def _make_helper(self, tmp_path: Path, md_cases: dict, code_bindings: dict, duplicates: list | None = None):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        return _validate(md_cases, code_bindings, duplicates or [], repo_root)

    def _make_case(self, priority: str, test_type: str) -> dict:
        """辅助构造一个 MD 用例字典。"""
        return {
            "priority": priority,
            "layer": "UI",
            "scenario": "测试场景",
            "how": "手动操作",
            "assertions": "正常",
            "test_type": test_type,
            "related_check": "—",
            "code_location": "—",
            "source_file": "test.md",
        }

    def test_p0_manual_only(self, tmp_path: Path):
        """P0 + 仅 manual + 无绑定 -> p0_p1_manual_only。"""
        md_cases = {"MANUAL-P0-001": self._make_case("P0", "manual")}
        code_bindings: dict = {}

        errors = self._make_helper(tmp_path, md_cases, code_bindings)

        manual_errs = [e for e in errors if e["type"] == "p0_p1_manual_only"]
        assert len(manual_errs) == 1
        assert manual_errs[0]["id"] == "MANUAL-P0-001"

    def test_p1_manual_only(self, tmp_path: Path):
        """P1 + 仅 manual + 无绑定 -> p0_p1_manual_only。"""
        md_cases = {"MANUAL-P1-001": self._make_case("P1", "manual")}
        code_bindings: dict = {}

        errors = self._make_helper(tmp_path, md_cases, code_bindings)

        manual_errs = [e for e in errors if e["type"] == "p0_p1_manual_only"]
        assert len(manual_errs) == 1

    def test_p0_manual_with_binding_no_error(self, tmp_path: Path):
        """P0 + manual 但有代码绑定 -> 不报告（有自动化覆盖）。"""
        md_cases = {"MANUAL-P0-002": self._make_case("P0", "manual")}
        code_bindings = {
            "MANUAL-P0-002": {"files": ["tests/test_manual.py"], "type": "pytest"}
        }

        errors = self._make_helper(tmp_path, md_cases, code_bindings)

        manual_errs = [e for e in errors if e["type"] == "p0_p1_manual_only"]
        assert len(manual_errs) == 0

    def test_p0_mixed_manual_pytest_no_error(self, tmp_path: Path):
        """P0 + manual,pytest 混合 -> 不报告（不全是 manual）。"""
        md_cases = {"MIXED-P0-001": self._make_case("P0", "manual, pytest")}
        code_bindings: dict = {}

        errors = self._make_helper(tmp_path, md_cases, code_bindings)

        manual_errs = [e for e in errors if e["type"] == "p0_p1_manual_only"]
        assert len(manual_errs) == 0

    def test_p2_manual_no_error(self, tmp_path: Path):
        """P2 + manual -> 不报告（P2 不受此规则约束）。"""
        md_cases = {"MANUAL-P2-001": self._make_case("P2", "manual")}
        code_bindings: dict = {}

        errors = self._make_helper(tmp_path, md_cases, code_bindings)

        manual_errs = [e for e in errors if e["type"] == "p0_p1_manual_only"]
        assert len(manual_errs) == 0


# ===========================================================================
# 场景 8：能发现 screenshot 缺少 snapshot 更新条件
# ===========================================================================

class TestScreenshotSnapshotCondition:
    """验证测试类型含 screenshot 但关联检查列不包含 snapshot 时应报告错误。"""

    def _make_helper(self, tmp_path: Path, md_cases: dict, code_bindings: dict, duplicates: list | None = None):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        return _validate(md_cases, code_bindings, duplicates or [], repo_root)

    def _make_case(self, test_type: str, related_check: str) -> dict:
        return {
            "priority": "P0",
            "layer": "UI",
            "scenario": "截图测试",
            "how": "自动",
            "assertions": "截图一致",
            "test_type": test_type,
            "related_check": related_check,
            "code_location": "—",
            "source_file": "test.md",
        }

    def test_screenshot_without_snapshot(self, tmp_path: Path):
        """测试类型含 screenshot 但关联检查无 snapshot -> 报告错误。"""
        md_cases = {"SCREENSHOT-001": self._make_case("screenshot", "视觉回归检查")}
        code_bindings: dict = {}

        errors = self._make_helper(tmp_path, md_cases, code_bindings)

        ss_errs = [e for e in errors if e["type"] == "screenshot_missing_snapshot"]
        assert len(ss_errs) == 1
        assert ss_errs[0]["id"] == "SCREENSHOT-001"

    def test_screenshot_with_snapshot_no_error(self, tmp_path: Path):
        """测试类型含 screenshot 且关联检查有 snapshot -> 不报告。"""
        md_cases = {"SCREENSHOT-002": self._make_case("screenshot", "snapshot 更新 + 视觉回归")}
        code_bindings: dict = {}

        errors = self._make_helper(tmp_path, md_cases, code_bindings)

        ss_errs = [e for e in errors if e["type"] == "screenshot_missing_snapshot"]
        assert len(ss_errs) == 0

    def test_no_screenshot_no_error(self, tmp_path: Path):
        """测试类型不含 screenshot -> 不报告。"""
        md_cases = {"NOSCREENSHOT-001": self._make_case("pytest", "—")}
        code_bindings: dict = {}

        errors = self._make_helper(tmp_path, md_cases, code_bindings)

        ss_errs = [e for e in errors if e["type"] == "screenshot_missing_snapshot"]
        assert len(ss_errs) == 0

    def test_screenshot_case_insensitive(self, tmp_path: Path):
        """screenshot 大小写不敏感时也应匹配。"""
        md_cases = {"SCREENSHOT-003": self._make_case("pytest, Screenshot", "视觉检查")}
        code_bindings: dict = {}

        errors = self._make_helper(tmp_path, md_cases, code_bindings)

        ss_errs = [e for e in errors if e["type"] == "screenshot_missing_snapshot"]
        assert len(ss_errs) == 1
