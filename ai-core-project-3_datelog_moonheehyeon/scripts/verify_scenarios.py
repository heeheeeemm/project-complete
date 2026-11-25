"""실제 LangGraph/SQLite 검증. LLM/외부 API 경계만 고정 응답으로 대체한다.

실행: python -m scripts.verify_scenarios --output docs/sample-execution.json
"""
import argparse
import json
import os
import tempfile
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from app import store
from app.agent import MovieAgent
from app.events import EventBus, LoggingAgent
from tools_start import TOOLS, fail, ok


def verify():
    records = []
    scenarios = [
        ('single_pass', '2026-11-21 오후 3시 이후, 오후 5시 전에 끝나는 영화', [90], 0, 1, False),
        ('replan', '같은 시간 조건에서 다른 후보도 찾아 줘', [180, 180, 180, 90], 1, 1, False),
        ('limit', '2026-11-21 오후 3시부터 3시 30분 안에 끝나는 영화', [180] * 15, 3, 0, False),
        ('partial_failure', '조회 하나가 실패해도 다른 영화와 강남 영화관을 찾아 줘', ['upstream', 180, 180, 90], 1, 1, True),
        ('no_tool', '안녕, 사용법을 알려 줘', [], 0, 0, False),
    ]
    with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
        'PLANNER_DB_PATH': str(Path(folder) / 'scenarios.db'), 'MAX_REPLANS': '3',
    }):
        for name, message, runtimes, replans, accepted, cinema in scenarios:
            conditions = {'watch_date': '2026-11-21', 'start_time': '15:00', 'deadline': '15:30' if name == 'limit' else '17:00'}
            selected = ['get_boxoffice', 'get_movie_detail']
            if cinema:
                conditions['region'] = '강남'
                selected.append('search_cinemas')
            analysis = {'intent': 'help' if name == 'no_tool' else 'plan', 'reason': '명시된 고정 분석 데이터',
                        'conditions': {} if name == 'no_tool' else conditions,
                        'tool_names': [] if name == 'no_tool' else selected}
            calls = []

            def external(tool, **args):
                calls.append({'tool': tool, 'arguments': args})
                if tool == 'get_boxoffice':
                    result = ok({'items': [{'movie_cd': f'{i:08}', 'movie_nm': f'M{i}', 'rank': str(i)} for i in range(1, len(runtimes) + 1)],
                                 'requested_date': args['target_date'], 'query_date': '2026-11-19', 'estimated': True, 'source': '고정 KOBIS 응답 (실제 조회 아님)'})
                elif tool == 'get_movie_detail':
                    i = int(args['movie_cd'])
                    runtime = runtimes[i - 1]
                    result = fail('UPSTREAM_ERROR', '고정 상세 조회 실패') if runtime == 'upstream' else ok({
                        'movie_cd': args['movie_cd'], 'movie_nm': f'M{i}', 'runtime_minutes': runtime,
                        'genres': ['드라마'], 'ratings': ['전체관람가'], 'source': '고정 KOBIS 상세 응답 (실제 조회 아님)',
                    })
                else:
                    result = fail('INVALID_KEY', '고정 영화관 키 누락 시나리오')
                return TOOLS[tool].result_adapter.validate_python(result).model_dump(mode='json')

            bus = EventBus()
            bus.subscribe(LoggingAgent())
            agent = MovieAgent(analyzer=lambda *args: analysis, tool_runner=external, event_bus=bus)
            started = perf_counter()
            result = agent.run(name, message)
            elapsed = round((perf_counter() - started) * 1000, 2)
            expected = {'replans': replans, 'recommendations': accepted, 'error_codes': ['UPSTREAM_ERROR', 'INVALID_KEY'] if cinema else []}
            actual = {'replans': result['replans'], 'recommendations': len(result['recommendations']), 'error_codes': [e['code'] for e in result['errors']]}
            assert actual == expected, (name, actual, expected)
            assert store.get_logs(name) == result['events'], name
            request_keys = [json.dumps(call, sort_keys=True) for call in calls]
            assert len(request_keys) == len(set(request_keys)), name
            records.append({'scenario': name, 'request': message, 'analysis_fixture': analysis, 'expected': expected,
                            'actual': actual, 'difference': None, 'elapsed_ms': elapsed, 'tool_calls': calls, **result})
    return {'notice': '실제 LangGraph와 SQLite로 실행했습니다. LLM 분석/외부 API 응답은 고정 데이터이며 실제 외부 연동 기록이 아닙니다. 상한 시나리오는 반복 상한 검증을 위한 가상 후보 15개를 사용합니다.',
            'records': records}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = verify()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(f"Verified {len(report['records'])} scenarios with real LangGraph and SQLite.")
