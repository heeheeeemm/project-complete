import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class ItineraryTests(unittest.TestCase):
    def test_empty_draft_snapshot_removes_old_search_anchor(self):
        from app import store
        from app.agent import MovieAgent
        from app.events import EventBus
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ',{'PLANNER_DB_PATH':str(Path(folder)/'snapshot.db')}):
            store.save_memory('reset',{'course':{'anchor':{'name':'지운 카페','lat':35.15,'lng':129.06}}})
            agent=MovieAgent(analyzer=lambda *args:{'intent':'help','reason':'상태 확인'},event_bus=EventBus())
            result=agent.run('reset','안녕',course={})
            self.assertEqual(result['course'],{})

    def test_api_can_save_cafe_without_movie_and_edit_order(self):
        from test_requirements import APITests
        api=APITests()
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ',{'PLANNER_DB_PATH':str(Path(folder)/'api.db')}):
            payload={'title':'카페부터','watch_date':'2026-11-21','stops':[{'kind':'cafe','name':'카페 A'},{'kind':'cafe','name':'카페 B'}]}
            status,saved=api.request('POST','/api/itineraries',payload)
            self.assertEqual(status,201)
            path='/api/itineraries/'+str(saved['itinerary_id'])
            self.assertEqual(api.request('GET',path)[1]['watch_date'],'2026-11-21')
            payload['stops'].reverse()
            self.assertEqual(api.request('PUT',path,payload)[0],200)
            self.assertEqual(api.request('GET','/api/itineraries')[1][0]['stops'][0]['name'],'카페 B')
            self.assertEqual(api.request('DELETE',path)[0],204)
            self.assertEqual(api.request('GET',path)[0],404)

    def test_cafe_only_and_repeated_categories_preserve_user_order(self):
        from app.itineraries import ItineraryIn, save_itinerary, list_itineraries, delete_itinerary
        stops=[{'kind':'cafe','name':'첫 카페','start_time':'13:00'},
               {'kind':'restaurant','name':'식당','start_time':'18:00'},
               {'kind':'cafe','name':'다른 카페'}]
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ',{'PLANNER_DB_PATH':str(Path(folder)/'test.db')}):
            saved=save_itinerary(ItineraryIn(title='우리 약속',watch_date='2026-11-21',stops=stops))
            self.assertEqual(saved['watch_date'],'2026-11-21')
            self.assertEqual([x['name'] for x in saved['stops']],['첫 카페','식당','다른 카페'])
            revised=ItineraryIn(title='수정한 약속',watch_date='2026-11-21',stops=[stops[2],stops[0]])
            save_itinerary(revised,saved['itinerary_id'])
            loaded=list_itineraries()[0]
            self.assertEqual([x['name'] for x in loaded['stops']],['다른 카페','첫 카페'])
            self.assertEqual(loaded['stops'][1]['start_time'],'13:00')
            self.assertTrue(delete_itinerary(saved['itinerary_id']))
            self.assertEqual(list_itineraries(),[])

    def test_empty_stop_and_invalid_time_are_rejected(self):
        from app.itineraries import ItineraryIn
        from pydantic import ValidationError
        for stops in ([],[{'kind':'cafe','name':' '}],[{'kind':'cafe','name':'카페','start_time':'25:00'}]):
            with self.assertRaises(ValidationError):
                ItineraryIn(title='약속',stops=stops)

    def test_nearby_cafe_can_start_from_selected_cafe_without_movie(self):
        from app.agent import MovieAgent
        from app.events import EventBus
        memory={'conditions':{},'course':{'cafe':{'name':'첫 카페','lat':35.15,'lng':129.06},'anchor':{'name':'첫 카페','lat':35.15,'lng':129.06}}}
        agent=MovieAgent(analyzer=lambda *args:{'intent':'places','conditions':{'place_kind':'restaurant'},'reason':'식당 탐색','tool_names':['search_places']},event_bus=EventBus())
        state=agent.plan(agent.analyze(agent.initial_state('free','그 근처 밥집 추천해줘',memory)))
        self.assertFalse(state['question'])
        self.assertEqual(state['tasks'][0]['args']['anchor_name'],'첫 카페')
