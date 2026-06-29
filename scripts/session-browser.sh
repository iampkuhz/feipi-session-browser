#!/usr/bin/env bash
# 本地 entry point for session-browser（Java launcher + Python 开发工具）。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CALLER_DIR="$(pwd)"
VERSION_FILE="$PROJECT_DIR/VERSION"
VENV_DIR="${SESSION_BROWSER_VENV_DIR:-$PROJECT_DIR/.venv}"
DEFAULT_LOCAL_HOST=127.0.0.1
DEFAULT_LOCAL_PORT=8848
DEFAULT_LOCAL_DATA_DIR="$HOME/.local/share/feipi/session-browser/local-test-index"

export PYTHONPATH="${PYTHONPATH:-}"

CMD="${1:-help}"
shift || true

read_version() {
    if [[ -n "${SESSION_BROWSER_VERSION:-}" ]]; then
        printf '%s\n' "$SESSION_BROWSER_VERSION"
    elif [[ -f "$VERSION_FILE" ]]; then
        tr -d '[:space:]' < "$VERSION_FILE"
        printf '\n'
    else
        printf '0.0-dev\n'
    fi
}

validate_version() {
    local version="$1"
    if [[ ! "$version" =~ ^[0-9]+\.[0-9]+(-[A-Za-z0-9._-]+)?$|^[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9._-]+)?$ ]]; then
        echo "版本号不合法：$version" >&2
        echo "请使用版本号 x.y 或 x.y.z，例如 0.4 或 0.4.1-rc.1" >&2
        exit 1
    fi
}

set_version() {
    local version="$1"
    validate_version "$version"
    printf '%s\n' "$version" > "$VERSION_FILE"
    echo "版本已更新：$version"
}

local_test_index_dir() {
    expand_path "${SESSION_BROWSER_LOCAL_DATA_DIR:-$DEFAULT_LOCAL_DATA_DIR}"
}

arg_has_option() {
    local opt="$1"
    shift || true
    local arg
    for arg in "$@"; do
        if [[ "$arg" == "$opt" || "$arg" == "$opt="* ]]; then
            return 0
        fi
    done
    return 1
}

