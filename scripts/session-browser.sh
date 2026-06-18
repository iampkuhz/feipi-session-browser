#!/usr/bin/env bash
# Unified local and Podman entry point for session-browser.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CALLER_DIR="$(pwd)"
SRC_DIR="$(cd "$SCRIPT_DIR/../src" && pwd)"
VERSION_FILE="$PROJECT_DIR/VERSION"
VENV_DIR="${SESSION_BROWSER_VENV_DIR:-$PROJECT_DIR/.venv}"
DIST_DIR="${SESSION_BROWSER_DIST_DIR:-$PROJECT_DIR/tmp/release/dist}"
DEFAULT_LOCAL_PORT=18999
DEFAULT_PODMAN_HOST_PORT=8899
DEFAULT_LOCAL_DATA_DIR="$HOME/.local/share/feipi/session-browser/local-test-index"
DEFAULT_PODMAN_DATA_DIR="$HOME/.local/share/feipi/session-browser/index"

export PYTHONPATH="$SRC_DIR:${PYTHONPATH:-}"

CMD="${1:-help}"
shift || true

read_version() {
    if [[ -n "${SESSION_BROWSER_VERSION:-}" ]]; then
        printf '%s\n' "$SESSION_BROWSER_VERSION"
    elif [[ -f "$VERSION_FILE" ]]; then
        tr -d '[:space:]' < "$VERSION_FILE"
        printf '\n'
    else
        printf '0.0.0-dev\n'
    fi
}

validate_version() {
    local version="$1"
    if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9._-]+)?$ ]]; then
        echo "版本号不合法：$version" >&2
        echo "请使用语义化版本，例如 0.2.0 或 0.2.0-rc.1" >&2
        exit 1
    fi
}

set_version() {
    local version="$1"
    validate_version "$version"
    printf '%s\n' "$version" > "$VERSION_FILE"
    echo "版本已更新：$version"
}

image_repo() {
    printf '%s\n' "${SESSION_BROWSER_IMAGE_REPO:-localhost/feipi/session-browser}"
}

container_name() {
    printf '%s\n' "${SESSION_BROWSER_CONTAINER_NAME:-session-browser}"
}

host_port() {
    printf '%s\n' "${SESSION_BROWSER_HOST_PORT:-$DEFAULT_PODMAN_HOST_PORT}"
}

local_test_port() {
    printf '%s\n' "${SESSION_BROWSER_LOCAL_PORT:-$DEFAULT_LOCAL_PORT}"
}

local_test_index_dir() {
    expand_path "${SESSION_BROWSER_LOCAL_DATA_DIR:-$DEFAULT_LOCAL_DATA_DIR}"
}

