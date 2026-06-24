# QA-090: S4 Query/Application API 冻结与 Stage 收口

## Stage
S4 -- Query + Diagnostics + Application

## Goal
只读验收 Java 查询能力和 presentation model；生产 Python Web 在 S5 切换。

## Boundary
stage.S4.closeout

## Owner Before
Python production query; Java candidate

## Owner After
Java query/application API frozen

## Fallback
forbidden

## Kind
CLOSEOUT

## Verification Scope
- 冷构建 `./gradlew clean check --no-build-cache`
- warm cache `./gradlew check --configuration-cache`
- `./gradlew qualityFull`
- `./gradlew reuseAnalyzeIncremental`
- `./scripts/session-browser.sh test`
- `python3 scripts/quality/check_code_comment_language.py java/ --jobs auto`
- `./gradlew verifyJavaApiSnapshot`
- production closeout diff 为空
- query/application 所有权转移证明

## Allowed Files
- docs/**
- harness/**
- scripts/harness/**
- scripts/quality/**
- tests/**
- java/contract-tests/**
- tmp/java-migration-run/**

## Forbidden Files
- java/**/src/main/**
- src/session_browser/**

## Acceptance Criteria
- Java 可独立生成全部 Web 所需模型
- Python Web 仍可运行
- production closeout diff 为空
- 0 skipped/aborted
- S4-ACCEPTED marker 生成
- durable ownership 文档更新
