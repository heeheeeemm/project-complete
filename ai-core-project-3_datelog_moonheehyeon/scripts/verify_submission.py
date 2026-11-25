"""로깅 분리·Tool 계약 재생·기본값 검증. 외부 네트워크 호출 없음."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timedelta

from app import store
from app.agent import MovieAgent
from app.events import EventBus, LoggingAgent
from tools_start import TOOLS, ok

ROOT=Path(__file__).resolve().parent.parent


def verify():
    records=[]
    analyze=lambda message,memory:{'intent':'help','conditions':{},'reason':'고정 분석, 로깅 분리 확인','tool_names':[]}
    with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'PLANNER_DB_PATH':str(Path(folder)/'isolated.db')}):
        for mode in ['unplugged','logger','storage_failure']:
            bus=EventBus()
            if mode!='unplugged':bus.subscribe(LoggingAgent())
            def broken(event):raise RuntimeError('고정 구독자 장애')
            if mode=='storage_failure':bus.subscribe(broken)
            with patch('app.llm.requests.post',side_effect=AssertionError('로깅에서 LLM 호출 금지')):
                if mode=='storage_failure':
                    with patch('app.store.append_event',side_effect=OSError('고정 저장 장애')):
                        result=MovieAgent(analyzer=analyze,event_bus=bus).run(mode,'안녕 사용법 알려줘')
                else:result=MovieAgent(analyzer=analyze,event_bus=bus).run(mode,'안녕 사용법 알려줘')
            saved=store.get_logs(mode)
            assert result['events'] and not result['errors']
            assert (saved==result['events']) if mode=='logger' else not saved
            records.append({'mode':mode,'main_succeeded':True,'llm_calls':0,'returned_events':len(result['events']),'stored_events':len(saved),'events_equal':saved==result['events'] if mode=='logger' else None})
    (ROOT/'docs/logger-isolation.json').write_text(json.dumps({'mode':'fixed_analysis_real_graph_sqlite','records':records},ensure_ascii=False,indent=2),encoding='utf8')
    successes={}
    for name in ['live-integration.json','live-ui.json','live-kobis.json','sample-execution.json']:
        for rec in json.loads((ROOT/'docs'/name).read_text(encoding='utf8'))['records']:
            for event in rec.get('response',rec).get('events',[]):
                if event['type']=='tool_response' and event['data'].get('result',{}).get('ok'):
                    successes.setdefault(event['data']['tool'],event['data']['result'])
    successes['search_cinemas']=ok({'items':[{'name':'고정 영화관','address':'고정 주소','url':'https://place.map.kakao.com/1','lat':37.5,'lng':127.0}],'source':'고정 카카오 응답','notice':'실제 조회 아님'})
    bad_args={'get_boxoffice':{'target_date':'bad'},'get_movie_detail':{'movie_cd':'bad'},'search_cinemas':{'region':''},'search_movies':{'query':''},'search_places':{'region':'서면','kind':'bad'},'get_showtimes':{'region':'','movie_nm':'폭설','watch_date':'bad'}}
    valid_args={'get_boxoffice':{},'get_movie_detail':{'movie_cd':'20124079'},'search_cinemas':{'region':'강남'},'search_movies':{'query':'폭설'},'search_places':{'region':'서면','kind':'cafe'}}
    contracts=[]
    for name,tool in TOOLS.items():
        with patch.object(tool,'func',return_value=successes[name]):normal=tool.run()
        assert normal['ok']
        invalid=tool.run(**bad_args[name])
        assert not invalid['ok']
        missing=None
        if name in valid_args:
            with patch.dict(os.environ,{'KOBIS_API_KEY':'','KAKAO_REST_API_KEY':''}):missing=tool.run(**valid_args[name])
            assert missing['error']['code']=='INVALID_KEY'
        contracts.append({'tool':name,'normal_contract_replay':normal,'invalid_arguments':invalid,'missing_key':missing,'note':'정상 응답을 Tool 출력 계약에 재생했다. search_cinemas는 고정 응답. 시간표는 API 키를 요구하지 않아 키 누락은 해당없음.'})
    yesterday=(datetime.now().astimezone().date()-timedelta(days=1)).isoformat()
    fixture=ok({'boxOfficeResult':{'dailyBoxOfficeList':[{'movieCd':'00000001','movieNm':'기본값 고정 영화','rank':'1'}]}})
    with patch.dict(os.environ,{'KOBIS_API_KEY':'fixture'}),patch('tools_start._get',return_value=fixture):
        default=TOOLS['get_boxoffice'].run()
        assert default['data']['query_date']==yesterday
    (ROOT/'docs/tool-verification.json').write_text(json.dumps({'mode':'contract_replay_and_fixed_http','records':contracts,'boxoffice_default':default},ensure_ascii=False,indent=2),encoding='utf8')
    (ROOT/'docs/agent-graph.mmd').write_text(MovieAgent().build_graph().get_graph().draw_mermaid(),encoding='utf8')
    print('Logging isolation (3 modes) and Tool contracts (6 tools) passed.')


if __name__=='__main__':verify()
