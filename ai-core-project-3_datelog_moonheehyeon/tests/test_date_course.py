import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, Mock


def place(name='양식 식당', category='음식점 > 양식 > 이탈리안', **changes):
    return {'id':'123', 'place_name':name, 'category_name':category, 'category_group_code':'FD6', 'address_name':'부산 부산진구 부전동',
            'road_address_name':'부산 부산진구 서면로 1', 'phone':'051-123-4567', 'place_url':'https://place.map.kakao.com/123',
            'x':'129.06', 'y':'35.15', 'distance':'150', **changes}


def http(documents):
    response=Mock(status_code=200)
    response.json.return_value={'documents':documents}
    return response


class SavedDateTests(unittest.TestCase):
    def test_date_places_survive_reload_and_movie_edit(self):
        from app import store
        from app.schemas import PlanIn, PlanOut
        restaurant = {'name':'파스타 식당','lat':35.15,'lng':129.06,'address':'부산 서면','url':'https://place.map.kakao.com/123'}
        cafe = {**restaurant,'name':'커피 카페'}
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'PLANNER_DB_PATH':str(Path(folder)/'date.db')}):
            saved = store.save_plan(PlanIn(movie_nm='폭설', watch_date='2026-11-21', restaurant=restaurant, cafe=cafe))
            loaded = PlanOut.model_validate(store.get_plan(saved['plan_id']))
            self.assertEqual(loaded.restaurant.name, restaurant['name'])
            self.assertEqual(loaded.cafe.name, cafe['name'])
            edited = PlanIn.model_validate({**loaded.model_dump(mode='json'),'start_time':'14:00'})
            store.save_plan(edited, saved['plan_id'])
            self.assertEqual(store.list_plans()[0]['cafe'], cafe)


class PlaceTests(unittest.TestCase):
    def test_selected_cinema_is_resolved_and_only_western_food_is_returned(self):
        from app.places import search_places
        cinema=place('CGV 서면','문화,예술 > 영화관', category_group_code='CT1')
        with patch.dict('os.environ',{'KAKAO_REST_API_KEY':'fixture'}), patch('tools_start.requests.get', side_effect=[http([cinema]),http([place(),place('한식 식당','음식점 > 한식')])]) as request:
            result=search_places(region='서면',kind='restaurant',cuisine='양식',anchor_name='CGV 서면')
        self.assertTrue(result['ok'],result)
        self.assertEqual(len(result['data']['items']),1)
        self.assertEqual(result['data']['anchor']['name'],'CGV 서면')
        self.assertEqual(request.call_args.kwargs['params']['radius'],1000)
        self.assertEqual(request.call_args.kwargs['params']['sort'],'distance')

    def test_cafe_does_not_reuse_western_cuisine_and_keeps_coordinates(self):
        from app.places import search_places
        cafe=place('근처 카페','음식점 > 카페', category_group_code='CE7')
        with patch.dict('os.environ',{'KAKAO_REST_API_KEY':'fixture'}), patch('tools_start.requests.get',return_value=http([cafe])) as request:
            result=search_places(region='서면',kind='cafe',cuisine='양식',anchor_name='선택한 식당',lat=35.15,lng=129.06)
        self.assertTrue(result['ok'],result)
        self.assertIsNone(result['data']['cuisine'])
        self.assertEqual(result['data']['items'][0]['lat'],35.15)
        self.assertEqual(request.call_args.kwargs['params']['category_group_code'],'CE7')

    def test_unknown_cinema_is_not_silently_replaced_by_another_branch(self):
        from app.places import search_places
        with patch.dict('os.environ',{'KAKAO_REST_API_KEY':'fixture'}), patch('tools_start.requests.get',side_effect=[http([place('CGV 다른지점')]),http([])]):
            result=search_places(region='서면',kind='restaurant',anchor_name='CGV 서면')
        self.assertTrue(result['ok'])
        self.assertIsNone(result['data']['anchor'])
        self.assertIn('지역',result['data']['notice'])


