import importlib
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch, Mock

from pydantic import ValidationError

import tools_start as tools
from app.schemas import PlanIn


class ToolTests(unittest.TestCase):
    def test_cinema_results_preserve_real_map_coordinates(self):
        response = Mock(status_code=200)
        response.json.return_value = {'documents': [{'place_name': '영화관', 'road_address_name': '서울 주소', 'place_url': 'https://place.map.kakao.com/123', 'x': '127.0276', 'y': '37.4979'}]}
        with patch.dict(os.environ, {'KAKAO_REST_API_KEY': 'fixture'}), patch.object(tools.requests, 'get', return_value=response):
            result = tools.TOOLS['search_cinemas'].run(region='강남')
        self.assertTrue(result['ok'])
        self.assertEqual(result['data']['items'][0].get('lat'), 37.4979)
        self.assertEqual(result['data']['items'][0].get('lng'), 127.0276)

    def test_kakao_permission_error_explains_activation_without_raw_details(self):
        response = Mock(status_code=403)
        response.json.return_value = {'code': -3, 'msg': 'secret upstream body'}
        with patch.dict(os.environ, {'KAKAO_REST_API_KEY': 'fixture'}), patch.object(tools.requests, 'get', return_value=response):
            result = tools.TOOLS['search_cinemas'].run(region='강남')
        self.assertIn('403', result['error']['message'])
        self.assertIn('카카오맵', result['error']['message'])
        self.assertNotIn('secret upstream body', str(result))

    def test_catalog_defines_success_and_failure_outputs(self):
        for entry in tools.catalog():
            self.assertEqual(entry.get('tool_type'), 'external_api')
            schema = entry.get('output_schema', {})
            self.assertIn('anyOf', schema)
            self.assertIn('ToolFailure', schema.get('$defs', {}))

    def test_compact_boxoffice_date_is_rejected(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(tools.get_boxoffice('20261120')['error']['code'], 'BAD_ARGUMENT')

    def test_tool_contract_rejects_malformed_success(self):
        from dataclasses import replace
        broken = replace(tools.TOOLS['get_movie_detail'], func=lambda **args: tools.ok({'runtime_minutes': 90}))
        self.assertEqual(broken.run(movie_cd='20240001')['error']['code'], 'UPSTREAM_ERROR')

    def test_three_external_tools_are_registered(self):
        self.assertTrue({'get_boxoffice', 'get_movie_detail', 'search_cinemas'} <= tools.TOOLS.keys())

    def test_invalid_arguments_and_missing_key_are_safe(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(tools.TOOLS['get_movie_detail'].run(movie_cd='20240001')['error']['code'], 'INVALID_KEY')
            self.assertEqual(tools.TOOLS['get_movie_detail'].run(movie_cd='')['error']['code'], 'BAD_ARGUMENT')

    def test_future_boxoffice_date_is_disclosed(self):
        response = Mock(status_code=200)
        response.json.return_value = {'boxOfficeResult': {'dailyBoxOfficeList': [{'movieCd': '20240001', 'movieNm': '테스트', 'rank': '1'}]}}
        with patch.dict(os.environ, {'KOBIS_API_KEY': 'test'}), patch.object(tools.requests, 'get', return_value=response):
            result = tools.get_boxoffice((date.today() + timedelta(days=20)).isoformat())
        self.assertTrue(result['ok'])
        self.assertTrue(result['data']['estimated'])
        self.assertEqual(result['data']['query_date'], (date.today() - timedelta(days=1)).isoformat())
        self.assertEqual(result['data']['items'][0]['movie_cd'], '20240001')

    def test_missing_runtime_is_not_invented(self):
        response = Mock(status_code=200)
        response.json.return_value = {'movieInfoResult': {'movieInfo': {'movieCd': '20240001', 'movieNm': '테스트', 'showTm': '', 'genres': [], 'audits': []}}}
        with patch.dict(os.environ, {'KOBIS_API_KEY': 'test'}), patch.object(tools.requests, 'get', return_value=response):
            result = tools.get_movie_detail('20240001')
        self.assertEqual(result['error']['code'], 'NO_RUNTIME')


class PlanTests(unittest.TestCase):
    def test_blank_movie_and_invalid_interval_are_rejected(self):
        for values in ({'movie_nm': '  ', 'watch_date': '2026-11-21'}, {'movie_nm': '영화', 'watch_date': '2026-11-21', 'start_time': '18:00', 'end_time': '17:00'}):
            with self.assertRaises(ValidationError):
                PlanIn(**values)

    def test_persistence_overlap_and_adjacency(self):
        from app import store
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'PLANNER_DB_PATH': str(Path(folder) / 'plans.db')}):
            p = PlanIn(movie_nm='A', watch_date='2026-11-21', start_time='15:00', end_time='17:00')
            a = store.save_plan(p)
            b = store.save_plan(p.model_copy(update={'movie_nm': 'B', 'start_time': '16:00', 'end_time': '18:00'}))
            c = store.save_plan(p.model_copy(update={'movie_nm': 'C', 'start_time': '18:00', 'end_time': '19:00'}))
            self.assertEqual(b['overlap_plan_ids'], [a['plan_id']])
            self.assertEqual(c['overlap_plan_ids'], [])
            importlib.reload(store)
            self.assertEqual(len(store.list_plans()), 3)
            self.assertTrue(store.get_plan(a['plan_id'])['created_at'])