expand_path() {
    local value="$1"
    local expanded
    case "$value" in
        "~") expanded="$HOME" ;;
        "~/"*) expanded="$HOME/${value#~/}" ;;
        *) expanded="$value" ;;
    esac

    case "$expanded" in
        /*) printf '%s\n' "$expanded" ;;
        *) printf '%s/%s\n' "$CALLER_DIR" "$expanded" ;;
    esac
}

# Java launcher 定位（help/version cutover）。
# 不执行 Gradle build；launcher 必须已预构建。
java_launcher_path() {
    printf '%s\n' "$PROJECT_DIR/java/app-cli/build/install/app-cli/bin/app-cli"
}

# 通过 Java launcher 执行 help/version。
# launcher 缺失时中文报错、非零退出、不 fallback 到 Python。
run_java_help_version() {
    run_java_command "$@"
}

python_bin() {
    if [[ -n "${SESSION_BROWSER_PYTHON:-}" ]]; then
        if python_is_compatible "$SESSION_BROWSER_PYTHON"; then
            printf '%s\n' "$SESSION_BROWSER_PYTHON"
            return 0
        fi
        echo "SESSION_BROWSER_PYTHON 不可执行或低于 Python 3.10：$SESSION_BROWSER_PYTHON" >&2
        exit 1
    fi

    if [[ -x "$VENV_DIR/bin/python" ]] && python_is_compatible "$VENV_DIR/bin/python"; then
        printf '%s\n' "$VENV_DIR/bin/python"
        return 0
    fi

    if command -v python >/dev/null 2>&1 && python_is_compatible python; then
        printf 'python\n'
        return 0
    fi

    if command -v python3 >/dev/null 2>&1 && python_is_compatible python3; then
        printf 'python3\n'
        return 0
    fi

    echo "未找到可用 Python 解释器（需要 Python >= 3.10）。" >&2
    exit 1
}

python_is_compatible() {
    local candidate="$1"
    "$candidate" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

run_dev_tool() {
    local tool="$1"
    shift || true
    cd "$PROJECT_DIR"
    if command -v uv >/dev/null 2>&1; then
        uv run "$tool" "$@"
        return $?
    fi
    if [[ -x "$VENV_DIR/bin/$tool" ]]; then
        "$VENV_DIR/bin/$tool" "$@"
        return $?
    fi
    PATH="$VENV_DIR/bin:${PATH:-}" "$tool" "$@"
}

run_tests() {
    cd "$PROJECT_DIR"
    "$(python_bin)" "$PROJECT_DIR/scripts/harness/python_env.py" check-installed --profile test
    local -a pytest_args
    pytest_args=(-W error)
    if [[ $# -gt 0 ]]; then
        pytest_args+=("$@")
    else
        pytest_args+=(tests)
    fi
    PYTHONPATH="${PYTHONPATH:-}" "$(python_bin)" -m pytest "${pytest_args[@]}"
}

print_deps_usage() {
    cat <<'EOF'
用法：./scripts/session-browser.sh deps [--dry-run] [--dev] [dev installer options]

默认行为：
  deps                 构建 Java launcher，并运行产品运行时 preflight
  deps --dry-run       只检查将执行的 Java bootstrap 步骤，不写入构建产物

开发依赖：
  deps --dev           安装 Python 开发/测试依赖
  deps --dev --dry-run 仅检查 Python 依赖声明和锁文件一致性

说明：
  scan/serve 是产品命令，依赖 Java launcher；Python 依赖仅用于开发质量门和测试。
EOF
}

install_dev_deps() {
    cd "$PROJECT_DIR"
    if [[ "${1:-}" == "--dry-run" ]]; then
        "$(python_bin)" "$PROJECT_DIR/scripts/harness/python_env.py" report
        echo "[DRY-RUN] 未安装依赖；锁文件一致性检查完成。"
        return 0
    fi
    if command -v uv >/dev/null 2>&1 && [[ "${SESSION_BROWSER_DEPS_INSTALLER:-uv}" == "uv" ]]; then
        uv sync --extra dev "$@"
        return $?
    fi
    if [[ ! -x "$VENV_DIR/bin/python" ]]; then
        python3 -m venv "$VENV_DIR"
    fi
    "$(python_bin)" -m pip install -r requirements-dev.txt "$@"
}

install_deps() {
    local dry_run=false
    local dev=false
    local -a passthrough=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run)
                dry_run=true
                ;;
            --dev)
                dev=true
                ;;
            -h|--help)
                print_deps_usage
                return 0
                ;;
            *)
                passthrough+=("$1")
                ;;
        esac
        shift
    done

    if [[ "$dev" == true ]]; then
        if [[ "$dry_run" == true ]]; then
            if [[ ${#passthrough[@]} -gt 0 ]]; then
                install_dev_deps --dry-run "${passthrough[@]}"
            else
                install_dev_deps --dry-run
            fi
        else
            if [[ ${#passthrough[@]} -gt 0 ]]; then
                install_dev_deps "${passthrough[@]}"
            else
                install_dev_deps
            fi
        fi
        return $?
    fi

    if [[ ${#passthrough[@]} -gt 0 ]]; then
        echo "错误：deps 默认 bootstrap 不接受额外参数：${passthrough[*]}" >&2
        echo "如需安装 Python 开发依赖，请使用：./scripts/session-browser.sh deps --dev" >&2
        return 1
    fi

    cd "$PROJECT_DIR"
    local index_dir
    index_dir="$(local_test_index_dir)"
    if ! command -v java >/dev/null 2>&1; then
        echo "错误：未找到 Java 运行时。请先安装 Java 17 或更高版本。" >&2
        return 1
    fi
    if [[ ! -x "$PROJECT_DIR/gradlew" ]]; then
        echo "错误：Gradle wrapper 不可执行：$PROJECT_DIR/gradlew" >&2
        return 1
    fi

    local launcher
    launcher="$(java_launcher_path)"
    if [[ "$dry_run" == true ]]; then
        echo "[DRY-RUN] 将执行：./gradlew :java:app-cli:installDist"
        echo "[DRY-RUN] 将使用本地索引目录：$index_dir"
        if [[ -x "$launcher" ]]; then
            echo "[DRY-RUN] Java launcher 已存在：$launcher"
        else
            echo "[DRY-RUN] Java launcher 尚未构建；正式运行 deps 会创建：$launcher"
        fi
        return 0
    fi

    ./gradlew :java:app-cli:installDist
    if [[ ! -x "$launcher" ]]; then
        echo "错误：Java launcher 构建后仍未找到：$launcher" >&2
        return 1
    fi
    export INDEX_DIR="$index_dir"
    "$launcher" deps
    echo ""
    echo "下一步："
    echo "  ./scripts/session-browser.sh scan"
    echo "  ./scripts/session-browser.sh serve"
}

run_format() {
    run_dev_tool ruff format .
    run_dev_tool ruff check --select I --fix .
}

run_format_check() {
    run_dev_tool ruff format --check .
    run_dev_tool ruff check --select I .
}

run_lint() {
    run_dev_tool ruff check .
}

run_type_check() {
    run_dev_tool pyright
}

run_doc_checks() {
    run_dev_tool interrogate scripts
    run_dev_tool pydoclint scripts
}

run_coverage() {
    run_dev_tool pytest -W error --cov=scripts --cov-branch --cov-report=term-missing --cov-report=xml "$@"
}

run_audit() {
    run_dev_tool pip-audit
    run_dev_tool bandit -r scripts
}

run_complexity() {
    run_dev_tool xenon --max-absolute B --max-modules B --max-average A scripts
}

run_dead_code() {
    run_dev_tool vulture --min-confidence 90 scripts tests
}

run_deps_check() {
    run_dev_tool deptry scripts
}

run_quality() {
    run_format_check
    run_lint
    run_type_check
    run_doc_checks
    run_coverage
    run_audit
    run_complexity
    run_dead_code
    run_deps_check
}

# 通过 Java launcher 执行 serve/stop/scan 等命令。
# launcher 缺失时中文报错、非零退出、不 fallback 到 Python。
run_java_command() {
    local launcher
    launcher="$(java_launcher_path)"
    if [[ ! -x "$launcher" ]]; then
        echo "错误：Java launcher 未找到：$launcher" >&2
        echo "请先执行构建：./gradlew :java:app-cli:installDist" >&2
        exit 1
    fi
    exec "$launcher" "$@"
}

run_scan() {
    local index_dir
    index_dir="$(local_test_index_dir)"
    mkdir -p "$index_dir"

    export INDEX_DIR="$index_dir"
    export SESSION_BROWSER_VERSION="${SESSION_BROWSER_VERSION:-$(read_version)}"
    export SESSION_BROWSER_SCAN_LOCK_TIMEOUT_SECONDS="${SESSION_BROWSER_SCAN_LOCK_TIMEOUT_SECONDS:-30}"
    echo "使用本地测试索引目录：$index_dir"
    run_java_command scan "$@"
}

run_serve() {
    local index_dir
    index_dir="$(local_test_index_dir)"
    mkdir -p "$index_dir"

    export INDEX_DIR="$index_dir"
    export SESSION_BROWSER_VERSION="${SESSION_BROWSER_VERSION:-$(read_version)}"
    local -a java_args
    java_args=()
    if ! arg_has_option "--host" "$@"; then
        java_args+=("--host" "${SESSION_BROWSER_LOCAL_HOST:-$DEFAULT_LOCAL_HOST}")
    fi
    if ! arg_has_option "--port" "$@"; then
        java_args+=("--port" "${SESSION_BROWSER_LOCAL_PORT:-$DEFAULT_LOCAL_PORT}")
    fi
    if [[ $# -gt 0 ]]; then
        java_args+=("$@")
    fi
    run_java_command serve "${java_args[@]}"
}

run_stop() {
    run_java_command stop "$@"
}

print_usage() {
    cat <<'EOF'
用法：./scripts/session-browser.sh <command> [options]

本地验证：
  deps                             构建 Java launcher 并运行产品 preflight
  deps --dry-run                   仅展示 Java bootstrap 计划，不写入构建产物
  deps --dev [pip options]         安装 Python 开发/测试依赖
  deps --dev --dry-run             仅检查 Python、依赖声明和锁文件一致性
  format                           使用 Ruff Formatter/Ruff import 规则自动格式化
  format-check                     检查 Ruff 格式和 import 排序，不修改文件
  lint                             执行 Ruff lint
  type                             执行 Pyright 类型检查
  doc                              执行 interrogate 与 pydoclint 文档检查
  coverage [pytest options]        执行 pytest-cov/Coverage.py 覆盖率检查
  audit                            执行 pip-audit 与 Bandit 安全检查
  complexity                       执行 Xenon/Radon 复杂度检查
  dead-code                        执行 Vulture 死代码检查
  deps-check                       执行 Deptry 依赖声明检查
  quality                          执行完整 Python 标准质量门禁
  serve [serve options]            前台启动本地服务（Java launcher）
  scan [scan options]              扫描到本地测试索引（Java launcher）
  stop [--port 8848]               按端口停止本地服务进程（Java launcher）
  test [pytest options]            执行单元测试

版本管理：
  version                          输出当前版本
  set-version <x.y>                更新 VERSION

常用环境变量：
  SESSION_BROWSER_VENV_DIR         默认：./.venv
  SESSION_BROWSER_PYTHON           显式 Python；优先级高于虚拟环境
  SESSION_BROWSER_DEPS_INSTALLER   deps --dev 默认：uv；设为 pip 可使用 requirements-dev.txt 安装
  SESSION_BROWSER_LOCAL_HOST       默认：127.0.0.1
  SESSION_BROWSER_LOCAL_PORT       默认：8848
  SESSION_BROWSER_LOCAL_DATA_DIR   默认：~/.local/share/feipi/session-browser/local-test-index
  SESSION_BROWSER_LOG_LEVEL        默认：WARN；可设为 INFO 或 DEBUG 输出更多日志
  SESSION_BROWSER_DEV_SCAN_LOGIC_VERSION_GATE
                                   本地 scan 默认启用；内部逻辑版本变化时自动 full scan
  CLAUDE_DATA_DIR                  默认：~/.claude
  CODEX_DATA_DIR                   默认：~/.codex
  QODER_DATA_DIR                   默认：~/.qoder
  QODER_APP_SUPPORT_DIR            默认：~/Library/Application Support/Qoder

示例：
  ./scripts/session-browser.sh serve
  ./scripts/session-browser.sh scan
  ./scripts/session-browser.sh scan --full
EOF
}

case "$CMD" in
    help|-h|--help)
        print_usage
        # 尝试运行 Java launcher 显示扩展帮助；launcher 缺失时忽略错误
        _launcher="$(java_launcher_path)"
        if [[ -x "$_launcher" ]]; then
            echo ""
            "$_launcher" "--help" || true
        fi
        ;;
    dev)
        echo "提示：dev 已合并到 serve；等同执行 ./scripts/session-browser.sh serve。" >&2
        run_serve "$@"
        ;;
    deps)
        install_deps "$@"
        ;;
    format)
        run_format "$@"
        ;;
    format-check)
        run_format_check "$@"
        ;;
    lint)
        run_lint "$@"
        ;;
    type)
        run_type_check "$@"
        ;;
    doc)
        run_doc_checks "$@"
        ;;
    coverage)
        run_coverage "$@"
        ;;
    audit)
        run_audit "$@"
        ;;
    complexity)
        run_complexity "$@"
        ;;
    dead-code)
        run_dead_code "$@"
        ;;
    deps-check)
        run_deps_check "$@"
        ;;
    quality)
        run_quality "$@"
        ;;
    scan)
        run_scan "$@"
        ;;
    serve)
        run_serve "$@"
        ;;
    stop)
        run_stop "$@"
        ;;
    test)
        run_tests "$@"
        ;;
    version)
        run_java_help_version "--version"
        ;;
    set-version)
        if [[ $# -lt 1 ]]; then
            echo "用法：$0 set-version <x.y>" >&2
            exit 1
        fi
        set_version "$1"
        ;;
    *)
        echo "未知命令：$CMD" >&2
        print_usage
        exit 1
        ;;
esac
