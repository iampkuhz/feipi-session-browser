const path = require('path');

const repoRoot = path.resolve(__dirname, '../..');
const runId = process.env.FEIPI_RUN_ID || process.env.FEIPI_SESSION_ID || `pid-${process.pid}`;
const runtimeRoot = process.env.FEIPI_AGENT_RUNTIME_ROOT
  ? path.resolve(process.env.FEIPI_AGENT_RUNTIME_ROOT)
  : path.join(repoRoot, 'tmp', 'agent-runtime');
const runRoot = path.join(runtimeRoot, 'runs', runId);

module.exports = Object.freeze({
  repoRoot,
  runId,
  runtimeRoot,
  runTmpRoot: path.join(runRoot, 'tmp'),
  runPlaywrightRoot: path.join(runRoot, 'playwright'),
});