class EventTests(unittest.TestCase):
    def test_failed_analysis_has_safe_end_event(self):
        from app.agent import MovieAgent
        from app.events import EventBus
        from app.llm import AgentConfigurationError

        def broken_analyzer(*args):
            raise AgentConfigurationError('sensitive upstream detail')

        agent = MovieAgent(analyzer=broken_analyzer, event_bus=EventBus())
        state = agent.initial_state('s1', '조회', {})
        with self.assertRaises(AgentConfigurationError):
            agent.analyze(state)
        self.assertEqual([e['type'] for e in state['events']], ['stage_start', 'stage_end'])
        self.assertEqual(state['events'][-1]['data']['status'], 'failed')
        self.assertNotIn('sensitive upstream detail', str(state['events']))

    def test_broken_subscriber_does_not_stop_publication(self):
        from app.events import EventBus
        bus = EventBus()
        bus.subscribe(lambda event: 1 / 0)
        event = bus.emit('session-1', 'run-1', 'stage_start', {'stage': 'analyze'})
        self.assertEqual(event['session_id'], 'session-1')

    def test_logs_keep_order_and_sessions_separate_then_delete(self):
        from app import store
        from app.events import EventBus, LoggingAgent
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'PLANNER_DB_PATH': str(Path(folder) / 'logs.sqlite')}):
            bus = EventBus()
            bus.subscribe(LoggingAgent())
            bus.emit('s1', 'r1', 'stage_start', {'stage': 'analyze'})
            bus.emit('s2', 'r2', 'stage_start', {'stage': 'analyze'})
            bus.emit('s1', 'r1', 'stage_end', {'stage': 'analyze'})
            self.assertEqual([event['type'] for event in store.get_logs('s1')], ['stage_start', 'stage_end'])
            self.assertEqual(len(store.get_logs('s2')), 1)
            self.assertTrue(store.delete_logs('s1'))
            self.assertEqual(store.get_logs('s1'), [])
            self.assertEqual(len(store.list_logs()), 1)


