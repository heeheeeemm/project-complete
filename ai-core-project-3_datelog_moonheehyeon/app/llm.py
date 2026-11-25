"""OpenAI 호환 채팅 API. 조건 추출과 Tool 선택만 LLM에 맡긴다."""
import json
import os
import re
from datetime import datetime, timedelta, timezone

import requests

from tools_start import catalog
from .schemas import Analysis
from .showtime_request import parse_showtime_request
from .place_request import parse_place_request
from .movie_request import parse_movie_request


class AgentConfigurationError(Exception):
    def __init__(self, message, code='CONFIGURATION_ERROR', *, provider_code=None, retry_after=None):
        super().__init__(message)
        self.code = code
        self.provider_code = provider_code
        self.retry_after = retry_after


def rate_limit_details(response):
    """허용된 오류 코드와 숫자형 재시도 시간만 읽는다. 원문은 노출하지 않는다."""
    allowed = {'rate_limit_exceeded', 'rate_limit_error', 'slow_down', 'insufficient_quota',
               'credit_balance_exhausted', 'organization_spend_limit_exceeded',
               'project_spend_limit_exceeded', 'organization_usage_limit_exceeded'}
    provider_code = 'UNKNOWN'
    try:
        body = response.json()
        detail = body.get('error', body) if isinstance(body, dict) else {}
        if isinstance(detail, dict):
            for value in (detail.get('code'), detail.get('type')):
                if isinstance(value, str) and value in allowed:
                    provider_code = value
                    break
    except ValueError:
        pass
    retry = response.headers.get('Retry-After', '')
    retry_after = int(retry) if isinstance(retry, str) and retry.isascii() and retry.isdigit() and len(retry) <= 6 else None
    return provider_code, retry_after


