import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


MESSAGE='서울 강남에서 영화볼거얌 오늘 오후 2-6시 사이에 있는 폭설 영화 볼거얌'


class MovieDialogueTests(unittest.TestCase):
    def test_exact_title_candidates_exclude_unrelated_festival_programs(self):
        from app.movie_lookup import search_movies
        movies=[{'movieCd':'20240001','movieNm':'폭설','openDt':'20241023','prdtYear':'2023'},
                {'movieCd':'20260001','movieNm':'폭설','openDt':'20261118','prdtYear':'2025'},
                {'movieCd':'20260002','movieNm':'영화제 프로그램','prdtYear':'2026'}]
        with patch.dict('os.environ',{'KOBIS_API_KEY':'test'}),patch('tools_start._get',side_effect=[{'ok':True,'data':{'movieListResult':{'movieList':movies}}},{'ok':True,'data':{'peopleListResult':{'peopleList':[]}}}]):
            result=search_movies('폭설')
        self.assertEqual([m['movie_nm'] for m in result['data']['items']],['폭설','폭설'])
        self.assertEqual(result['data']['items'][0]['open_date'],'2026-11-18')

    def test_compact_range_keeps_both_hours_and_period(self):
        from app.time_conditions import parse_time_updates
        for text in ('오늘 오후 2-6시 사이','오후 2시~6시 사이','오후 2:30~6:30 사이'):
            updates,question,_,_=parse_time_updates(text,{}, {})
            self.assertIsNone(question)
            self.assertEqual(updates['start_time'],'14:30' if '2:30' in text else '14:00')
            self.assertEqual(updates['deadline'],'18:30' if '6:30' in text else '18:00')

    def test_range_preserves_exclusive_finish_and_zero_padded_24h_time(self):
        from app.time_conditions import parse_time_updates
        updates,question,_,_=parse_time_updates('오후 2시부터 6시 전에 끝나야 해',{}, {})
        self.assertIsNone(question)
        self.assertFalse(updates['deadline_inclusive'])
        updates,question,_,_=parse_time_updates('02:00~06:00',{}, {})
        self.assertIsNone(question)
        self.assertEqual(updates['start_time'],'02:00')
        self.assertEqual(updates['deadline'],'06:00')

    def test_ambiguous_range_is_preserved_until_period_reply(self):
        from app.time_conditions import parse_time_updates
        _,question,field,pending=parse_time_updates('2시부터 6시 전에 끝나야 해',{}, {})
        self.assertTrue(question)
        updates,question,_,_=parse_time_updates('오후라고 했잖아',{'pending_time':pending,'pending_field':field},{})
        self.assertIsNone(question)
        self.assertEqual(updates['start_time'],'14:00')
        self.assertEqual(updates['deadline'],'18:00')
        self.assertFalse(updates['deadline_inclusive'])

    def test_recent_release_followup_does_not_become_a_title_or_forget_time(self):
        from app.agent import MovieAgent
        from app.events import EventBus
        from app.showtimes import KST
        calls=[]
        candidates=[{'movie_cd':'20240001','movie_nm':'폭설','year':'2023','open_date':'2024-10-23'},
                    {'movie_cd':'20260001','movie_nm':'폭설 새 작품','year':'2025','open_date':'2026-11-01'}]
        def runner(name,**args):
            calls.append((name,args))
            if name=='search_movies':
                return {'ok':True,'data':{'items':candidates,'source':'KOBIS','warnings':[]}}
            self.assertEqual(name,'get_showtimes')
            return {'ok':True,'data':{'items':[],'complete':True,'checked_theaters':[],'warnings':[],'checked_at':datetime.now(KST).isoformat()}}
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',{'PLANNER_DB_PATH':str(Path(folder)/'db.sqlite')}),patch('app.llm.requests.post',side_effect=AssertionError('do not infer stated hours with LLM')):
            agent=MovieAgent(tool_runner=runner,event_bus=EventBus())
            first=agent.run('range',MESSAGE)
            self.assertEqual(first['conditions']['start_time'],'14:00')
            self.assertEqual(first['conditions']['deadline'],'18:00')
            second=agent.run('range','최근에 개봉한건데?')
            self.assertEqual(second['conditions']['start_time'],'14:00')
            self.assertNotEqual(second['conditions'].get('movie_nm'),'최근에 개봉한건데?')
            self.assertIn('폭설 새 작품',second['question'])
            self.assertEqual(len(second['movie_matches']),1)
            third=agent.run('range','오후라고 했잖아')
            self.assertEqual(third['conditions']['start_time'],'14:00')
            self.assertNotIn('몇 시',third['question'])
            fourth=agent.run('range','응 맞아')
            self.assertIsNone(fourth['question'])
            self.assertEqual(calls[-1][0],'get_showtimes')
            self.assertEqual(calls[-1][1]['start_time'],'14:00')
            self.assertEqual(calls[-1][1]['deadline'],'18:00')

    def test_recent_release_unknown_dates_are_not_guessed_from_code(self):
        from app.movie_request import parse_movie_request
        result=parse_movie_request('최근에 개봉한건데?',{'pending_movies':[{'movie_cd':'20269999','movie_nm':'옛날 제목','year':'2026'},{'movie_cd':'20240001','movie_nm':'다른 제목','year':'2024'}]})
        self.assertEqual(result['pending_field'],'movie_confirmation')
        self.assertNotIn('movie_nm',result.get('conditions',{}))