class AgentTests(unittest.TestCase):
    def test_partial_failure_does_not_block_next_candidate_batch(self):
        state, _ = self.run_agent({'intent': 'plan', 'conditions': {'watch_date': '2026-11-21', 'start_time': '15:00', 'deadline': '17:00'}, 'reason': 'partial failure', 'tool_names': ['get_boxoffice', 'get_movie_detail']}, ['upstream', 180, 180, 90])
        self.assertEqual(state['replans'], 1)
        self.assertEqual(state['recommendations'][0]['movie_nm'], 'M4')

    def test_cinema_search_without_region_asks_for_region(self):
        state, calls = self.run_agent({'intent': 'facts', 'conditions': {}, 'reason': 'missing region', 'tool_names': ['search_cinemas']}, [])
        self.assertTrue(state['question'])
        self.assertEqual(calls, [])

    def test_combined_movie_and_cinema_request_asks_for_missing_region(self):
        state, calls = self.run_agent({'intent': 'plan', 'conditions': {'watch_date': '2026-11-21', 'start_time': '15:00'}, 'reason': 'missing region', 'tool_names': ['get_boxoffice', 'get_movie_detail', 'search_cinemas']}, [90])
        self.assertTrue(state['question'])
        self.assertEqual(calls, [])

    def test_same_day_plan_excludes_midnight_overflow(self):
        state, _ = self.run_agent({'intent': 'plan', 'conditions': {'watch_date': '2026-11-21', 'start_time': '23:00'}, 'reason': 'late', 'tool_names': ['get_boxoffice', 'get_movie_detail']}, [90])
        self.assertEqual(state['recommendations'], [])
        self.assertTrue(state['excluded'][0]['reason'])

    def test_exception_and_malformed_tool_results_are_logged_safely(self):
        from app.agent import MovieAgent
        from app.events import EventBus
        for runner in (lambda *a, **k: 1 / 0, lambda *a, **k: None):
            with self.subTest(runner=runner):
                agent = MovieAgent(tool_runner=runner, event_bus=EventBus())
                state = agent.initial_state('s1', '조회', {})
                result = agent.call(state, 'get_boxoffice', {})
                self.assertFalse(result['ok'])
                self.assertEqual(state['errors'][0]['code'], 'UPSTREAM_ERROR')
                self.assertEqual(state['events'][-1]['type'], 'tool_response')

    def test_greeting_preserves_last_plan_for_different_movie_followup(self):
        from app import store
        from app.agent import MovieAgent
        from app.events import EventBus
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'PLANNER_DB_PATH': str(Path(folder) / 'memory.db')}):
            store.save_memory('s1', {'conditions': {'watch_date': '2026-11-21', 'start_time': '15:00'}, 'recommendations': [{'movie_cd': '00000001', 'movie_nm': 'M1'}]})
            agent = MovieAgent(analyzer=lambda *args: {'intent': 'help', 'reason': 'greeting'}, event_bus=EventBus())
            agent.run('s1', '고마워')
            self.assertEqual(store.get_memory('s1')['recommendations'][0]['movie_cd'], '00000001')

    def run_agent(self, analysis, runtimes, previous=None):
        from app.agent import MovieAgent
        from app.events import EventBus
        calls = []

        def external(name, **args):
            calls.append((name, args))
            if name == 'get_boxoffice':
                return tools.ok({'items': [{'movie_cd': f'{i:08}', 'movie_nm': f'M{i}'} for i in range(1, len(runtimes) + 1)], 'query_date': '2026-11-17', 'estimated': True})
            if name == 'get_movie_detail':
                i = int(args['movie_cd'])
                value = runtimes[i - 1]
                if value == 'upstream':
                    return tools.fail('UPSTREAM_ERROR', 'detail lookup failed')
                if value is None:
                    return tools.fail('NO_RUNTIME', 'unknown runtime')
                return tools.ok({'movie_cd': args['movie_cd'], 'movie_nm': f'M{i}', 'runtime_minutes': value, 'genres': [], 'ratings': [], 'source': 'fixture'})
            return tools.fail('INVALID_KEY', 'missing cinema key')

        agent = MovieAgent(analyzer=lambda message, memory: analysis, tool_runner=external, event_bus=EventBus())
        state = agent.initial_state('s1', '영화 추천', previous or {})
        state = agent.analyze(state)
        for _ in range(5):
            state = agent.plan(state)
            state = agent.execute(state)
            state = agent.judge(state)
            if not state['retry']:
                break
        state = agent.respond(state)
        return state, calls

    def test_replans_reuse_candidates_and_keep_cinema_failure_partial(self):
        state, calls = self.run_agent({'intent': 'plan', 'conditions': {'watch_date': '2026-11-21', 'start_time': '15:00', 'deadline': '17:00', 'region': '강남'}, 'reason': 'explicit', 'tool_names': ['get_boxoffice', 'get_movie_detail', 'search_cinemas']}, [180, 180, 180, 90])
        self.assertEqual(state['replans'], 1)
        self.assertEqual(state['recommendations'][0]['latest_start'], '15:30')
        self.assertEqual(len([v for v in calls if v[0] == 'get_boxoffice']), 1)
        self.assertEqual(len([v for v in calls if v[0] == 'search_cinemas']), 1)
        self.assertEqual(state['errors'][0]['code'], 'INVALID_KEY')

    def test_replan_limit_and_no_duplicate_detail_calls(self):
        state, calls = self.run_agent({'intent': 'plan', 'conditions': {'watch_date': '2026-11-21', 'start_time': '15:00', 'deadline': '15:30'}, 'reason': 'explicit', 'tool_names': ['get_boxoffice', 'get_movie_detail']}, [180] * 15)
        self.assertEqual(state['replans'], 3)
        self.assertEqual(len(state['recommendations']), 0)
        codes = [args['movie_cd'] for name, args in calls if name == 'get_movie_detail']
        self.assertEqual(len(codes), len(set(codes)))

    def test_followup_keeps_unchanged_conditions(self):
        state, _ = self.run_agent({'intent': 'plan', 'conditions': {'deadline': '18:00'}, 'reason': 'followup', 'tool_names': ['get_boxoffice', 'get_movie_detail']}, [90], {'conditions': {'watch_date': '2026-11-21', 'start_time': '15:00', 'region': '강남'}})
        self.assertEqual(state['conditions']['start_time'], '15:00')
        self.assertEqual(state['conditions']['deadline'], '18:00')
        self.assertEqual(state['conditions']['region'], '강남')

    def test_missing_start_asks_before_any_tool_call(self):
        state, calls = self.run_agent({'intent': 'plan', 'conditions': {'watch_date': '2026-11-21', 'deadline': '19:00'}, 'reason': 'missing start', 'tool_names': ['get_boxoffice']}, [90])
        self.assertEqual(calls, [])
        self.assertEqual(state['recommendations'], [])

    def test_greeting_needs_no_tools(self):
        state, calls = self.run_agent({'intent': 'help', 'conditions': {}, 'reason': 'greeting', 'tool_names': []}, [])
        self.assertEqual(calls, [])
        self.assertTrue(state['answer'])

    def test_cinema_only_question_does_not_lookup_movies(self):
        state, calls = self.run_agent({'intent': 'facts', 'conditions': {'region': '강남'}, 'reason': 'cinema only', 'tool_names': ['search_cinemas']}, [90])
        self.assertEqual([name for name, args in calls], ['search_cinemas'])

    def test_explicit_null_removes_previous_constraint(self):
        state, _ = self.run_agent({'intent': 'plan', 'conditions': {'deadline': None, 'genre': None}, 'reason': 'remove filters', 'tool_names': ['get_boxoffice', 'get_movie_detail']}, [90], {'conditions': {'watch_date': '2026-11-21', 'start_time': '15:00', 'deadline': '15:30', 'genre': '액션'}})
        self.assertNotIn('deadline', state['conditions'])
        self.assertNotIn('genre', state['conditions'])
        self.assertEqual(len(state['recommendations']), 1)

    def test_changed_movie_title_clears_stale_movie_code(self):
        state, _ = self.run_agent({'intent': 'plan', 'conditions': {'movie_nm': 'M2'}, 'reason': 'changed movie', 'tool_names': ['get_boxoffice', 'get_movie_detail']}, [90, 90], {'conditions': {'watch_date': '2026-11-21', 'start_time': '15:00', 'movie_cd': '00000001', 'movie_nm': 'M1'}})
        self.assertEqual(state['recommendations'][0]['movie_nm'], 'M2')

    def test_different_movie_clears_previous_pin_and_excludes_recommendation(self):
        state, _ = self.run_agent({'intent': 'plan', 'conditions': {}, 'different_movie': True, 'reason': 'different movie', 'tool_names': ['get_boxoffice', 'get_movie_detail']}, [90, 90], {'conditions': {'watch_date': '2026-11-21', 'start_time': '15:00', 'movie_cd': '00000001'}, 'recommendations': [{'movie_cd': '00000001'}]})
        self.assertEqual(state['recommendations'][0]['movie_cd'], '00000002')

    def test_boxoffice_facts_follow_actual_plan_despite_old_movie_pin(self):
        state, calls = self.run_agent({'intent': 'facts', 'conditions': {}, 'reason': 'boxoffice', 'tool_names': ['get_boxoffice']}, [90, 90], {'conditions': {'movie_cd': '00000001', 'movie_nm': 'M1'}})
        self.assertEqual([name for name, args in calls], ['get_boxoffice'])
        self.assertIn('M2', state['answer'])

    def test_one_upstream_detail_failure_does_not_block_other_movies(self):
        state, _ = self.run_agent({'intent': 'plan', 'conditions': {'watch_date': '2026-11-21', 'start_time': '15:00', 'deadline': '17:00'}, 'reason': 'partial failure', 'tool_names': ['get_boxoffice', 'get_movie_detail']}, ['upstream', 90])
        self.assertEqual(state['recommendations'][0]['movie_nm'], 'M2')


