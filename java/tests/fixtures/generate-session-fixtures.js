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

module.exports = { SPEC, generateSessionFixtures };
