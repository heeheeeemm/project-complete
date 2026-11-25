import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class SubmissionPlanTests(unittest.TestCase):
    def test_final_itinerary_requires_a_date(self):
        from app.itineraries import ItineraryIn
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ItineraryIn(title='날짜 없는 초안',stops=[{'kind':'cafe','name':'카페'}])

    def test_overlaps_are_reported_without_blocking_save_and_update_clears_them(self):
        from app.itineraries import ItineraryIn, save_itinerary, get_itinerary
        from app import store
        from app.schemas import PlanIn
        def plan(name,start,end):
            return ItineraryIn(title=name,watch_date='2026-11-21',stops=[{'kind':'cafe','name':name,'start_time':start,'end_time':end}])
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',{'PLANNER_DB_PATH':str(Path(folder)/'check.db')}):
            first=save_itinerary(plan('첫 약속','13:00','14:00'))
            second=save_itinerary(plan('다른 약속','13:30','14:30'))
            self.assertEqual(second['overlap_itinerary_ids'],[first['itinerary_id']])
            self.assertTrue(second['warnings'])
            self.assertIsNotNone(get_itinerary(second['itinerary_id']))
            adjacent=save_itinerary(plan('다른 약속','14:00','15:00'),second['itinerary_id'])
            self.assertEqual(adjacent['overlap_itinerary_ids'],[])
            legacy=store.save_plan(PlanIn(movie_nm='이전 영화 약속',watch_date='2026-11-21',start_time='14:20',end_time='16:00'))
            self.assertEqual(get_itinerary(second['itinerary_id'])['overlap_plan_ids'],[legacy['plan_id']])

    def test_internal_overlaps_and_unknown_times_are_visible(self):
        from app.itineraries import ItineraryIn, save_itinerary
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',{'PLANNER_DB_PATH':str(Path(folder)/'check.db')}):
            result=save_itinerary(ItineraryIn(title='중복',watch_date='2026-11-21',stops=[
                {'kind':'cafe','name':'A','start_time':'13:00','end_time':'14:00'},
                {'kind':'restaurant','name':'B','start_time':'13:30','end_time':'15:00'},
                {'kind':'place','name':'산책'}]))
            self.assertTrue(result['overlapping_stop_ids'])
            self.assertTrue(any('판단' in warning for warning in result['warnings']))

    def test_legacy_plan_warns_about_saved_itinerary_too(self):
        from app.itineraries import ItineraryIn, save_itinerary
        from app import store
        from app.schemas import PlanIn
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',{'PLANNER_DB_PATH':str(Path(folder)/'check.db')}):
            other=save_itinerary(ItineraryIn(watch_date='2026-11-21',stops=[{'kind':'cafe','name':'카페','start_time':'14:00','end_time':'16:00'}]))
            result=store.save_plan(PlanIn(movie_nm='영화',watch_date='2026-11-21',start_time='14:30',end_time='15:30'))
            self.assertEqual(result['overlap_itinerary_ids'],[other['itinerary_id']])
            self.assertTrue(result['warnings'])


class SubmissionResponseTests(unittest.TestCase):
    def test_simple_boxoffice_facts_do_not_require_a_watch_date(self):
        from app.llm import analyze_request
        with patch('app.llm.requests.post',side_effect=AssertionError('simple facts need no LLM')):
            result=analyze_request('박스오피스 순위 알려줘',{})
        self.assertEqual(result['intent'],'facts')
        self.assertEqual(result['tool_names'],['get_boxoffice'])

    def test_replan_limit_notice_is_available_to_the_ui(self):
        from app.agent import MovieAgent
        from app.events import EventBus
        agent=MovieAgent(event_bus=EventBus())
        state=agent.initial_state('notice','추천',{})
        state.update(intent='plan',conditions={},stop_reason='재계획 상한에 도달했습니다.')
        result=agent.respond(state)
        self.assertEqual(result['notice'],'재계획 상한에 도달했습니다.')
