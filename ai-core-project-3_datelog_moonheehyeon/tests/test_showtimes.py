"""CGV 응답 경계와 실제 회차 기반 추천 회귀 테스트."""
import tempfile
import unittest
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import requests


def response(data=None, status=200):
    result = Mock(status_code=status)
    result.json.return_value = {'statusCode': 0, 'data': data}
    return result


def sites():
    return response({'regionInfo': [{'comCdval': '07', 'comCdvalNm': '부산/울산'}, {'comCdval': '01', 'comCdvalNm': '서울'}],
                     'siteInfo': [{'siteNo': '0005', 'siteNm': '서면', 'regnGrpCd': '07'},
                                  {'siteNo': '0285', 'siteNm': '서면삼정타워', 'regnGrpCd': '07'},
                                  {'siteNo': '0056', 'siteNm': '강남', 'regnGrpCd': '01'}]})


def row(start='1800', seats='12', **changes):
    return {'siteNo': '0005', 'siteNm': 'CGV 서면', 'scnYmd': '20261121', 'scnsNo': '003',
            'scnSseq': start, 'scnsNm': '3관', 'movNo': '30001643', 'movNm': '폭설',
            'scnsrtTm': start, 'scnendTm': '1940', 'frSeatCnt': seats, 'stcnt': '165',
            'cntlYn': 'N', 'movkndDsplNm': '2D', **changes}


class ShowtimeClientTests(unittest.TestCase):
    def search(self, replies, **changes):
        from app.showtimes import get_showtimes
        values = dict(region='부산 서면', movie_nm='폭설', watch_date='2026-11-21', start_time='18:00')
        with patch('app.showtimes.requests.get', side_effect=replies) as request:
            return get_showtimes(**{**values, **changes}), request

    def test_requested_movie_time_and_seats_are_from_actual_rows(self):
        result, request = self.search([sites(), response([row('1759'), row(), row('2000', '3', scnendTm='2140'),
                                                        row('2100', movNm='폭설의 밤')]), response([])])
        self.assertTrue(result['ok'], result)
        items = result['data']['items']
        self.assertEqual([item['start_time'] for item in items], ['18:00', '20:00'])
        self.assertEqual([item['remaining_seats'] for item in items], [12, 3])
        self.assertTrue(result['data']['complete'])
        self.assertEqual(len(result['data']['checked_theaters']), 2)
        self.assertEqual(request.call_count, 3)

    def test_sold_out_and_unknown_are_not_available(self):
        result, _ = self.search([sites(), response([row(seats='0'), row('2000', None, scnendTm='2140')]), response([])])
        self.assertEqual([x['availability'] for x in result['data']['items']], ['sold_out', 'unknown'])
        self.assertIsNone(result['data']['items'][1]['remaining_seats'])

    def test_access_denial_is_not_an_empty_success(self):
        result, _ = self.search([sites(), response(status=403), response(status=403)])
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'ACCESS_DENIED')

    def test_partial_failure_keeps_results_and_is_explicit(self):
        result, _ = self.search([sites(), response([row()]), response(status=403)])
        self.assertTrue(result['ok'])
        self.assertFalse(result['data']['complete'])
        self.assertEqual(len(result['data']['warnings']), 1)

    def test_valid_empty_data_is_distinct_from_schema_change(self):
        empty, _ = self.search([sites(), response([]), response([])])
        self.assertTrue(empty['ok'])
        self.assertEqual(empty['data']['items'], [])
        broken, _ = self.search([sites(), response({'unexpected': []}), response({'unexpected': []})])
        self.assertFalse(broken['ok'])
        self.assertEqual(broken['error']['code'], 'UPSTREAM_ERROR')

    def test_inconsistent_date_or_negative_seats_are_not_published(self):
        for bad in (row(scnYmd='20261120'), row(seats='-1'), row(seats='166')):
            with self.subTest(bad=bad):
                result, _ = self.search([sites(), response([bad]), response([bad])])
                self.assertFalse(result['ok'])

    def test_extended_clock_keeps_actual_calendar_day(self):
        result, _ = self.search([sites(), response([row('2510', scnendTm='2649')]), response([])])
        item = result['data']['items'][0]
        self.assertEqual(item['watch_date'], '2026-11-22')
        self.assertEqual(item['start_time'], '01:10')
        self.assertEqual(item['start_label'], '익일 01:10')
        self.assertEqual(item['end_time'], '02:49')

    def test_deadline_compares_actual_end_and_buffer(self):
        result, _ = self.search([sites(), response([row(), row('1900', scnendTm='2040')]), response([])], deadline='20:00', buffer_minutes=10)
        self.assertEqual(len(result['data']['items']), 1)

    def test_timeout_is_safe_and_unknown_theater_does_not_guess(self):
        result, _ = self.search([requests.Timeout('sensitive')])
        self.assertEqual(result['error']['code'], 'TIMEOUT')
        self.assertNotIn('sensitive', str(result))
        result, request = self.search([sites()], region='부산 강남')
        self.assertFalse(result['ok'])
        self.assertEqual(request.call_count, 1)