class DateCourseParsingTests(unittest.TestCase):
    def test_region_before_place_noun_does_not_need_a_particle(self):
        from app.place_request import parse_place_request
        for message, region in [('서면 카페 추천해줘','서면'),('홍대 양식 밥집 찾아줘','홍대'),('서울 강남 카페 찾아줘','서울 강남')]:
            self.assertEqual(parse_place_request(message,{})['conditions'].get('place_region'),region)

    def test_place_modifiers_do_not_replace_remembered_region(self):
        from app.place_request import parse_place_request
        for message in ['다른 카페 추천해줘','조용한 카페 추천해줘','근처 카페 추천해줘','그 근처 카페 찾아줘','예쁜 카페 추천해줘']:
            self.assertNotIn('place_region',parse_place_request(message,{'conditions':{'region':'서면'}})['conditions'],message)

    def test_food_and_cafe_followups_do_not_require_llm(self):
        from app.place_request import parse_place_request
        memory={'active_intent':'showtimes','conditions':{'region':'서면','movie_nm':'폭설','cuisine':'양식'}}
        meal=parse_place_request('그 근처에서 먹을 수 있는 밥집 추천해줘 나 양식으로 먹고 싶어',memory)
        self.assertEqual(meal['intent'],'places')
        self.assertEqual(meal['conditions']['cuisine'],'양식')
        cafe=parse_place_request('나 카페 가고 싶어',memory)
        self.assertEqual(cafe['conditions']['place_kind'],'cafe')
        self.assertNotIn('region',cafe['conditions'])

    def test_nearby_pronouns_do_not_replace_remembered_region(self):
        from app.place_request import parse_place_request
        for message in ['그 근처에서 먹을 수 있는 밥집 추천해줘 나 양식으로 먹고 싶어','나 그 근처 카페 가고 싶어']:
            result=parse_place_request(message,{'conditions':{'region':'서면'}})
            self.assertNotIn('place_region',result['conditions'])

    def test_missing_place_region_can_be_answered_without_repeating_food_request(self):
        from app.place_request import parse_place_request
        result=parse_place_request('서면',{'active_intent':'places','pending_field':'region','conditions':{'place_kind':'cafe'}})
        self.assertEqual(result['conditions']['place_region'],'서면')

    def test_meal_appointment_in_movie_deadline_is_not_a_restaurant_request(self):
        from app.place_request import parse_place_request
        self.assertIsNone(parse_place_request('나 6시에 밥 먹으러 가야해서 5시 30분 전에 끝나야해',{}))


class CourseGraphTests(unittest.TestCase):
    def test_explicit_movie_anchor_overrides_previously_selected_restaurant(self):
        from app.agent import MovieAgent
        from app.llm import analyze_request
        from app.events import EventBus
        agent=MovieAgent(analyzer=analyze_request,event_bus=EventBus())
        memory={'intent':'places','active_intent':'places','conditions':{'region':'서면','place_kind':'restaurant'},
                'course':{'movie':{'cinema':'CGV 서면','movie_nm':'폭설'},'restaurant':{'name':'다른 식당','lat':35.15,'lng':129.06}}}
        state=agent.initial_state('anchor','영화관 근처 카페 추천해줘',memory)
        state=agent.plan(agent.analyze(state))
        self.assertEqual(state['tasks'][0]['args']['anchor_name'],'CGV 서면')

    def test_movie_then_western_then_cafe_keeps_movie_and_uses_selected_anchor(self):
        from app.agent import MovieAgent
        from app.events import EventBus
        from app.llm import analyze_request
        from app import store
        from app.places import PlaceData
        from app.showtimes import KST
        calls=[]
        def runner(name,**args):
            calls.append((name,args))
            data=PlaceData(items=[],kind=args['kind'],region=args['region'],cuisine=args.get('cuisine'),checked_at=datetime.now(KST))
            return {'ok':True,'data':data.model_dump(mode='json')}
        conditions={'watch_date':'2026-11-21','start_time':'14:00','region':'서면','movie_nm':'폭설','brands':['cgv']}
        course={'movie':{'cinema':'CGV 서면','movie_nm':'폭설','watch_date':'2026-11-21','start_time':'14:40','end_time':'16:19'}}
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',{'PLANNER_DB_PATH':str(Path(folder)/'test.db')}),patch('app.llm.requests.post',side_effect=AssertionError('LLM must not be called')):
            store.save_memory('course',{'intent':'showtimes','active_intent':'showtimes','conditions':conditions})
            agent=MovieAgent(analyzer=analyze_request,tool_runner=runner,event_bus=EventBus())
            meal=agent.run('course','그 근처 양식 밥집 추천해줘',course=course)
            self.assertEqual(calls[-1][0],'search_places')
            self.assertEqual(calls[-1][1]['anchor_name'],'CGV 서면')
            self.assertEqual(meal['answer'],'')
            course['restaurant']={'name':'선택한 식당','lat':35.15,'lng':129.06,'url':'https://place.map.kakao.com/123'}
            cafe=agent.run('course','나 카페 가고 싶어',course=course)
            self.assertEqual(calls[-1][1]['kind'],'cafe')
            self.assertEqual(calls[-1][1]['anchor_name'],'선택한 식당')
            self.assertEqual(calls[-1][1]['lat'],35.15)
            self.assertEqual(cafe['conditions']['movie_nm'],'폭설')
            self.assertEqual(cafe['conditions']['brands'],['cgv'])
