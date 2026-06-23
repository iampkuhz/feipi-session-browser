# AC-090: S2C 所有权、CI 与 Stage 收口

## Stage
S2C -- Canonical Artifact Cutover

## Goal
只读验证并同步 ownership 文档；发现 production 缺陷时返回 owning task。

## Boundary
stage.S2C.closeout

## Owner Before
mixed artifact ownership (Python writer + Java batch)

## Owner After
Java canonical artifact owner; Python scan orchestration + SQLite + read-only consumer

## Fallback
forbidden

## Kind
CLOSEOUT

## Verification Scope
- 冷构建 `./gradlew clean check --no-build-cache`
- warm cache `./gradlew check --configuration-cache`
- `./gradlew qualityFull`
- `./scripts/session-browser.sh test`
- `bash scripts/harness/doctor.sh`
- `./gradlew reuseAnalyzeIncremental`
- `python3 -m pytest tests -q`
- `python3 scripts/quality/check_code_comment_language.py --jobs auto`
- 三来源 full/incremental/tiered synthetic scan
- artifact/source 隐私和只读 AST 证明

## Allowed Files
- docs/**
- harness/**
- scripts/harness/**
- scripts/quality/**
- scripts/claude_hooks/classify.py
- AGENTS.md, CLAUDE.md, README.md
- .github/workflows/**
- tests/**
- java/contract-tests/**
- tmp/java-migration-run/**

## Forbidden Files
- java/**/src/main/**
- src/session_browser/normalized/**
- src/session_browser/index/scanners.py
- scripts/session-browser.sh

## Acceptance Criteria
- Java 是 canonical JSON/meta 唯一 producer
- Python 仍拥有 scan orchestration/SQLite
- 0 skipped/aborted
- production 实现无 closeout 修改
- S2C-ACCEPTED marker 生成
- durable ownership 文档更新