def analyze_request(message, memory):
    if re.fullmatch(r'\s*(?:최근\s*|현재\s*)?박스오피스\s*(?:순위|목록)?\s*(?:알려\s*줘|조회해\s*줘|보여\s*줘|조회)?[.!?]?\s*',message):
        return {'intent':'facts','conditions':{},'reason':'관람 제약이 없는 박스오피스 사실 조회','tool_names':['get_boxoffice']}
    explicit = parse_movie_request(message,memory) or parse_place_request(message,memory) or parse_showtime_request(message, memory)
    if explicit is not None:
        return explicit
    key, model = os.getenv('OPENAI_API_KEY'), os.getenv('OPENAI_MODEL')
    if not key or not model:
        raise AgentConfigurationError('.env에 OPENAI_API_KEY와 OPENAI_MODEL을 설정해 주세요.')
    today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    # Tool 선택에 필요한 명함만 전달한다. 전체 출력 스키마는 레지스트리에 유지한다.
    tool_cards = [{key: tool[key] for key in ('name', 'description', 'parameters')} for tool in catalog()]
    system = f'''너는 영화 관람 계획 요청 분석기다. 한국 기준 오늘은 {today}다.
사용자 입력과 직전 대화 요약에서 의도·조건을 추출하고 등록된 Tool 설명에 따라 필요한 Tool을 선택한다.
조건은 이번 발화에서 명시적으로 새로 말하거나 바꾼 항목만 반환한다. 이전 조건 병합은 서버가 한다.
말하지 않은 조건 필드는 JSON에서 생략한다. 사용자가 조건을 해제한 경우에만 해당 필드를 null로 반환한다.
시간대가 불명확한 '3시'는 추측하지 말고 question으로 되묻는다. 오후 3시는 15:00이다.
날짜는 YYYY-MM-DD, 시각은 HH:MM. 없는 날짜/시각/지역/예산/여유 시간/영화코드는 만들지 않는다.
시작 시각이 없고 종료 제약만 있으면 되묻는다. 지역/장르/예산은 선택 조건이다.
영화명만으로 영화코드를 지어내지 않는다. 다른 영화 요청은 different_movie=true.
intent: plan(후보 추천·러닝타임 비교), showtimes(실제 상영시간표·잔여석), facts(사실조회), help(인사/사용법), save(확정/저장).
식당/밥집/카페 추천은 intent=places, search_places를 선택한다. place_kind=restaurant/cafe, cuisine은 양식/한식/일식/중식 등 명시한 것만 담는다.
"그 근처"는 지역명이 아니다. 기존 지역·선택한 영화관·코스는 서버에서 연결한다. 음식 요청은 영화명·날짜·브랜드를 지우지 않는다.
help에는 Tool이 필요 없다. save는 화면에서 최종 확인한다.
후보 미정이면 get_boxoffice→get_movie_detail, 특정 코드면 get_movie_detail,
지역 주변 영화관이 필요하면 search_cinemas를 선택한다.
특정 영화·지역에서 관람할 시간이나 잔여석을 찾는 요청은 intent=showtimes, get_showtimes를 선택한다.
CGV·롯데시네마·메가박스 통합 조회다. 특정 브랜드를 명시하면 brands에 cgv/lotte/megabox를 넣고, 모두 조회는 세 값을 넣는다. 브랜드가 없으면 생략한다.
이때 movie_nm에 작품명만 담고 영화코드는 만들지 않는다. 예: 부산 서면에서 <폭설> → region=부산 서면, movie_nm=폭설.
인물명·출연자·모호한 제목은 movie_nm으로 확정하지 않는다. movie_query에 검색어를 담고 search_movies를 선택해 실제 작품을 먼저 확인한다.
새 데이트를 시작하면 이전 날짜·시각을 임의로 재사용하지 말고 새 발화에 명시한 조건만 사용한다.
직전 intent가 showtimes이고 날짜·시간·영화·지역을 바꾸면 showtimes를 유지한다.
active_intent가 showtimes이면 인사나 짧은 답변 뒤에도 기존 시간표 작업을 유지한다. missing movie_nm일 때만 제목을 묻는다.
"5시 30분 전에 끝나야 해", "아니 그럼 6시 이전"은 시작 시각이 아니라 deadline 변경이다. 기존 영화·지역·브랜드·시작 시각을 생략하거나 지우지 않는다.
"전에/이전"은 deadline_inclusive=false, "까지"는 true다. 오후 시작 조건으로 오전 종료가 불가능하면 같은 오후 시각으로 연결하고, 둘 다 가능하면 오전·오후만 묻는다.
JSON 객체만 반환한다. reason은 짧은 판단 근거이며 내부 사고 과정을 적지 않는다.
출력 JSON Schema: {json.dumps(Analysis.model_json_schema(), ensure_ascii=False)}
등록 Tool: {json.dumps(tool_cards, ensure_ascii=False)}'''
    base_url = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1').rstrip('/')
    try:
        res = requests.post(f'{base_url}/chat/completions', headers={'Authorization': f'Bearer {key}'}, json={
            'model': model, 'messages': [
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': json.dumps({'previous_summary': memory, 'message': message}, ensure_ascii=False)},
            ], 'response_format': {'type': 'json_object'}, 'max_completion_tokens': 1024,
        }, timeout=30)
        res.raise_for_status()
        content = res.json()['choices'][0]['message']['content']
        return Analysis.model_validate_json(content).model_dump(mode='json', exclude_unset=True)
    except requests.Timeout:
        raise AgentConfigurationError('LLM 응답 시간이 초과됐습니다. 잠시 후 다시 시도해 주세요.', 'TIMEOUT') from None
    except requests.ConnectionError:
        raise AgentConfigurationError('LLM 서버에 연결할 수 없습니다. 접속 주소와 네트워크·방화벽 설정을 확인해 주세요.', 'CONNECTION_ERROR') from None
    except requests.HTTPError as error:
        status = error.response.status_code if error.response is not None else 0
        if status == 429:
            provider_code, retry_after = rate_limit_details(error.response)
            if provider_code in {'rate_limit_exceeded', 'rate_limit_error', 'slow_down'}:
                guidance = '요청 빈도 또는 토큰 처리량 제한입니다. 호출 간격과 해당 모델의 한도를 확인해 주세요.'
            elif provider_code != 'UNKNOWN':
                guidance = '제공 서비스가 크레딧 또는 모델·프로젝트 할당량 제한을 반환했습니다. GMS 전체 잔액과 서비스별 한도를 함께 확인해 주세요.'
            else:
                guidance = '세부 제한 코드가 확인되지 않았습니다. GMS의 해당 모델 호출 한도와 서비스 상태 확인이 필요합니다.'
            if retry_after is not None:
                guidance += f' 서버가 안내한 재시도 대기 시간: {retry_after}초.'
            raise AgentConfigurationError(f'LLM HTTP 429 [{provider_code}]: {guidance}', 'HTTP_429',
                                          provider_code=provider_code, retry_after=retry_after) from None
        guidance = {
            400: '모델명과 JSON 응답 형식 지원 여부를 확인해 주세요.',
            401: 'API 키와 접속 주소의 제공업체가 일치하는지 확인해 주세요. GMS 키는 GMS 주소를 사용해야 합니다.',
            403: '해당 키의 모델·서비스 사용 권한을 확인해 주세요.',
            404: '접속 주소와 해당 서비스에서 제공하는 모델명을 확인해 주세요.',
        }.get(status, 'LLM 제공 서비스의 상태를 확인하고 잠시 후 다시 시도해 주세요.')
        raise AgentConfigurationError(f'LLM HTTP {status}: {guidance}', f'HTTP_{status}') from None
    except requests.exceptions.JSONDecodeError:
        raise AgentConfigurationError('LLM 응답이 필요한 JSON 형식과 다릅니다. 모델의 JSON 출력 지원 여부를 확인해 주세요.', 'INVALID_RESPONSE') from None
    except requests.RequestException:
        raise AgentConfigurationError('LLM 요청을 전송하지 못했습니다. 연결 설정을 확인해 주세요.', 'REQUEST_ERROR') from None
    except (ValueError, KeyError, IndexError, TypeError):
        raise AgentConfigurationError('LLM 응답이 필요한 JSON 형식과 다릅니다. 모델의 JSON 출력 지원 여부를 확인해 주세요.', 'INVALID_RESPONSE') from None
