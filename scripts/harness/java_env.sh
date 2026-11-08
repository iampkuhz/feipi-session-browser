#!/usr/bin/env bash
# 共享 JDK 发现：供产品入口、Gate 执行和 POSIX Gradle wrapper 复用。
REQUIRED_JAVA_MAJOR=25

# 从实际执行结果获取真实 JDK home；不把可执行的系统占位程序视为可用 Java。
_read_java_home() {
    local java_bin="$1" settings major home arch
    [[ -x "$java_bin" ]] || return 1
    settings=$("$java_bin" -XshowSettings:properties -version 2>&1) || return 1
    major=$(printf '%s\n' "$settings" | sed -n 's/^[[:space:]]*java.specification.version = //p')
    home=$(printf '%s\n' "$settings" | sed -n 's/^[[:space:]]*java.home = //p')
    arch=$(printf '%s\n' "$settings" | sed -n 's/^[[:space:]]*os.arch = //p')
    [[ "$major" == "$REQUIRED_JAVA_MAJOR" && "$arch" == aarch64 && -n "$home" ]] || return 1
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

    local brew_prefixes=("${HOMEBREW_PREFIX:-}" "/opt/homebrew")
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
    if [[ "$(uname -sm)" != 'Darwin arm64' ]]; then
        echo "错误：开发与构建仅支持 Apple Silicon macOS（arm64）。" >&2
        return 1
    fi
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


if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    discover_java_home || exit $?
    printf '%s\n' "$JAVA_HOME"
fi
