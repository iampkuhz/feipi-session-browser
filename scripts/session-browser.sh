#!/usr/bin/env bash
# Session Browser 唯一公开产品入口：仅负责构建引导、验证入口、Java 环境发现与 CLI 转发。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
JAVA_LAUNCHER="$PROJECT_DIR/java/app-cli/build/install/app-cli/bin/app-cli"
REQUIRED_JAVA_MAJOR=25

# 从实际执行结果获取真实 JDK home；不把可执行的系统占位程序视为可用 Java。
_read_java_home() {
    local java_bin="$1" settings major home
    [[ -x "$java_bin" ]] || return 1
    settings=$("$java_bin" -XshowSettings:properties -version 2>&1) || return 1
    major=$(printf '%s\n' "$settings" | sed -n 's/^[[:space:]]*java.specification.version = //p')
    home=$(printf '%s\n' "$settings" | sed -n 's/^[[:space:]]*java.home = //p')
    [[ "$major" == "$REQUIRED_JAVA_MAJOR" && -n "$home" ]] || return 1
    [[ -x "$home/bin/java" && -x "$home/bin/javac" ]] || return 1
    (cd "$home" && pwd -P)
}

# PATH 可能是 shim 或多层软链接；验证其返回的真实 Java 与编译器，而非猜测父目录。
_resolve_java_home() {
    local home verified compiler major
    home=$(_read_java_home "$1") || return 1
    verified=$(_read_java_home "$home/bin/java") || return 1
    [[ "$home" == "$verified" ]] || return 1
    compiler=$("$home/bin/javac" -version 2>&1) || return 1
    major=$(printf '%s\n' "$compiler" | sed -n 's/^javac \([0-9][0-9]*\).*/\1/p')
    [[ "$major" == "$REQUIRED_JAVA_MAJOR" ]] || return 1
    printf '%s\n' "$home"
}

_validate_java_home() {
    [[ -x "$1/bin/javac" ]] || return 1
    _resolve_java_home "$1/bin/java"
}

# 仅探测有限的公开安装入口，不加载交互式 shell 或个人配置。
_find_java_home() {
    local candidate java_path root prefix formula home
    local macos_probe="/usr/libexec/java_home"
    java_path=$(type -P java || true)
    if candidate=$(_resolve_java_home "$java_path"); then
        printf '%s\n' "$candidate"
        return 0
    fi

    local brew_prefixes=("${HOMEBREW_PREFIX:-}" "/opt/homebrew" "/usr/local")
    local candidates_dirs=("${SDKMAN_CANDIDATES_DIR:-}")
    if [[ -n "${SDKMAN_DIR:-}" ]]; then
        candidates_dirs+=("$SDKMAN_DIR/candidates")
    fi
    if [[ -n "${HOME:-}" ]]; then
        candidates_dirs+=("$HOME/.sdkman/candidates")
    fi
    for prefix in "${brew_prefixes[@]}"; do
        [[ -n "$prefix" ]] && candidates_dirs+=("$prefix/opt/sdkman-cli/libexec/candidates")
    done
    for root in "${candidates_dirs[@]}"; do
        [[ -n "$root" ]] || continue
        if candidate=$(_validate_java_home "$root/java/current"); then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    if [[ -x "$macos_probe" ]]; then
        if home=$("$macos_probe" -F -v "$REQUIRED_JAVA_MAJOR" 2>/dev/null) &&
            candidate=$(_validate_java_home "$home"); then
            printf '%s\n' "$candidate"
            return 0
        fi
    fi

    for prefix in "${brew_prefixes[@]}"; do
        [[ -n "$prefix" ]] || continue
        for formula in "openjdk@$REQUIRED_JAVA_MAJOR" openjdk; do
            for home in "$prefix/opt/$formula" "$prefix/opt/$formula/libexec/openjdk.jdk/Contents/Home"; do
                if candidate=$(_validate_java_home "$home"); then
                    printf '%s\n' "$candidate"
                    return 0
                fi
            done
        done
    done
    return 1
}