class ShowtimeRequestTests(unittest.TestCase):
    def parse(self, message, memory=None):
        from app.showtime_request import parse_showtime_request
        return parse_showtime_request(message, memory or {}, today=date(2026, 11, 20))

    def test_exact_user_example_without_llm(self):
        result = self.parse('나는 내일 오후 6시 이후에 부산 서면에서 <폭설>이라는 영화를 보고싶어')
        self.assertEqual(result['intent'], 'showtimes')
        self.assertEqual(result['conditions'], {'watch_date': '2026-11-21', 'start_time': '18:00', 'region': '부산 서면', 'movie_nm': '폭설'})
        self.assertEqual(result['tool_names'], ['get_showtimes'])

    def test_reordered_request_and_followup(self):
        result = self.parse('부산 서면에서 내일 오후 7시 30분 이후에 "폭설" 보고 싶어')
        self.assertEqual(result['conditions']['region'], '부산 서면')
        self.assertEqual(result['conditions']['start_time'], '19:30')
        followup = self.parse('모레 오후 8시 이후로 바꿔줘', {'intent': 'showtimes', 'conditions': result['conditions']})
        self.assertEqual(followup['conditions'], {'watch_date': '2026-11-22', 'start_time': '20:00'})

    def test_title_without_brackets_does_not_absorb_date_or_region(self):
        result = self.parse('나는 내일 오후 6시 이후에 부산 서면에서 폭설이라는 영화를 보고싶어')
        self.assertEqual(result['conditions']['movie_nm'], '폭설')
        self.assertEqual(result['conditions']['region'], '부산 서면')

    def test_followup_can_complete_a_missing_region_without_llm(self):
        result = self.parse('부산 서면에서', {'intent': 'showtimes', 'conditions': {'movie_nm': '폭설'}})
        self.assertEqual(result['conditions'], {'region': '부산 서면'})

    def test_followup_time_change_without_after_does_not_keep_old_time(self):
        result = self.parse('모레 오후 8시로 바꿔줘', {'intent': 'showtimes', 'conditions': {'start_time': '18:00'}})
        self.assertEqual(result['conditions']['start_time'], '20:00')

    def test_before_time_is_not_interpreted_as_after(self):
        result = self.parse('내일 오후 6시 전에 부산 서면에서 <폭설> 보고 싶어')
        self.assertEqual(result['conditions']['deadline'], '18:00')
        self.assertEqual(result['conditions']['region'], '부산 서면')
        self.assertNotIn('start_time', result['conditions'])

    def test_ambiguous_time_asks_instead_of_guessing(self):
        result = self.parse('내일 6시 이후에 부산 서면에서 <폭설> 보고 싶어')
        self.assertNotIn('start_time', result['conditions'])
        self.assertTrue(result['question'])

    def test_general_requests_still_use_existing_analyzer(self):
        self.assertIsNone(self.parse('내일 강남에서 액션 영화 추천해줘'))

    def test_explicit_request_does_not_require_llm_credentials(self):
        from app.llm import analyze_request
        with patch('app.llm.requests.post', side_effect=AssertionError('LLM must not be called')):
            result = analyze_request('나는 내일 오후 6시 이후에 부산 서면에서 <폭설>이라는 영화를 보고싶어', {})
        self.assertEqual(result['intent'], 'showtimes')


class ShowtimeAgentTests(unittest.TestCase):
    def test_direct_api_works_without_llm_and_validates_query(self):
        from test_requirements import APITests
        api = APITests()
        query = '/api/showtimes?region=%EB%B6%80%EC%82%B0%20%EC%84%9C%EB%A9%B4&movie_nm=%ED%8F%AD%EC%84%A4&watch_date=2026-11-21&start_time=18:00&brands=cgv'
        with patch('app.showtimes.requests.get', side_effect=[sites(), response([row()]), response([])]), patch.dict('os.environ', {'OPENAI_API_KEY': ''}):
            status, result = api.request('GET', query)
        self.assertEqual(status, 200)
        self.assertTrue(result['ok'])
        self.assertEqual(result['data']['items'][0]['remaining_seats'], 12)
        self.assertEqual(api.request('GET', query.replace('18:00', '25:00'))[0], 422)

    def test_graph_uses_showtime_tool_without_boxoffice_and_keeps_followup_memory(self):
        from app.agent import MovieAgent
        from app.events import EventBus
        from app import store
        from app.showtimes import get_showtimes
        analysis = {'intent': 'showtimes', 'conditions': {'watch_date': '2026-11-21', 'start_time': '18:00', 'region': '부산 서면', 'movie_nm': '폭설'}, 'tool_names': ['get_showtimes'], 'reason': 'explicit'}
        with patch('app.showtimes.requests.get', side_effect=[sites(), response([row()]), response([])]):
            data = get_showtimes(**analysis['conditions'])
        calls = []
        def runner(name, **args):
            calls.append(name)
            return data
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'PLANNER_DB_PATH': str(Path(folder) / 'test.db')}):
            agent = MovieAgent(analyzer=lambda *args: analysis, tool_runner=runner, event_bus=EventBus())
            result = agent.run('showtime-test', 'example')
            self.assertEqual(calls, ['get_showtimes'])
            self.assertEqual(result['showtimes'][0]['remaining_seats'], 12)
            self.assertEqual(result['answer'], '')
            self.assertEqual(store.get_memory('showtime-test')['intent'], 'showtimes')

    def test_missing_region_is_asked_before_external_calls(self):
        from app.agent import MovieAgent
        from app.events import EventBus
        runner = Mock(side_effect=AssertionError('must ask first'))
        agent = MovieAgent(analyzer=lambda *args: {'intent': 'showtimes', 'conditions': {'movie_nm': '폭설', 'watch_date': '2026-11-21', 'start_time': '18:00'}, 'tool_names': ['get_showtimes'], 'reason': 'missing'}, tool_runner=runner, event_bus=EventBus())
        state = agent.build_graph().invoke(agent.initial_state('missing', 'example', {}))
        self.assertIn('지역', state['answer'])
        self.assertEqual(runner.call_count, 0)
