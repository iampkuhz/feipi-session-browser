#!/usr/bin/env python3
"""Generate 43 mock sessions for the hifi fixture.

43 sessions at page_size=20 gives exactly 3 pages (20 + 20 + 3),
enough to test pagination (next from page 1 -> page 2).
"""

import json
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent.parent / 'tests' / 'fixtures' / 'session_hifi_fixture'
PROJECT = 'test-hifi-project'

AGENTS = ['claude_code', 'codex', 'qoder']
MODELS = [
    'claude-sonnet-4-20250514',
    'claude-opus-4-20250514',
    'gpt-4o',
    'qwen-max',
]
STATUSES = ['success', 'failed', 'error', 'stopped']
PROJECTS = [
    'test-hifi-project',
    'project-alpha',
    'project-beta',
    'project-gamma',
]

TITLES = [
    'Implement token usage visualization',
    'Fix session detail layout regression',
    'Add agent run duration tracking',
    'Refactor token normalizer module',
    'Improve dashboard metric cards',
    'Fix pagination off-by-one bug',
    'Add dark mode support',
    'Optimize database query performance',
    'Implement session search feature',
    'Add project-level aggregation',
    'Fix tool call linking logic',
    'Add session export to MHTML',
    'Improve error page UX',
    'Add keyboard navigation support',
    'Refactor CSS architecture',
    'Implement session comparison view',
    'Add token cost estimation',
    'Fix subagent run tracking',
    'Improve session list sort',
    'Add session tag filtering',
    'Implement anomaly detection',
    'Fix hero section responsiveness',
    'Add session bookmarking',
    'Optimize template rendering',
    'Implement session diff view',
    'Add agent model matrix',
    'Fix trace panel overflow',
    'Add session replay feature',
    'Improve payload viewer',
    'Implement session archiving',
    'Add project health dashboard',
    'Fix session detail tabs',
    'Add batch session operations',
    'Implement timeline compression',
    'Add session activity heatmap',
    'Fix pagination state management',
    'Add session duration histogram',
    'Implement custom filter presets',
    'Add session quality metrics',
    'Fix CSS loading order issue',
    'Implement session export wizard',
    'Add agent performance trends',
    'Fix mobile responsive layout',
]

assert len(TITLES) == 43, f'Need 43 titles, got {len(TITLES)}'

# Base timestamp: 2026-04-24 10:00:00 UTC
BASE_TS = 1713952800000

history_lines = []
projects_dir = FIXTURE_DIR / 'projects' / PROJECT
projects_dir.mkdir(parents=True, exist_ok=True)

for i in range(43):
    sid = f'mock-session-{i + 1:03d}'
    ts = BASE_TS + i * 3600000  # 1 hour apart
    agent = AGENTS[i % len(AGENTS)]
    model = MODELS[i % len(MODELS)]
    status = STATUSES[i % len(STATUSES)]
    proj = PROJECTS[i % len(PROJECTS)]
    title = TITLES[i]

    input_tokens = 5000 + i * 200
    output_tokens = 800 + i * 50
    cache_read = i * 3000
    cache_write = i * 1500
    rounds = 5 + i % 15
    tools = 10 + i * 2
    duration_sec = 120 + i * 10

    history_lines.append(
        json.dumps(
            {
                'sessionId': sid,
                'project': proj,
                'display': title,
                'timestamp': ts,
            }
        )
    )

    # Write minimal JSONL event file
    event_lines = [
        json.dumps(
            {
                'type': 'user',
                'message': {'role': 'user', 'content': title},
                'timestamp': f'2026-04-24T10:{i % 60:02d}:00.000Z',
            }
        ),
        json.dumps(
            {
                'type': 'assistant',
                'message': {
                    'model': model,
                    'role': 'assistant',
                    'content': [{'type': 'text', 'text': f'Working on task {i + 1}...'}],
                    'usage': {
                        'input_tokens': input_tokens,
                        'output_tokens': output_tokens,
                        'cache_read_input_tokens': cache_read,
                        'cache_creation_input_tokens': cache_write,
                    },
                    'stop_reason': 'end_turn',
                },
                'timestamp': f'2026-04-24T10:{i % 60:02d}:05.000Z',
            }
        ),
    ]

    # If status is failed, add a tool error
    if status == 'failed':
        event_lines.append(
            json.dumps(
                {
                    'type': 'assistant',
                    'message': {
                        'model': model,
                        'role': 'assistant',
                        'content': [
                            {
                                'type': 'tool_use',
                                'name': 'Bash',
                                'input': {'command': 'exit 1'},
                                'id': f'tool_err_{i}',
                            }
                        ],
                        'usage': {
                            'input_tokens': input_tokens + 100,
                            'output_tokens': 50,
                        },
                        'stop_reason': 'tool_use',
                    },
                    'timestamp': f'2026-04-24T10:{i % 60:02d}:10.000Z',
                }
            )
        )
        event_lines.append(
            json.dumps(
                {
                    'type': 'user',
                    'message': {
                        'role': 'user',
                        'content': [
                            {
                                'tool_use_id': f'tool_err_{i}',
                                'type': 'tool_result',
                                'content': [{'type': 'text', 'text': 'command failed'}],
                                'is_error': True,
                            }
                        ],
                    },
                    'timestamp': f'2026-04-24T10:{i % 60:02d}:15.000Z',
                }
            )
        )

    (projects_dir / f'{sid}.jsonl').write_text('\n'.join(event_lines) + '\n', encoding='utf-8')

# Write history.jsonl
(FIXTURE_DIR / 'history.jsonl').write_text('\n'.join(history_lines) + '\n', encoding='utf-8')

print(
    f'Generated 43 sessions ({len(history_lines)} history entries, {len(list(projects_dir.glob("*.jsonl")))} event files)'
)
