#!/usr/bin/env bash
# Session Browser 唯一公开产品入口：仅负责构建引导、验证入口和 Java CLI 转发。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
JAVA_LAUNCHER="$PROJECT_DIR/java/app-cli/build/install/app-cli/bin/app-cli"

# Java launcher 是所有产品子命令的唯一 owner；缺失时必须显式失败。
require_java_launcher() {
    if [[ -x "$JAVA_LAUNCHER" ]]; then
        return 0
    fi
    echo "错误：Java launcher 未找到：$JAVA_LAUNCHER" >&2
    echo "请先执行：./scripts/session-browser.sh deps" >&2
    return 1
}

# deps 只负责构建 launcher，随后交给 Java deps 执行运行时 preflight。
run_deps() {
    case "${1:-}" in
        "")
            ;;
        --dry-run)
            if [[ $# -ne 1 ]]; then
                echo "错误：deps --dry-run 不接受额外参数。" >&2
                return 2
            fi
            echo "[DRY-RUN] 将执行：./gradlew :java:app-cli:installDist"
            echo "[DRY-RUN] 构建后将执行：$JAVA_LAUNCHER deps"
            return 0
            ;;
        -h|--help)
            echo "用法：./scripts/session-browser.sh deps [--dry-run]"
            return 0
            ;;
        *)
            echo "错误：deps 仅支持 --dry-run，不接受：$*" >&2
            return 2
            ;;
    esac

    if [[ ! -x "$PROJECT_DIR/gradlew" ]]; then
        echo "错误：Gradle wrapper 不可执行：$PROJECT_DIR/gradlew" >&2
        return 1
    fi

    cd "$PROJECT_DIR"
    ./gradlew :java:app-cli:installDist
    require_java_launcher
    exec "$JAVA_LAUNCHER" deps
}

# test 是固定的 Java 产品验证；定向 Python 测试不再伪装成产品命令。
run_test() {
    if [[ $# -ne 0 ]]; then
        echo "错误：test 不接受额外参数；该入口固定执行 Java 产品测试。" >&2
        return 2
    fi
    cd "$PROJECT_DIR"
    exec ./gradlew verifyNoSkippedJavaTests --no-daemon --no-build-cache --no-parallel --max-workers=1
}

# quality 默认执行增量 Gate；显式参数原样交给 Gate CLI。
run_quality() {
    cd "$PROJECT_DIR"
    if [[ $# -eq 0 ]]; then
        exec python3 scripts/gates/cli.py run --mode incremental
    fi
    exec python3 scripts/gates/cli.py "$@"
}

if [[ $# -eq 0 ]]; then
    require_java_launcher
    exec "$JAVA_LAUNCHER" --help
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
        require_java_launcher
        exec "$JAVA_LAUNCHER" "$COMMAND" "$@"
        ;;
esac
