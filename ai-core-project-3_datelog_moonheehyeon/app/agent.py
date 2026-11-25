"""분석→계획→실행→판단→응답. 시간 계산과 재계획 제한은 코드가 책임진다."""
import json
import os
import re
from datetime import datetime
from functools import wraps
from time import perf_counter
from typing import TypedDict
from uuid import uuid4

from tools_start import TOOLS, fail, normalize_result
from . import store
from .events import bus
from .llm import AgentConfigurationError, analyze_request
from .schemas import Analysis, Conditions, CourseContext
from .showtimes import KST


class AgentState(TypedDict, total=False):
    session_id: str
    run_id: str
    message: str
    memory: dict
    conditions: dict
    intent: str
    question: str | None
    selected_tools: list[str]
    tasks: list[dict]
    cache: dict
    candidates: list[dict]
    details: dict
    recommendations: list[dict]
    excluded: list[dict]
    cinemas: list[dict]
    showtimes: list[dict]
    showtime_search: dict | None
    errors: list[dict]
    events: list[dict]
    replans: int
    retry: bool
    answer: str
    fatal: bool
    different_movie: bool
    stop_reason: str
    pending_field: str | None
    pending_time: dict | None
    updated_fields: list[str]
    places: list[dict]
    place_search: dict | None
    course: dict
    movie_matches: list[dict]
    movie_preference: str | None
    notice: str | None


def stage(func):
    @wraps(func)
    def wrapped(self, state):
        self.emit(state, 'stage_start', {'stage': func.__name__})
        started = perf_counter()
        try:
            result = func(self, state)
        except Exception:
            self.emit(state, 'stage_end', {'stage': func.__name__, 'status': 'failed',
                                         'elapsed_ms': round((perf_counter() - started) * 1000, 2)})
            raise
        self.emit(result, 'stage_end', {'stage': func.__name__, 'status': 'completed',
                                      'elapsed_ms': round((perf_counter() - started) * 1000, 2)})
        return result
    return wrapped


def minutes(value):
    hours, mins = map(int, value.split(':'))
    return hours * 60 + mins


def clock(value):
    return f'{value // 60:02}:{value % 60:02}'


