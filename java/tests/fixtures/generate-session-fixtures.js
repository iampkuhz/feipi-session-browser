const fs = require('fs');
const path = require('path');

const SPEC = Object.freeze({
  project: 'test-hifi-project',
  mockCount: 43,
  longSessionId: 'long-session-001',
  longRounds: 100,
  baseTimestampMs: Date.parse('2026-04-24T10:00:00.000Z'),
});

function timestamp(offsetSeconds) {
  return new Date(SPEC.baseTimestampMs + offsetSeconds * 1000).toISOString();
}

function writeJsonl(file, records) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${records.map((record) => JSON.stringify(record)).join('\n')}\n`);
}

function userEvent(content, offsetSeconds) {
  return {
    synthetic: true,
    type: 'user',
    message: { role: 'user', content },
    timestamp: timestamp(offsetSeconds),
    entrypoint: 'cli',
    gitBranch: 'main',
  };
}

function usage(seed) {
  return {
    input_tokens: 400 + seed * 7,
    cache_read_input_tokens: seed % 3 === 0 ? 120 + seed : 0,
    cache_creation_input_tokens: seed % 5 === 0 ? 80 + seed : 0,
    output_tokens: 40 + (seed % 19),
  };
}

function assistantEvent(content, offsetSeconds, seed, stopReason = 'end_turn') {
  return {
    synthetic: true,
    type: 'assistant',
    message: {
      model: 'synthetic-claude-model',
      role: 'assistant',
      content,
      usage: usage(seed),
      stop_reason: stopReason,
    },
    timestamp: timestamp(offsetSeconds),
  };
}

function toolRound(seed, offsetSeconds) {
  const toolUseId = `synthetic-tool-${String(seed).padStart(3, '0')}`;
  return [
    assistantEvent(
      [
        { type: 'text', text: `Synthetic tool request ${seed}` },
        { type: 'tool_use', id: toolUseId, name: seed % 2 === 0 ? 'Read' : 'Bash', input: {} },
      ],
      offsetSeconds,
      seed,
      'tool_use',
    ),
    {
      ...userEvent(
        [{
          type: 'tool_result',
          tool_use_id: toolUseId,
          content: 'Synthetic tool result',
          is_error: seed % 25 === 0,
        }],
        offsetSeconds + 1,
      ),
    },
  ];
}

function generateMockSessions(projectDir) {
  const history = [];
  for (let index = 1; index <= SPEC.mockCount; index += 1) {
    const id = `mock-session-${String(index).padStart(3, '0')}`;
    const offset = index * 10;
    const events = [userEvent(`Synthetic mock request ${index}`, offset)];
    if (index % 4 === 0) {
      events.push(...toolRound(index, offset + 1));
    } else {
      events.push(
        assistantEvent([{ type: 'text', text: `Synthetic mock response ${index}` }], offset + 1, index),
      );
    }
    writeJsonl(path.join(projectDir, `${id}.jsonl`), events);
    history.push({
      synthetic: true,
      sessionId: id,
      project: SPEC.project,
      display: `Synthetic mock session ${index}`,
      timestamp: SPEC.baseTimestampMs + offset * 1000,
    });
  }
  return history;
}

function generateLongSession(projectDir) {
  const events = [];
  for (let round = 1; round <= SPEC.longRounds; round += 1) {
    const offset = 1000 + round * 3;
    events.push(userEvent(`Synthetic long-session round ${round}`, offset));
    if (round % 4 === 0) {
      events.push(...toolRound(round, offset + 1));
    } else {
      events.push(
        assistantEvent([{ type: 'text', text: `Synthetic round response ${round}` }], offset + 1, round),
      );
    }
  }
  writeJsonl(path.join(projectDir, `${SPEC.longSessionId}.jsonl`), events);
  return {
    synthetic: true,
    sessionId: SPEC.longSessionId,
    project: SPEC.project,
    display: `Synthetic long session with ${SPEC.longRounds} rounds`,
    timestamp: SPEC.baseTimestampMs + 1000 * 1000,
  };
}

function generateSessionFixtures(dataDir) {
  const projectDir = path.join(dataDir, 'projects', SPEC.project);
  const historyPath = path.join(dataDir, 'history.jsonl');
  const committedHistory = fs.readFileSync(historyPath, 'utf8').trim().split('\n').map(JSON.parse);
  const generatedHistory = [...generateMockSessions(projectDir), generateLongSession(projectDir)];
  writeJsonl(historyPath, [...committedHistory, ...generatedHistory]);
}

// 原始 Codex 合成来源经正常发现、适配、归一化和 HTTP，不以 API mock 冒充来源链。
function executionSourceRecords() {
  const id = '11111111-2222-4333-8444-555555555555';
  const records = [];
  const add = (type, payload) => records.push({ type, timestamp: timestamp(5000 + records.length), payload });
  add('session_meta', { id, timestamp: timestamp(5000), cwd: '/synthetic/execution', source: 'cli' });
  add('turn_context', { turn_id: 'synthetic-turn', model: 'synthetic-codex' });
  add('response_item', { type: 'message', role: 'user', content: [{ type: 'input_text', text: '检查项目，执行命令并验证结果（全部为合成数据）' }] });
  let action = 0;
  for (let response = 1; response <= 25; response += 1) {
    const count = response === 1 ? 3 : 1;
    add('response_item', { type: 'message', role: 'assistant', content: [{ type: 'output_text', text: `合成模型输出 ${response}：${count === 3 ? '一次下发三个工具' : '执行一个工具'}` }] });
    const ids = [];
    for (let tool = 0; tool < count; tool += 1) {
      action += 1;
      const callId = `synthetic-action-${action}`;
      ids.push(callId);
      const cmd = action === 1 ? 'printf "first"; printf "second"; node --version' : action === 27 ? 'node synthetic-failure.js' : `printf "synthetic action ${action}"`;
      add('response_item', { type: 'function_call', name: 'exec_command', call_id: callId, arguments: JSON.stringify({ cmd }) });
    }
    add('token_usage_record', { response_id: `synthetic-response-${response}`, turn_id: 'synthetic-turn', usage: { input_tokens: 100, cached_input_tokens: 40, cache_write_input_tokens: 0, output_tokens: 20 } });
    for (const callId of ids) {
      const n = Number(callId.split('-').pop());
      add('response_item', { type: 'function_call_output', call_id: callId, output: n === 27 ? 'Synthetic failure: exit 7' : `Synthetic result ${n}` });
      if (n !== 3) add('event_msg', { type: 'exec_command_end', call_id: callId, process_id: `synthetic-process-${n}`, duration: { secs: n === 24 ? 9 : n < 3 ? 0 : 1, nanos: n === 2 ? 500000 : 0 }, exit_code: n === 27 ? 7 : 0, status: n === 27 ? 'failed' : 'completed' });
    }
  }
  return records;
}

module.exports = { SPEC, generateSessionFixtures, executionSourceRecords };
