"""사용자가 보고한 시간표 대화가 다른 작업으로 전환되지 않는지 검증한다."""
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from app.showtime_request import parse_showtime_request


CONDITIONS = {'watch_date': '2026-11-21', 'start_time': '14:00', 'region': '서면', 'movie_nm': '폭설', 'brands': ['cgv', 'lotte']}


class ConversationParsingTests(unittest.TestCase):
    def parse(self, message, **memory):
        return parse_showtime_request(message, {'intent': 'showtimes', 'conditions': CONDITIONS, **memory}, today=date(2026, 11, 20))

    def test_meal_time_is_not_start_time_and_explicit_finish_is_deadline(self):
        result = self.parse('아 근ㄷ데 나 6시에 밥 먹으러 가야해서 5시 30분 전에 끝나야해')
        self.assertIsNotNone(result)
        self.assertEqual(result['intent'], 'showtimes')
        self.assertEqual(result['conditions'], {'deadline': '17:30', 'deadline_inclusive': False})
        self.assertIsNone(result.get('question'))

    def test_correction_changes_only_deadline(self):
        result = self.parse('아니 그럼 6시 이전으로 할게')
        self.assertIsNotNone(result)
        self.assertEqual(result['conditions'], {'deadline': '18:00', 'deadline_inclusive': False})

    def test_until_and_before_have_distinct_boundaries(self):
        for message, inclusive in [('오후 6시까지 끝나야 해', True), ('오후 6시 전에 끝나야 해', False)]:
            with self.subTest(message=message):
                result = self.parse(message)
                self.assertEqual(result['conditions']['deadline'], '18:00')
                self.assertEqual(result['conditions']['deadline_inclusive'], inclusive)

    def test_ambiguous_finish_asks_only_for_period_and_keeps_pending_value(self):
        result = self.parse('6시 전에 끝나야 해', conditions={**CONDITIONS, 'start_time': '02:00'})
        self.assertTrue(result['question'])
        self.assertEqual(result['pending_field'], 'deadline')
        self.assertEqual(result['pending_time']['hour'], 6)

    def test_period_answer_resolves_pending_deadline(self):
        result = self.parse('오후야', pending_field='deadline', pending_time={'field':'deadline','hour':6,'minute':0,'inclusive':False})
        self.assertEqual(result['conditions'], {'deadline':'18:00', 'deadline_inclusive':False})

    def test_pending_movie_answer_is_not_a_new_unrelated_request(self):
        result = self.parse('폭설', conditions={key:value for key,value in CONDITIONS.items() if key!='movie_nm'}, pending_field='movie_nm')
        self.assertEqual(result['conditions'], {'movie_nm':'폭설'})

    def test_start_change_remains_a_start_change(self):
        result = self.parse('시작은 오후 3시 이후로 바꿔줘')
        self.assertEqual(result['conditions'], {'start_time':'15:00'})

    def test_two_time_sentence_keeps_start_and_finish_roles_separate(self):
        result=self.parse('오후 2시부터 시작하고 오후 6시 전에 끝나야 해')
        self.assertEqual(result['conditions'],{'start_time':'14:00','deadline':'18:00','deadline_inclusive':False})

    def test_deadline_can_be_removed_without_losing_other_conditions(self):
        result = self.parse('종료 제한은 없애줘')
        self.assertEqual(result['conditions'], {'deadline':None,'deadline_inclusive':None})

    def test_greeting_does_not_destroy_active_showtime_context(self):
        result = self.parse('그럼 오후 6시 이전에 끝나는 걸로', intent='help', active_intent='showtimes')
        self.assertEqual(result['intent'], 'showtimes')
        self.assertEqual(result['conditions']['deadline'], '18:00')

    def test_explicit_different_task_is_not_hijacked(self):
        self.assertIsNone(self.parse('다른 영화 추천해줘'))
        self.assertIsNone(self.parse('오늘 박스오피스 순위를 알려줘'))


class ConversationGraphTests(unittest.TestCase):
    def test_reported_followups_keep_movie_region_start_date_and_brands(self):
        from app.agent import MovieAgent
        from app.llm import analyze_request
        from app.events import EventBus
        from app import store
        from app.showtimes import KST, ShowtimesData
        calls = []
        def runner(name, **args):
            calls.append((name, args))
            return {'ok':True, 'data':ShowtimesData(items=[], checked_at=datetime.now(KST), checked_theaters=['CGV 서면', '롯데시네마 부산본점'], complete=True, warnings=[]).model_dump(mode='json')}
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'PLANNER_DB_PATH':str(Path(folder)/'test.db')}), patch('app.llm.requests.post', side_effect=AssertionError('condition edits must not depend on LLM')):
            store.save_memory('report', {'intent':'showtimes', 'conditions':CONDITIONS})
            agent = MovieAgent(analyzer=analyze_request, tool_runner=runner, event_bus=EventBus())
            first = agent.run('report', '아 근ㄷ데 나 6시에 밥 먹으러 가야해서 5시 30분 전에 끝나야해')
            second = agent.run('report', '아니 그럼 6시 이전으로 할게')
            for result, deadline in [(first,'17:30'),(second,'18:00')]:
                for key, value in CONDITIONS.items():
                    self.assertEqual(result['conditions'][key], value)
                self.assertEqual(result['conditions']['deadline'], deadline)
                self.assertFalse(result['conditions']['deadline_inclusive'])
                self.assertEqual(result['answer'], '')
                self.assertIsNone(result['question'])
                self.assertEqual(result['recommendations'], [])
            self.assertEqual([name for name,_ in calls], ['get_showtimes','get_showtimes'])

    def test_movie_clarification_survives_a_greeting(self):
        from app.agent import MovieAgent
        from app.llm import analyze_request
        from app.events import EventBus
        from app import store
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'PLANNER_DB_PATH':str(Path(folder)/'test.db')}):
            conditions = {key:value for key,value in CONDITIONS.items() if key!='movie_nm'}
            store.save_memory('pending', {'intent':'showtimes', 'conditions':conditions})
            agent = MovieAgent(analyzer=lambda *args:{'intent':'showtimes','conditions':{},'tool_names':['get_showtimes'],'reason':'pending movie'}, event_bus=EventBus())
            response = agent.run('pending','영화관 시간표')
            self.assertIn('영화', response['question'])
            self.assertEqual(store.get_memory('pending')['pending_field'],'movie_nm')
            agent = MovieAgent(analyzer=lambda *args:{'intent':'help','reason':'greeting'}, event_bus=EventBus())
            agent.run('pending','고마워')
            memory = store.get_memory('pending')
            self.assertEqual(memory['active_intent'],'showtimes')
            self.assertEqual(parse_showtime_request('폭설', memory)['conditions']['movie_nm'],'폭설')


class FinishBoundaryTests(unittest.TestCase):
    def test_exact_deadline_is_excluded_for_before_but_included_for_until(self):
        from app.showtimes import get_showtimes
        from test_showtimes import sites, response, row
        for inclusive, expected in [(False,1),(True,2)]:
            with self.subTest(inclusive=inclusive), patch('app.showtimes.requests.get', side_effect=[sites(),response([row('1400',scnendTm='1729'),row('1500',scnendTm='1730')]),response([])]):
                result = get_showtimes(region='부산 서면',movie_nm='폭설',watch_date='2026-11-21',start_time='14:00',deadline='17:30',deadline_inclusive=inclusive)
                self.assertEqual(len(result['data']['items']),expected)
