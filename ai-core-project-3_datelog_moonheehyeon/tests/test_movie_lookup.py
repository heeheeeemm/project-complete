import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class MovieLookupTests(unittest.TestCase):
    def test_new_date_prompt_has_no_hidden_movie_date_or_time(self):
        from app.llm import analyze_request
        old={'active_intent':'showtimes','conditions':{'movie_nm':'폭설','watch_date':'2026-11-21','start_time':'14:00'}}
        result=analyze_request('서면에서 영화 데이트 하고 싶어',old)
        for key in ('movie_nm','watch_date','start_time'):
            self.assertIsNone(result['conditions'][key])

    def test_actor_description_extracts_person_name(self):
        from app.movie_request import parse_movie_request
        for text in ('임영웅이 나온다는 영화 보고 싶어','임영웅 출연한 영화 보고 싶어'):
            self.assertEqual(parse_movie_request(text,{})['conditions']['movie_query'],'임영웅')

    def test_description_is_not_used_as_a_title_or_given_invented_times(self):
        from app.llm import analyze_request
        with patch('app.llm.requests.post', side_effect=AssertionError('no LLM needed')):
            result = analyze_request('서면에서 영화 데이트 나는 임영웅 영화 보고 싶음', {'conditions':{'watch_date':'2026-11-21','start_time':'14:00','movie_nm':'폭설'}})
        self.assertEqual(result['conditions']['movie_query'], '임영웅')
        self.assertNotEqual(result['conditions'].get('movie_nm'), '임영웅')
        self.assertIsNone(result['conditions']['watch_date'])
        self.assertIsNone(result['conditions']['start_time'])

    def test_lookup_confirmation_then_date_and_time_are_required(self):
        from app.agent import MovieAgent
        from app.events import EventBus
        calls=[]
        matches=[{'movie_cd':'20240001','movie_nm':'임영웅 콘서트 영화','year':'2024'}]
        def runner(name, **args):
            calls.append(name)
            self.assertEqual(name,'search_movies')
            return {'ok':True,'data':{'items':matches,'source':'KOBIS','warnings':[]}}
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ',{'PLANNER_DB_PATH':str(Path(folder)/'db.sqlite')}):
            agent=MovieAgent(tool_runner=runner,event_bus=EventBus())
            first=agent.run('lookup','서면에서 영화 데이트 나는 임영웅 영화 보고 싶음')
            self.assertIn('맞',first['question'])
            self.assertIsNone(first['showtime_search'])
            second=agent.run('lookup','응 맞아')
            self.assertEqual(second['conditions']['movie_nm'],matches[0]['movie_nm'])
            self.assertIn('날짜',second['question'])
            third=agent.run('lookup','내일')
            self.assertIn('몇 시',third['question'])
            self.assertEqual(calls,['search_movies'])

    def test_person_filmography_uses_real_movie_ids(self):
        from app.movie_lookup import search_movies
        responses=[{'movieListResult':{'movieList':[]}},
                   {'peopleListResult':{'peopleList':[{'peopleNm':'배우이름','peopleCd':'100'}]}},
                   {'peopleInfoResult':{'peopleInfo':{'filmos':[{'movieCd':'20240001','movieNm':'실제 작품','moviePartNm':'배우'}]}}}]
        with patch.dict('os.environ',{'KOBIS_API_KEY':'test'}), patch('tools_start._get',side_effect=[{'ok':True,'data':r} for r in responses]):
            result=search_movies('배우이름')
        self.assertEqual(result['data']['items'][0]['movie_nm'],'실제 작품')

    def test_ambiguous_yes_does_not_choose_first_movie(self):
        from app.movie_request import parse_movie_request
        result=parse_movie_request('응',{'pending_movies':[{'movie_nm':'A','movie_cd':'20240001'},{'movie_nm':'B','movie_cd':'20240002'}]})
        self.assertTrue(result['question'])
        self.assertNotIn('movie_nm',result.get('conditions',{}))