class APITests(unittest.TestCase):
    def test_map_config_exposes_only_separate_public_javascript_key(self):
        with patch.dict(os.environ, {'KAKAO_JAVASCRIPT_KEY': 'public-js-key', 'KAKAO_REST_API_KEY': 'private-rest-key', 'OPENAI_API_KEY': 'private-llm-key'}):
            status, result = self.request('GET', '/api/maps/config')
        self.assertEqual(status, 200)
        self.assertEqual(result.get('javascript_key'), 'public-js-key')
        self.assertNotIn('private', str(result))
        with patch.dict(os.environ, {'KAKAO_JAVASCRIPT_KEY': 'same-key', 'KAKAO_REST_API_KEY': 'same-key'}):
            self.assertIsNone(self.request('GET', '/api/maps/config')[1]['javascript_key'])

    def test_direct_cinema_search_works_without_llm(self):
        response = Mock(status_code=200)
        response.json.return_value = {'documents': [{'place_name': '검색 영화관', 'road_address_name': '주소', 'place_url': 'https://place.map.kakao.com/123', 'x': '127.0276', 'y': '37.4979'}]}
        with patch.dict(os.environ, {'KAKAO_REST_API_KEY': 'fixture', 'OPENAI_API_KEY': ''}), patch.object(tools.requests, 'get', return_value=response):
            status, result = self.request('GET', '/api/cinemas?region=Gangnam')
        self.assertEqual(status, 200)
        self.assertTrue(result.get('ok'))
        self.assertEqual(result['data']['items'][0]['name'], '검색 영화관')
        self.assertEqual(self.request('GET', '/api/cinemas?region=')[0], 422)

    def test_chat_graph_tools_memory_and_persisted_logs_work_together(self):
        import json

        def llm_response(conditions):
            response = Mock(status_code=200)
            analysis = {'intent': 'plan', 'conditions': conditions, 'reason': '고정 분석',
                        'tool_names': ['get_boxoffice', 'get_movie_detail', 'search_cinemas']}
            response.json.return_value = {'choices': [{'message': {'content': json.dumps(analysis)}}]}
            return response

        def upstream(url, **kwargs):
            response = Mock(status_code=200)
            if 'searchDailyBoxOfficeList' in url:
                response.json.return_value = {'boxOfficeResult': {'dailyBoxOfficeList': [{'movieCd': '20240001', 'movieNm': '테스트 영화', 'rank': '1'}]}}
            elif 'searchMovieInfo' in url:
                self.assertEqual(kwargs['params']['movieCd'], '20240001')
                response.json.return_value = {'movieInfoResult': {'movieInfo': {'movieCd': '20240001', 'movieNm': '테스트 영화', 'showTm': '90', 'genres': [{'genreNm': '드라마'}], 'audits': [{'watchGradeNm': '전체관람가'}]}}}
            else:
                self.assertEqual(kwargs['params']['query'], '강남 영화관')
                response.json.return_value = {'documents': [{'place_name': '테스트 영화관', 'road_address_name': '고정 주소', 'place_url': 'https://example.com/cinema'}]}
            return response

        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
            'PLANNER_DB_PATH': str(Path(folder) / 'integration.db'), 'OPENAI_API_KEY': 'fixture',
            'OPENAI_MODEL': 'fixture', 'KOBIS_API_KEY': 'fixture', 'KAKAO_REST_API_KEY': 'fixture',
        }), patch('app.llm.requests.post', side_effect=[
            llm_response({'watch_date': '2026-11-21', 'start_time': '15:00', 'deadline': '17:00', 'region': '강남'}),
            llm_response({'deadline': '16:00'}),
        ]), patch.object(tools.requests, 'get', side_effect=upstream):
            status, first = self.request('POST', '/api/chat', {'message': '2026-11-21 오후 3시~5시 강남 영화'})
            self.assertEqual(status, 200)
            self.assertEqual(first['recommendations'][0]['latest_start'], '15:30')
            self.assertEqual(first['cinemas'][0]['name'], '테스트 영화관')
            session = first['session_id']
            status, followup = self.request('POST', '/api/chat', {'message': '종료 제한만 오후 4시로', 'session_id': session})
            self.assertEqual(status, 200)
            self.assertEqual(followup['conditions']['start_time'], '15:00')
            self.assertEqual(followup['conditions']['deadline'], '16:00')
            self.assertEqual(followup['recommendations'], [])
            status, detail = self.request('GET', f'/api/logs/{session}')
            self.assertEqual(status, 200)
            self.assertEqual(detail['events'], first['events'] + followup['events'])
            self.assertEqual(self.request('DELETE', f'/api/logs/{session}')[0], 204)
            self.assertEqual(self.request('GET', f'/api/logs/{session}')[0], 404)

    def request(self, method, path, body=None):
        import asyncio
        import json
        from app.main import app
        from urllib.parse import urlsplit
        parsed = urlsplit(path)
        result = []
        payload = json.dumps(body).encode() if body is not None else b''
        async def receive():
            return {'type': 'http.request', 'body': payload, 'more_body': False}
        async def send(message):
            result.append(message)
        scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': method, 'scheme': 'http', 'path': parsed.path, 'raw_path': parsed.path.encode(), 'query_string': parsed.query.encode(), 'root_path': '', 'headers': [(b'content-type', b'application/json')], 'server': ('test', 80), 'client': ('test', 1)}
        asyncio.run(app(scope, receive, send))
        status = next(item['status'] for item in result if item['type'] == 'http.response.start')
        raw = b''.join(item.get('body', b'') for item in result if item['type'] == 'http.response.body')
        return status, json.loads(raw) if raw else None

    def test_crud_and_overlap_are_exposed_through_original_api(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'PLANNER_DB_PATH': str(Path(folder) / 'db.sqlite')}):
            payload = {'movie_nm': '영화', 'watch_date': '2026-11-21', 'start_time': '15:00', 'end_time': '17:00'}
            status, a = self.request('POST', '/api/plans', payload)
            self.assertEqual(status, 201)
            self.assertIn('created_at', a)
            _, b = self.request('POST', '/api/plans', payload)
            self.assertEqual(b['overlap_plan_ids'], [a['plan_id']])
            status, updated = self.request('PUT', f"/api/plans/{a['plan_id']}", {**payload, 'movie_nm': '수정'})
            self.assertEqual((status, updated['movie_nm']), (200, '수정'))
            self.assertEqual(self.request('DELETE', f"/api/plans/{a['plan_id']}")[0], 204)
            self.assertEqual(self.request('GET', f"/api/plans/{a['plan_id']}")[0], 404)

    def test_chat_route_and_logs_are_available(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'PLANNER_DB_PATH': str(Path(folder) / 'db.sqlite')}):
            self.assertEqual(self.request('POST', '/api/chat', {'message': ''})[0], 422)
            self.assertEqual(self.request('GET', '/api/logs'), (200, []))
            self.assertEqual(self.request('GET', '/api/logs/missing')[0], 404)
            self.assertEqual(self.request('PUT', '/api/logs/missing', {})[0], 405)

    def test_missing_agent_configuration_is_safe(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'PLANNER_DB_PATH': str(Path(folder) / 'db.sqlite'), 'OPENAI_API_KEY': '', 'OPENAI_MODEL': ''}):
            status, body = self.request('POST', '/api/chat', {'message': '안녕'})
            self.assertEqual(status, 503)
            self.assertIsInstance(body['detail'], str)


class GraphTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('langgraph'), 'LangGraph is not installed in this environment')
    def test_real_graph_returns_a_greeting(self):
        from app.agent import MovieAgent
        from app.events import EventBus
        agent = MovieAgent(analyzer=lambda message, memory: {'intent': 'help', 'reason': 'greeting'}, event_bus=EventBus())
        result = agent.build_graph().invoke(agent.initial_state('test', '안녕', {}))
        self.assertTrue(result['answer'])
        self.assertEqual(result['replans'], 0)


class FrontendServerTests(unittest.TestCase):
    def test_only_frontend_is_served_and_internal_files_are_not_exposed(self):
        from http.server import ThreadingHTTPServer
        from threading import Thread
        from urllib.error import HTTPError
        from urllib.request import urlopen
        import serve_frontend
        server = ThreadingHTTPServer(('127.0.0.1', 0), serve_frontend.FrontendHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            with urlopen(base + '/') as response:
                self.assertIn(b'DateLog', response.read())
            for path in ['/.env', '/.env.example', '/data/planner.db', '/app/main.py', '/%2eenv', '/..%2f.env']:
                with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                    urlopen(base + path)
                self.assertEqual(error.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
