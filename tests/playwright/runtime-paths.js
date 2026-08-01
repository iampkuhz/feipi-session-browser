const crypto = require('crypto');
const path = require('path');

const repoRoot = path.resolve(__dirname, '../..');
const defaultRuntimeRoot = path.join(repoRoot, 'tmp', 'agent-runtime');

/**
 * 为 checkout 生成稳定且可读的目录名。
 *
 * linked checkout 会共享 Git common dir，也可能共享 FEIPI_AGENT_RUNTIME_ROOT，
 * 因此 runId 不能单独作为隔离边界。目录名同时保留 checkout 名称和绝对路径摘要，
 * 避免两个同名 checkout 相互覆盖 Playwright 输出或 fixture 临时数据。
 */
function checkoutScope(checkoutRoot) {
  const resolved = path.resolve(checkoutRoot);
  const readableName = path.basename(resolved).replace(/[^a-zA-Z0-9._-]/g, '-') || 'checkout';
  const digest = crypto.createHash('sha256').update(resolved).digest('hex').slice(0, 12);
  return `${readableName}-${digest}`;
}

/** 按 checkout、run 两层边界解析 Playwright 的全部运行目录。 */
function resolveRuntimePaths(options = {}) {
  const resolvedRepoRoot = path.resolve(options.repoRoot || repoRoot);
  const environment = options.env || process.env;
  const runId = environment.FEIPI_RUN_ID || environment.FEIPI_SESSION_ID || `pid-${process.pid}`;
  const runtimeRoot = environment.FEIPI_AGENT_RUNTIME_ROOT
    ? path.resolve(environment.FEIPI_AGENT_RUNTIME_ROOT)
    : (options.repoRoot ? path.join(resolvedRepoRoot, 'tmp', 'agent-runtime') : defaultRuntimeRoot);
  const scope = checkoutScope(resolvedRepoRoot);
  const runRoot = path.join(runtimeRoot, 'checkouts', scope, 'runs', runId);

  return Object.freeze({
    repoRoot: resolvedRepoRoot,
    checkoutScope: scope,
    runId,
    runtimeRoot,
    runTmpRoot: path.join(runRoot, 'tmp'),
    runPlaywrightRoot: path.join(runRoot, 'playwright'),
  });
}

module.exports = Object.freeze({
  ...resolveRuntimePaths(),
  resolveRuntimePaths,
});