# 显式配置错误不静默回退；构建和 launcher 继承同一套选定 JDK。
discover_java_home() {
    local candidate
    if [[ -n "${JAVA_HOME:-}" ]]; then
        if ! candidate=$(_validate_java_home "$JAVA_HOME"); then
            echo "错误：JAVA_HOME 已设置但无效或非 JDK ${REQUIRED_JAVA_MAJOR}：$JAVA_HOME" >&2
            echo "请检查 JAVA_HOME 指向有效的 JDK ${REQUIRED_JAVA_MAJOR} 安装。" >&2
            return 1
        fi
    elif ! candidate=$(_find_java_home); then
        echo "错误：未找到有效的 JDK ${REQUIRED_JAVA_MAJOR}。" >&2
        echo "请设置 JAVA_HOME 或安装 JDK ${REQUIRED_JAVA_MAJOR}（SDKMAN、Homebrew 等）。" >&2
        return 1
    fi
    export JAVA_HOME="$candidate"
    export PATH="$JAVA_HOME/bin:${PATH:-}"
}

# Java launcher 是所有产品子命令的唯一 owner；缺失时必须显式失败。
require_java_launcher() {
    if [[ -x "$JAVA_LAUNCHER" ]]; then
        return 0
    fi
    echo "错误：Java launcher 未找到：$JAVA_LAUNCHER" >&2
    echo "请先执行：./scripts/session-browser.sh deps" >&2
    return 1
}

# 使用 Gradle 的增量能力刷新 launcher；不执行测试。
build_java_launcher() {
    if [[ ! -x "$PROJECT_DIR/java/gradlew" ]]; then
        echo "错误：Gradle wrapper 不可执行：$PROJECT_DIR/java/gradlew" >&2
        return 1
    fi

    (
        cd "$PROJECT_DIR"
        ./java/gradlew -p java :java:app-cli:installDist
    )
}

# deps 构建 launcher，随后交给 Java deps 执行运行时 preflight。
run_deps() {
    case "${1:-}" in
        "")
            ;;
        plan)
            if [[ $# -ne 1 ]]; then
                echo "错误：deps plan 不接受额外参数。" >&2
                return 2
            fi
            echo "PLAN ./java/gradlew -p java :java:app-cli:installDist"
            echo "PLAN $JAVA_LAUNCHER deps"
            return 0
            ;;
        -h|--help)
            echo "用法：./scripts/session-browser.sh deps [plan]"
            return 0
            ;;
        *)
            echo "错误：deps 参数无效：$*" >&2
            echo "用法：./scripts/session-browser.sh deps [plan]" >&2
            return 2
            ;;
    esac

    discover_java_home
    build_java_launcher
    require_java_launcher
    cd "$PROJECT_DIR"
    exec "$JAVA_LAUNCHER" deps
}

# test 是固定的 Java 产品验证入口。
run_test() {
    if [[ $# -ne 0 ]]; then
        echo "错误：test 不接受额外参数；该入口固定执行 Java 产品测试。" >&2
        return 2
    fi
    discover_java_home
    cd "$PROJECT_DIR"
    exec ./java/gradlew -p java verifyNoSkippedJavaTests --no-daemon --no-build-cache --no-parallel --max-workers=1
}

# quality 默认执行增量 Gate；显式参数原样交给 Gate CLI。
run_quality() {
    cd "$PROJECT_DIR"
    if [[ $# -eq 0 ]]; then
        exec python3 scripts/gates/cli.py run --mode incremental
    fi
    exec python3 scripts/gates/cli.py "$@"
}

# serve 是本地开发启动命令；每次启动前刷新 launcher，Gradle 自行判断是否需要编译。
# 非 serve 命令先检查 launcher，保留原有缺 launcher 诊断不被 JDK 缺失遮盖。
run_java_command() {
    if [[ "${1:-}" == "serve" ]]; then
        discover_java_home
        build_java_launcher
        require_java_launcher
    else
        require_java_launcher
        discover_java_home
    fi
    exec "$JAVA_LAUNCHER" "$@"
}

if [[ $# -eq 0 ]]; then
    run_java_command --help
fi

COMMAND="$1"
shift

case "$COMMAND" in
    deps)
        run_deps "$@"
        ;;
    test)
        run_test "$@"
        ;;
    quality)
        run_quality "$@"
        ;;
    *)
        run_java_command "$COMMAND" "$@"
        ;;
esac