local_test_host() {
    printf '%s\n' "${SESSION_BROWSER_LOCAL_HOST:-127.0.0.1}"
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

require_podman() {
    if ! command -v "${PODMAN_BIN:-podman}" >/dev/null 2>&1; then
        echo "未找到 podman。请安装 Podman，或设置 PODMAN_BIN=/path/to/podman。" >&2
        exit 1
    fi
}

warn_if_podman_running() {
    if ! command -v "${PODMAN_BIN:-podman}" >/dev/null 2>&1; then
        return 0
    fi

    local name status
    name="$(container_name)"
    status="$("${PODMAN_BIN:-podman}" inspect -f '{{.State.Status}}' "$name" 2>/dev/null || true)"
    if [[ "$status" == "running" ]]; then
        echo "提示：Podman 容器 $name 正在运行；本地测试会使用独立端口和独立索引目录。"
        echo "      测试结束请用 Ctrl-C 关闭当前前台进程，Podman 容器不受影响。"
    fi
}

python_bin() {
    if [[ -n "${SESSION_BROWSER_PYTHON:-}" ]]; then
        printf '%s\n' "$SESSION_BROWSER_PYTHON"
    elif [[ -x "$VENV_DIR/bin/python" ]]; then
        printf '%s\n' "$VENV_DIR/bin/python"
    elif command -v python >/dev/null 2>&1 && python - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
    then
        printf 'python\n'
    else
        printf 'python3\n'
    fi
}

run_tests() {
    cd "$PROJECT_DIR"
    if [[ $# -gt 0 ]]; then
        PYTHONPATH="$SRC_DIR:${PYTHONPATH:-}" "$(python_bin)" -m pytest "$@"
    else
        PYTHONPATH="$SRC_DIR:${PYTHONPATH:-}" "$(python_bin)" -m pytest tests
    fi
}

install_deps() {
    cd "$PROJECT_DIR"
    if [[ ! -x "$VENV_DIR/bin/python" ]]; then
        python3 -m venv "$VENV_DIR"
    fi
    "$VENV_DIR/bin/python" -m pip install -r requirements-dev.txt "$@"
}

ensure_runtime_deps() {
    "$(python_bin)" - <<'PY'
import importlib
import sys

missing = []
for module, package in (("jinja2", "jinja2"), ("markdown_it", "markdown-it-py")):
    try:
        importlib.import_module(module)
    except ModuleNotFoundError:
        missing.append(package)

if missing:
    print(
        "缺少 Python 运行依赖：" + ", ".join(missing),
        file=sys.stderr,
    )
    print(
        "请执行：./scripts/session-browser.sh deps",
        file=sys.stderr,
    )
    sys.exit(1)
PY
}

cleanup_python_build_artifacts() {
    rm -rf "$PROJECT_DIR/build" "$PROJECT_DIR/src/feipi_session_browser.egg-info"
}

build_dist() {
    local version="${1:-$(read_version)}"
    validate_version "$version"

    local current_version
    current_version="$(read_version)"
    if [[ "$current_version" != "$version" ]]; then
        echo "VERSION 与目标版本不一致：VERSION=$current_version target=$version" >&2
        echo "请先执行：./scripts/session-browser.sh set-version $version" >&2
        exit 1
    fi

    cd "$PROJECT_DIR"
    rm -rf "$DIST_DIR"
    mkdir -p "$DIST_DIR"
    cleanup_python_build_artifacts
    if ! "$(python_bin)" -m build --sdist --outdir "$DIST_DIR"; then
        cleanup_python_build_artifacts
        exit 1
    fi
    cleanup_python_build_artifacts
    echo "Python source 发布包已构建：$DIST_DIR"
}

verify_dist() {
    local version="${1:-$(read_version)}"
    validate_version "$version"

    VERSION_TO_VERIFY="$version" DIST_DIR_TO_VERIFY="$DIST_DIR" "$(python_bin)" - <<'PY'
import os
import sys
import tarfile
from pathlib import Path

version = os.environ["VERSION_TO_VERIFY"]
dist_dir = Path(os.environ["DIST_DIR_TO_VERIFY"])
normalized = "feipi_session_browser"
sdist = dist_dir / f"{normalized}-{version}.tar.gz"

missing_artifacts = [str(path) for path in (sdist,) if not path.exists()]
if missing_artifacts:
    print("缺少发布包：" + ", ".join(missing_artifacts), file=sys.stderr)
    sys.exit(1)

required_sdist_suffixes = {
    f"{normalized}-{version}/VERSION",
    f"{normalized}-{version}/pyproject.toml",
    f"{normalized}-{version}/src/session_browser/web/templates/base.html",
    f"{normalized}-{version}/src/session_browser/web/static/css/base.css",
    f"{normalized}-{version}/src/session_browser/web/static/js/session-detail/init.js",
    f"{normalized}-{version}/src/session_browser/web/static/images/favicon.svg",
}
with tarfile.open(sdist, "r:gz") as tf:
    names = set(tf.getnames())
    missing = sorted(required_sdist_suffixes - names)
    if missing:
        print("sdist 缺少必要资源：" + ", ".join(missing), file=sys.stderr)
        sys.exit(1)

print(f"source 发布包校验通过：{sdist.name}")
PY
}

build_image() {
    local version="${1:-$(read_version)}"
    validate_version "$version"
    require_podman

    local repo
    repo="$(image_repo)"

    echo "构建本地镜像："
    echo "  image: $repo:$version"
    echo "  latest: $repo:latest"
    "${PODMAN_BIN:-podman}" build \
        --build-arg "SESSION_BROWSER_VERSION=$version" \
        --label "org.opencontainers.image.version=$version" \
        --label "org.opencontainers.image.title=session-browser" \
        --label "org.opencontainers.image.source=feipi-session-browser" \
        -t "$repo:$version" \
        -t "$repo:latest" \
        "$PROJECT_DIR"
}

podman_up() {
    local version="${1:-$(read_version)}"
    validate_version "$version"
    require_podman

    local repo name port index_dir claude_dir codex_dir qoder_dir qoder_app_support_dir
    repo="$(image_repo)"
    name="$(container_name)"
    port="$(host_port)"
    index_dir="$(expand_path "${SESSION_BROWSER_DATA_DIR:-$DEFAULT_PODMAN_DATA_DIR}")"
    claude_dir="$(expand_path "${CLAUDE_DATA_DIR:-$HOME/.claude}")"
    codex_dir="$(expand_path "${CODEX_DATA_DIR:-$HOME/.codex}")"
    qoder_dir="$(expand_path "${QODER_DATA_DIR:-$HOME/.qoder}")"
    qoder_app_support_dir="$(expand_path "${QODER_APP_SUPPORT_DIR:-$HOME/Library/Application Support/Qoder}")"

    mkdir -p "$index_dir"

    local -a volume_args
    volume_args=(-v "$index_dir:/data/index")
    if [[ -d "$claude_dir" ]]; then
        volume_args+=(-v "$claude_dir:/data/claude:ro")
    else
        echo "警告：Claude 数据目录不存在，跳过挂载：$claude_dir" >&2
    fi
    if [[ -d "$codex_dir" ]]; then
        volume_args+=(-v "$codex_dir:/data/codex:ro")
    else
        echo "警告：Codex 数据目录不存在，跳过挂载：$codex_dir" >&2
    fi
    if [[ -d "$qoder_dir" ]]; then
        volume_args+=(-v "$qoder_dir:/data/qoder:ro")
    fi
    if [[ -d "$qoder_app_support_dir" ]]; then
        volume_args+=(-v "$qoder_app_support_dir:/data/qoder-app-support:ro")
    fi

    "${PODMAN_BIN:-podman}" rm -f "$name" >/dev/null 2>&1 || true
    "${PODMAN_BIN:-podman}" run -d \
        --name "$name" \
        -p "$port:8899" \
        "${volume_args[@]}" \
        -e "CLAUDE_DATA_DIR=/data/claude" \
        -e "CODEX_DATA_DIR=/data/codex" \
        -e "QODER_DATA_DIR=/data/qoder" \
        -e "QODER_APP_SUPPORT_DIR=/data/qoder-app-support" \
        -e "INDEX_DIR=/data/index" \
        -e "SERVER_HOST=0.0.0.0" \
        -e "SERVER_PORT=8899" \
        -e "SESSION_BROWSER_RUN_MODE=podman" \
        -e "SESSION_BROWSER_LOG_LEVEL=${SESSION_BROWSER_LOG_LEVEL:-INFO}" \
        -e "SESSION_BROWSER_VERSION=$version" \
        "$repo:$version" \
        ./scripts/session-browser.sh serve --allow-empty --startup-scan

    echo "session-browser 已启动：http://127.0.0.1:$port"
    echo "容器：$name"
    echo "镜像：$repo:$version"
    echo "索引目录：$index_dir"
    echo "数据挂载："
    echo "  Claude: $claude_dir"
    echo "  Codex:  $codex_dir"
    echo "  Qoder:  $qoder_dir"
    echo "  Qoder App Support: $qoder_app_support_dir"
}

run_local_serve() {
    ensure_runtime_deps

    local port host index_dir
    port="$(local_test_port)"
    host="$(local_test_host)"
    index_dir="$(local_test_index_dir)"
    mkdir -p "$index_dir"

    export PYTHONUNBUFFERED=1
    export SESSION_BROWSER_LOG_LEVEL="${SESSION_BROWSER_LOG_LEVEL:-DEBUG}"
    export SESSION_BROWSER_VERSION="${SESSION_BROWSER_VERSION:-$(read_version)}"

    local -a serve_args=()
    serve_args+=("$@")
    if ! arg_has_option "--host" "$@"; then
        serve_args=(--host "$host" "${serve_args[@]+"${serve_args[@]}"}")
    fi
    if ! arg_has_option "--port" "$@"; then
        serve_args=(--port "$port" "${serve_args[@]+"${serve_args[@]}"}")
    fi
    if ! arg_has_option "--startup-scan" "$@"; then
        serve_args=(--startup-scan "${serve_args[@]+"${serve_args[@]}"}")
    fi

    warn_if_podman_running
    echo "启动本地前台服务"
    echo "  版本：$SESSION_BROWSER_VERSION"
    echo "  地址：http://$host:$port"
    echo "  日志级别：$SESSION_BROWSER_LOG_LEVEL"
    echo "  本地测试索引：$index_dir"
    echo "  运行方式：前台进程；Ctrl-C 后本地测试服务立即关闭"
    echo "  源码目录：$SRC_DIR"
    INDEX_DIR="$index_dir" exec "$(python_bin)" -m session_browser serve --allow-empty "${serve_args[@]}"
}

run_scan() {
    local index_dir
    index_dir="$(local_test_index_dir)"
    mkdir -p "$index_dir"

    export SESSION_BROWSER_VERSION="${SESSION_BROWSER_VERSION:-$(read_version)}"
    echo "使用本地测试索引目录：$index_dir"
    INDEX_DIR="$index_dir" exec "$(python_bin)" -m session_browser scan "$@"
}

run_serve() {
    if [[ "${SESSION_BROWSER_RUN_MODE:-}" != "podman" ]]; then
        run_local_serve "$@"
    fi

    ensure_runtime_deps
    export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"
    export SESSION_BROWSER_VERSION="${SESSION_BROWSER_VERSION:-$(read_version)}"
    exec "$(python_bin)" -m session_browser serve --allow-empty "$@"
}

print_usage() {
    cat <<'EOF'
用法：./scripts/session-browser.sh <command> [options]

本地验证：
  deps [pip options]               安装本地运行/测试依赖
  serve [serve options]            前台启动本地服务，默认 DEBUG 日志
  scan [scan options]              扫描到本地测试索引
  stop [--port 18999]              按端口停止本地测试服务进程
  test [pytest options]            执行单元测试

版本与发布验证：
  version                          输出当前版本
  set-version <x.y.z>              更新 VERSION
  build-dist [x.y.z]               构建 Python source 发布包到 tmp/release/dist
  verify-dist [x.y.z]              校验 Python source 发布包版本与关键资源
  release-check [x.y.z]            测试、构建 source 发布包并校验发布包

常用环境变量：
  SESSION_BROWSER_VENV_DIR         默认：./.venv
  SESSION_BROWSER_LOCAL_HOST       默认：127.0.0.1
  SESSION_BROWSER_LOCAL_PORT       默认：18999
  SESSION_BROWSER_LOCAL_DATA_DIR   默认：~/.local/share/feipi/session-browser/local-test-index
  SESSION_BROWSER_LOG_LEVEL        默认：INFO；本地 serve 使用 DEBUG
  CLAUDE_DATA_DIR                  默认：~/.claude
  CODEX_DATA_DIR                   默认：~/.codex
  QODER_DATA_DIR                   默认：~/.qoder
  QODER_APP_SUPPORT_DIR            默认：~/Library/Application Support/Qoder

示例：
  ./scripts/session-browser.sh serve
  ./scripts/session-browser.sh scan --incremental
  ./scripts/session-browser.sh release-check 0.3.0
EOF
}

case "$CMD" in
    help|-h|--help)
        print_usage
        ;;
    dev)
        echo "提示：dev 已合并到 serve；等同执行 ./scripts/session-browser.sh serve。" >&2
        run_local_serve "$@"
        ;;
    deps)
        install_deps "$@"
        ;;
    scan)
        run_scan "$@"
        ;;
    serve)
        run_serve "$@"
        ;;
    stop)
        exec "$(python_bin)" -m session_browser stop "$@"
        ;;
    test)
        run_tests "$@"
        ;;
    version)
        read_version
        ;;
    set-version)
        if [[ $# -lt 1 ]]; then
            echo "用法：$0 set-version <x.y.z>" >&2
            exit 1
        fi
        set_version "$1"
        ;;
    build)
        build_image "${1:-$(read_version)}"
        ;;
    build-dist)
        build_dist "${1:-$(read_version)}"
        ;;
    verify-dist)
        verify_dist "${1:-$(read_version)}"
        ;;
    release-check)
        if [[ $# -ge 1 ]]; then
            set_version "$1"
        fi
        version="$(read_version)"
        run_tests
        build_dist "$version"
        verify_dist "$version"
        echo "本地发布验证通过："
        echo "  dist: $DIST_DIR"
        ;;
    deploy)
        if [[ $# -ge 1 ]]; then
            set_version "$1"
        fi
        version="$(read_version)"
        build_image "$version"
        podman_up "$version"
        ;;
    podman-up|up)
        podman_up "${1:-$(read_version)}"
        ;;
    podman-down|down)
        require_podman
        "${PODMAN_BIN:-podman}" rm -f "$(container_name)" >/dev/null 2>&1 || true
        echo "session-browser 已停止。"
        ;;
    podman-logs|logs)
        require_podman
        if [[ $# -gt 0 ]]; then
            "${PODMAN_BIN:-podman}" logs "$@" "$(container_name)"
        else
            "${PODMAN_BIN:-podman}" logs -f "$(container_name)"
        fi
        ;;
    podman-status|status)
        require_podman
        "${PODMAN_BIN:-podman}" ps -a --filter "name=$(container_name)"
        ;;
    *)
        echo "未知命令：$CMD" >&2
        print_usage
        exit 1
        ;;
esac