class MovieAgent:
    def __init__(self, analyzer=analyze_request, tool_runner=None, event_bus=bus):
        self.analyzer = analyzer
        self.tool_runner = tool_runner or (lambda name, **args: TOOLS[name].run(**args))
        self.event_bus = event_bus
        try:
            self.max_replans = min(3, max(0, int(os.getenv('MAX_REPLANS', '3'))))
        except ValueError:
            self.max_replans = 3

    def initial_state(self, session_id, message, memory):
        return AgentState(session_id=session_id, run_id=uuid4().hex, message=message, memory=memory,
                          conditions={}, tasks=[], cache={}, candidates=[], details={}, recommendations=[],
                          excluded=[], cinemas=[], showtimes=[], showtime_search=None, errors=[], events=[], replans=0, retry=False, fatal=False,
                          question=None, different_movie=False, stop_reason='', pending_field=None, pending_time=None, updated_fields=[],
                          places=[],place_search=None,course=dict(memory.get('course',{})),movie_matches=[],movie_preference=None,notice=None)

    def emit(self, state, kind, data):
        state['events'].append(self.event_bus.emit(state['session_id'], state['run_id'], kind, data))

    def ask_movie(self,state):
        matches=state['movie_matches']
        if state.get('movie_preference')=='recent':
            released=[m for m in matches if m.get('open_date') and m['open_date']<=datetime.now(KST).date().isoformat()]
            if released:
                latest=max(m['open_date'] for m in released)
                matches=[m for m in released if m['open_date']==latest]
                state['movie_matches']=matches
                if len(matches)==1:
                    state['question']=f"{latest} 개봉한 <{matches[0]['movie_nm']}> 맞으신가요?"
                else:
                    state['question']=f'{latest} 개봉한 후보들 중 어떤 영화가 맞으신가요?'
            else:
                state['question']='후보의 개봉일을 확인하지 못해 최근 작품을 단정할 수 없어요. 아래에서 제목을 확인해 주실래요?'
        elif len(matches)==1:
            state['question']=f"<{matches[0]['movie_nm']}> 이 영화가 맞으신가요?"
        elif matches:
            state['question']='관련 영화를 찾았어요. 아래 작품 중 어떤 영화가 맞으신가요?'
        else:
            state['question']='관련 영화를 찾지 못했어요. 제목 일부나 다른 출연자를 알려 주실래요?'
        state['pending_field']='movie_confirmation' if matches else 'movie_nm'

    @stage
    def analyze(self, state):
        analysis = Analysis.model_validate(self.analyzer(state['message'], state['memory']))
        previous = dict(state['memory'].get('conditions', {}))
        updates = analysis.conditions.model_dump(mode='json', exclude_unset=True)
        state['updated_fields'] = list(updates)
        state['pending_field'] = analysis.pending_field
        state['pending_time'] = analysis.pending_time.model_dump() if analysis.pending_time else None
        if analysis.different_movie:
            previous.pop('movie_cd', None)
            previous.pop('movie_nm', None)
        if 'movie_nm' in updates and 'movie_cd' not in updates:
            previous.pop('movie_cd', None)
        if 'movie_cd' in updates and 'movie_nm' not in updates:
            previous.pop('movie_nm', None)
        state['conditions'] = Conditions.model_validate({**previous, **updates}).model_dump(mode='json', exclude_none=True)
        state['intent'] = analysis.intent
        state['selected_tools'] = list(dict.fromkeys(analysis.tool_names))
        state['question'] = analysis.question
        state['different_movie'] = analysis.different_movie
        state['movie_preference']=analysis.movie_preference
        searching_movie=bool(updates.get('movie_query'))
        waiting_movie=bool(state['memory'].get('pending_movies')) and not searching_movie and 'movie_nm' not in updates
        if searching_movie:
            state['selected_tools']=['search_movies']
            state['question']=None
            state['course']={}
        elif waiting_movie:
            state['movie_matches']=state['memory']['pending_movies']
            self.ask_movie(state)
            if analysis.question:
                state['question']=analysis.question
        movie=state['course'].get('movie')
        if movie and analysis.intent in {'showtimes','plan'}:
            c=state['conditions']
            invalid=(('movie_nm' in updates and c.get('movie_nm')!=movie.get('movie_nm')) or
                     ('watch_date' in updates and c.get('watch_date')!=movie.get('watch_date')) or
                     ('region' in updates and updates['region']!=previous.get('region')) or
                     ('start_time' in updates and movie.get('start_time') and c.get('start_time','00:00')>movie['start_time']) or
                     ('deadline' in updates and c.get('deadline') and movie.get('end_time') and (movie['end_time']>c['deadline'] or (movie['end_time']==c['deadline'] and c.get('deadline_inclusive') is False))) or
                     ('brands' in updates and c.get('brands') and movie.get('brand') and movie['brand'] not in c['brands']))
            if invalid:
                state['course']={}
        if state['intent']=='places':
            state['selected_tools']=['search_places']
            if 'place_region' in updates and updates['place_region']!=previous.get('place_region'):
                state['course'].pop('restaurant',None)
                state['course'].pop('cafe',None)
            if not state['conditions'].get('place_kind'):
                state['question']='식당과 카페 중 어떤 곳을 찾으시나요?'
            elif not (state['conditions'].get('place_region') or state['conditions'].get('region') or any(state['course'].get(key) for key in ('anchor','movie','restaurant','cafe'))):
                state['question']='어느 지역에서 찾으시나요?'
                state['pending_field']='region'
        if not searching_movie and (state['intent'] == 'showtimes' or 'get_showtimes' in state['selected_tools']):
            state['intent'] = 'showtimes'
            state['selected_tools'] = ['get_showtimes']
            if not state['question']:
                for field, prompt in [('movie_nm', '어떤 영화의 상영시간표를 찾으시나요?'),
                                      ('region', '어느 지역이나 영화관 지점에서 관람하시나요? 예: 부산 서면.'),
                                      ('watch_date', '어느 날짜의 상영시간표를 찾으시나요?'),
                                      ('start_time', '몇 시 이후에 관람할 수 있나요? 오전·오후도 알려 주세요.')]:
                    if not state['conditions'].get(field):
                        state['question'] = prompt
                        state['pending_field'] = field
                        break
            if not state['question'] and state['conditions'].get('deadline') and state['conditions']['deadline'] <= state['conditions']['start_time']:
                state['question'] = '종료 제한이 시작 가능한 시각보다 늦어야 합니다. 종료 시각을 다시 알려 주세요.'
                state['pending_field'] = 'deadline'
        if state['intent'] == 'plan' and not state['question']:
            if not state['conditions'].get('watch_date'):
                state['question'] = '어느 날짜에 관람하실 예정인가요?'
            elif not state['conditions'].get('start_time'):
                state['question'] = '몇 시 이후에 관람할 수 있나요? 오전·오후도 알려 주세요.'
            elif state['conditions'].get('deadline') and state['conditions']['deadline'] <= state['conditions']['start_time']:
                state['question'] = '종료 제한 시각은 같은 날짜의 시작 시각보다 늦어야 합니다. 시각을 다시 알려 주세요.'
        self.emit(state, 'llm_decision', {'intent': analysis.intent, 'reason': analysis.reason, 'updates': updates, 'selected_tools': state['selected_tools']})
        return state

    @stage
    def plan(self, state):
        state['tasks'] = []
        if state['question'] or state['intent'] in {'help', 'save'}:
            return state
        c = state['conditions']
        selected = state['selected_tools']
        if 'search_movies' in selected:
            state['tasks']=[{'tool':'search_movies','args':{'query':c['movie_query']}}]
            self.emit(state,'work_plan',{'tasks':state['tasks'],'attempt':0})
            return state
        if state['intent']=='places':
            course=state['course']
            kind=c['place_kind']
            anchor=None
            if 'place_region' not in state['updated_fields'] or c.get('place_region') is None:
                if c.get('place_anchor')=='cinema' and course.get('movie'):
                    anchor={'name':course['movie']['cinema']}
                elif c.get('place_anchor')=='restaurant' and course.get('restaurant'):
                    anchor=course['restaurant']
                elif c.get('place_anchor')=='cafe' and course.get('cafe'):
                    anchor=course['cafe']
                elif course.get('anchor'):
                    anchor=course['anchor']
                elif kind=='cafe' and course.get('restaurant'):
                    anchor=course['restaurant']
                elif not c.get('place_region') and course.get('movie'):
                    anchor={'name':course['movie']['cinema']}
                elif not c.get('place_region') and course.get('cafe'):
                    anchor=course['cafe']
            region=c.get('place_region') or c.get('region') or (anchor or {}).get('name')
            args={'region':region,'kind':kind,'cuisine':c.get('cuisine') if kind=='restaurant' else None}
            if anchor:
                args['anchor_name']=anchor['name']
                for key in ('lat','lng'):
                    if anchor.get(key) is not None:
                        args[key]=anchor[key]
            state['tasks']=[{'tool':'search_places','args':args}]
            self.emit(state,'work_plan',{'tasks':state['tasks'],'attempt':0})
            return state
        if state['intent'] == 'showtimes':
            state['tasks'] = [{'tool': 'get_showtimes', 'args': {key: c[key] for key in
                ('region', 'movie_nm', 'watch_date', 'start_time', 'deadline', 'deadline_inclusive', 'buffer_minutes', 'brands') if key in c}}]
            self.emit(state, 'work_plan', {'tasks': state['tasks'], 'attempt': 0})
            return state
        if 'search_cinemas' in selected and not c.get('region'):
            state['question'] = '어느 지역의 영화관을 찾으시나요?'
            return state
        if state['replans']:
            self.emit(state, 'replan', {'attempt': state['replans'], 'reason': '조회한 후보가 제약을 충족하지 않아 다음 후보를 평가합니다.'})
        tasks = []
        if c.get('movie_cd') and 'get_movie_detail' in selected:
            tasks = [{'tool': 'get_movie_detail', 'args': {'movie_cd': c['movie_cd']}}]
        elif 'get_boxoffice' in selected or 'get_movie_detail' in selected:
            tasks = [{'tool': 'get_boxoffice', 'args': {'target_date': c.get('watch_date')}}]
            # 상세 인자는 앞선 Tool의 식별자에서 채운다.
            if 'get_movie_detail' in selected or state['intent'] == 'plan':
                tasks.append({'tool': 'get_movie_detail', 'args_from': 'get_boxoffice.items.movie_cd'})
        if c.get('region') and 'search_cinemas' in state['selected_tools']:
            tasks.append({'tool': 'search_cinemas', 'args': {'region': c['region']}})
        # 모델이 아무 Tool도 선택하지 않으면 외부 조회를 임의로 실행하지 않는다.
        if not state['selected_tools']:
            state['question'] = '영화 추천, 영화코드 상세 조회, 지역 영화관 검색 중 필요한 작업을 알려 주세요.'
        else:
            state['tasks'] = tasks
        self.emit(state, 'work_plan', {'tasks': state['tasks'], 'attempt': state['replans']})
        return state

    def call(self, state, name, args):
        key = json.dumps([name, args], sort_keys=True, ensure_ascii=False)
        if key in state['cache']:
            self.emit(state, 'tool_cache', {'tool': name, 'arguments': args})
            return state['cache'][key]
        self.emit(state, 'tool_request', {'tool': name, 'arguments': args})
        start = perf_counter()
        try:
            result = normalize_result(self.tool_runner(name, **args))
        except Exception:
            result = fail('UPSTREAM_ERROR', 'Tool 실행 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.')
        state['cache'][key] = result
        self.emit(state, 'tool_response', {'tool': name, 'result': result, 'elapsed_ms': round((perf_counter() - start) * 1000, 2)})
        if not result['ok']:
            error = {'tool': name, **result['error']}
            state['errors'].append(error)
            if (result['error']['code'] == 'INVALID_KEY' and name != 'search_cinemas') or (name == 'get_boxoffice' and result['error']['code'] == 'UPSTREAM_ERROR'):
                state['fatal'] = True
        return result

    @stage
    def execute(self, state):
        if not state['tasks'] or state['question']:
            return state
        c = state['conditions']
        if state['tasks'][0]['tool']=='search_movies':
            result=self.call(state,'search_movies',state['tasks'][0]['args'])
            if result['ok']:
                state['movie_matches']=result['data']['items']
                self.ask_movie(state)
            else:
                state['question']='영화 정보를 검색하지 못했어요. 잠시 후 다시 시도하거나 정확한 제목을 알려 주실래요?'
            state['pending_field']='movie_confirmation' if state['movie_matches'] else 'movie_nm'
            return state
        if state['intent']=='places':
            result=self.call(state,'search_places',state['tasks'][0]['args'])
            if result['ok']:
                state['place_search']=result['data']
                state['places']=result['data']['items']
            return state
        if state['intent'] == 'showtimes':
            result = self.call(state, 'get_showtimes', state['tasks'][0]['args'])
            if result['ok']:
                state['showtime_search'] = result['data']
                state['showtimes'] = result['data']['items']
            return state
        if c.get('movie_cd') and any(t['tool'] == 'get_movie_detail' and t.get('args', {}).get('movie_cd') for t in state['tasks']):
            state['candidates'] = [{'movie_cd': c['movie_cd'], 'movie_nm': c.get('movie_nm', c['movie_cd'])}]
        elif any(t['tool'] == 'get_boxoffice' for t in state['tasks']):
            result = self.call(state, 'get_boxoffice', {'target_date': c.get('watch_date')})
            if result['ok']:
                state['candidates'] = result['data']['items']
        candidates = state['candidates']
        if c.get('movie_nm') and not c.get('movie_cd') and any(t['tool'] == 'get_movie_detail' for t in state['tasks']):
            candidates = [item for item in candidates if c['movie_nm'] in item['movie_nm']]
            if not candidates:
                state['question'] = '해당 영화가 조회 후보에 없습니다. 정확한 KOBIS 영화코드를 알려 주세요.'
        if state['different_movie']:
            previous_codes = {item['movie_cd'] for item in state['memory'].get('recommendations', [])}
            candidates = [item for item in candidates if item['movie_cd'] not in previous_codes]
        state['candidates'] = candidates
        pending = [item for item in candidates if item['movie_cd'] not in state['details']] if any(t['tool'] == 'get_movie_detail' for t in state['tasks']) else []
        for item in pending[:3]:
            if any(error['code'] == 'INVALID_KEY' and error['tool'] != 'search_cinemas' for error in state['errors']):
                break
            result = self.call(state, 'get_movie_detail', {'movie_cd': item['movie_cd']})
            state['details'][item['movie_cd']] = result
        if c.get('region') and any(t['tool'] == 'search_cinemas' for t in state['tasks']):
            result = self.call(state, 'search_cinemas', {'region': c['region']})
            if result['ok']:
                state['cinemas'] = result['data']['items']
        return state

    @stage
    def judge(self, state):
        state['retry'] = False
        if state['question'] or not state['tasks']:
            return state
        if not any(t['tool'] == 'get_movie_detail' for t in state['tasks']):
            return state
        c = state['conditions']
        accepted, excluded = [], []
        for candidate in state['candidates']:
            result = state['details'].get(candidate['movie_cd'])
            if result is None:
                continue
            if not result['ok']:
                excluded.append({**candidate, 'reason': result['error']['message']})
                continue
            info = result['data']
            runtime = info['runtime_minutes']
            # 광고·이동 시간은 API에서 알 수 없다. 사용자가 준 여유 시간만 더한다.
            buffer = c.get('buffer_minutes', 0)
            required = runtime + buffer
            latest = minutes(c['deadline']) - required if c.get('deadline') else None
            reason = None
            if c.get('genre') and c['genre'] not in info.get('genres', []):
                reason = '요청한 장르와 다릅니다.'
            if c.get('start_time') and latest is not None and minutes(c['start_time']) > latest:
                reason = f'필요 시간 {required}분이 시작 가능 시각부터 종료 제한까지의 시간보다 깁니다.'
            if c.get('start_time') and minutes(c['start_time']) + required >= 24 * 60:
                reason = '필요 시간이 자정을 넘어 같은 날짜 안에 관람을 마칠 수 없습니다. 날짜 또는 시작 시각을 조정해 주세요.'
            if reason:
                excluded.append({**info, 'reason': reason})
            else:
                accepted.append({**info, 'watch_date': c.get('watch_date'), 'earliest_start': c.get('start_time'), 'latest_start': clock(latest) if latest is not None else None,
                                 'required_minutes': required, 'buffer_minutes': buffer,
                                 'basis': f'러닝타임 {runtime}분 + 사용자 여유 시간 {buffer}분. 실제 상영 시간표는 별도 확인해야 합니다.'})
        state['recommendations'], state['excluded'] = accepted, excluded
        remaining = any(item['movie_cd'] not in state['details'] for item in state['candidates'])
        if not accepted and remaining and not state['fatal'] and state['replans'] < self.max_replans:
            state['replans'] += 1
            state['retry'] = True
        elif not accepted:
            state['stop_reason'] = '재계획 상한에 도달했습니다. 시작 시각이나 종료 제한 등 조건을 조정해 주시겠어요?' if remaining and state['replans'] >= self.max_replans else '조회 가능한 후보에서 조건을 충족하는 영화를 찾지 못했습니다.'
        self.emit(state, 'constraint_result', {'recommended': len(accepted), 'excluded': excluded, 'replans': state['replans'], 'retry': state['retry'], 'stop_reason': state['stop_reason']})
        return state

    @stage
    def respond(self, state):
        c = state['conditions']
        if state['question']:
            answer = state['question']
        elif state['intent']=='places':
            answer='' if state['place_search'] else '주변 장소를 조회하지 못했습니다. 오류 안내를 확인해 주세요.'
        elif state['intent'] == 'showtimes':
            # 실제 회차·좌석·조건·오류는 선택 카드에만 표시한다.
            answer = '' if state['showtime_search'] is not None else '상영시간표를 조회하지 못했습니다. 오류 안내를 확인해 주세요.'
        elif state['intent'] == 'help':
            answer = '관람 날짜, 시작 가능한 시각, 종료 제한, 희망 지역을 알려 주세요. 영화 후보의 러닝타임으로 관람 조건을 비교합니다.'
        elif state['intent'] == 'save':
            answer = '추천 카드의 저장 준비 버튼으로 계획 관리 폼을 채운 뒤, 실제 상영 시각을 확인하고 저장해 주세요.'
        elif state['intent'] == 'facts' and (state['cinemas'] or state['candidates']) and not state['details']:
            answer = '조회 결과: ' + ', '.join(item.get('movie_nm', '') for item in state['candidates']) if state['candidates'] else '지역 영화관 검색 결과를 확인해 주세요.'
        elif state['recommendations']:
            answer = f"조건과 비교할 수 있는 영화 {len(state['recommendations'])}편을 찾았습니다. 카드의 러닝타임과 판단 기준을 확인해 주세요."
        else:
            answer = state['stop_reason'] or '추천에 필요한 정보를 확보하지 못했습니다.'
        if any(v.get('estimated') for v in (r.get('data', {}) for r in state['cache'].values())):
            answer += ' 관람일 집계가 없어 최근 박스오피스를 후보로 사용했습니다. 관람일 상영을 보장하지 않습니다.'
        if state['cinemas']:
            answer += ' 영화관 검색 결과는 주변 위치 정보이며 추천 영화의 상영 여부는 확인되지 않았습니다.'
        if c.get('budget') is not None:
            answer += ' 티켓 가격을 조회할 수 없어 예산 충족 여부는 판단하지 않았습니다.'
        if state['errors']:
            answer += ' 일부 조회가 실패했습니다. 오류 안내를 확인해 주세요.'
        state['answer'] = answer
        if not state['question'] and state['stop_reason']:
            state['notice']=state['stop_reason']
        elif state['intent']=='help' and re.search(r'사용법|도움말|어떻게.*(?:사용|이용|써)',state['message']):
            state['notice']='지역과 찾을 장소를 말하거나 오른쪽에서 검색해 보세요. 마음에 드는 곳을 일정에 담고 순서·시간을 정한 뒤 날짜와 함께 저장하면 내 약속에서 다시 볼 수 있어요.'
        return state

    def build_graph(self):
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError:
            raise AgentConfigurationError('LangGraph가 없습니다. python -m pip install -r requirements.txt 를 실행해 주세요.') from None
        graph = StateGraph(AgentState)
        for name in ['analyze', 'plan', 'execute', 'judge', 'respond']:
            graph.add_node(name, getattr(self, name))
        graph.add_edge(START, 'analyze')
        graph.add_edge('analyze', 'plan')
        graph.add_edge('plan', 'execute')
        graph.add_edge('execute', 'judge')
        graph.add_conditional_edges('judge', lambda s: 'plan' if s['retry'] else 'respond', {'plan': 'plan', 'respond': 'respond'})
        graph.add_edge('respond', END)
        return graph.compile()

    def run(self, session_id, message, course=None):
        memory=store.get_memory(session_id)
        if course is not None:
            incoming=CourseContext.model_validate(course).model_dump(mode='json',exclude_unset=True)
            # 화면이 보내는 현재 일정의 완전한 검색 문맥 스냅샷이다.
            # 빠진 키는 삭제된 장소이므로 이전 장소를 다시 합치지 않는다.
            memory['course']=incoming
        state = self.initial_state(session_id, message, memory)
        result = self.build_graph().invoke(state, {'recursion_limit': 30})
        recommendations = [{'movie_cd': item['movie_cd'], 'movie_nm': item['movie_nm']} for item in result['recommendations']]
        if result['intent'] != 'plan' or result['question']:
            recommendations = state['memory'].get('recommendations', [])
        active = result['intent'] if result['intent'] in {'plan', 'showtimes','places'} else state['memory'].get('active_intent', state['memory'].get('intent'))
        pending_field, pending_time = result.get('pending_field'), result.get('pending_time')
        if result['intent'] in {'help', 'facts', 'save'} and active in {'showtimes','places'}:
            pending_field, pending_time = state['memory'].get('pending_field'), state['memory'].get('pending_time')
        changed_time = next((key for key in ('deadline', 'start_time') if key in result['updated_fields']), state['memory'].get('last_time_field'))
        store.save_memory(session_id, {'intent': result['intent'], 'active_intent': active, 'pending_field': pending_field, 'pending_time': pending_time,
                                       'pending_movies':result['movie_matches'],
                                       'course':result['course'],'last_time_field': changed_time, 'conditions': result['conditions'], 'message': message[:1000], 'answer': result['answer'][:1000],
                                       'recommendations': recommendations})
        return {key: result[key] for key in ['session_id', 'run_id', 'answer', 'question', 'notice', 'movie_matches', 'conditions', 'recommendations', 'excluded', 'cinemas', 'showtimes', 'showtime_search', 'places','place_search','course','events', 'errors', 'replans']}
