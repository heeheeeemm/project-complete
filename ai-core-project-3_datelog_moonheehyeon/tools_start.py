"""영화 Tool: 기존 ①응답 ②Tool ③API ④등록 구조를 유지한다."""
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Generic, Literal, TypeVar
import requests
from dotenv import load_dotenv
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

load_dotenv(Path(__file__).with_name('.env'))

# ① 공통 응답
def ok(data):
    return {'ok': True, 'data': data}

def fail(code, message):
    return {'ok': False, 'error': {'code': code, 'message': message}}

# ② Tool 명함
Data = TypeVar('Data')


class ToolSuccess(BaseModel, Generic[Data]):
    ok: Literal[True]
    data: Data


class ToolError(BaseModel):
    code: Literal['BAD_ARGUMENT', 'INVALID_KEY', 'NOT_FOUND', 'NO_DATA', 'NO_RUNTIME', 'UPSTREAM_ERROR', 'ACCESS_DENIED', 'TIMEOUT', 'CONNECTION_ERROR']
    message: str


class ToolFailure(BaseModel):
    ok: Literal[False]
    error: ToolError


class MovieCandidate(BaseModel):
    movie_cd: str = Field(pattern=r'^\d{8}$')
    movie_nm: str = Field(min_length=1)
    rank: str | None = None


class BoxofficeData(BaseModel):
    items: list[MovieCandidate]
    requested_date: date
    query_date: date
    estimated: bool
    source: str


class MovieDetailData(BaseModel):
    movie_cd: str = Field(pattern=r'^\d{8}$')
    movie_nm: str = Field(min_length=1)
    runtime_minutes: int = Field(gt=0)
    genres: list[str]
    ratings: list[str]
    source: str


class Cinema(BaseModel):
    name: str = Field(min_length=1)
    address: str | None
    url: str | None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class CinemaData(BaseModel):
    items: list[Cinema]
    source: str
    notice: str


def normalize_result(result):
    """Agent 경계에서도 성공/실패 봉투를 검증한다. 오류 원문은 반환하지 않는다."""
    try:
        return TypeAdapter(ToolSuccess[dict] | ToolFailure).validate_python(result).model_dump(mode='json')
    except ValidationError:
        return fail('UPSTREAM_ERROR', 'Tool 응답 형식이 명세와 다릅니다.')


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    func: Callable
    output_model: type[BaseModel]
    tool_type: Literal['external_api', 'local_server_api'] = 'external_api'

    @property
    def result_adapter(self):
        return TypeAdapter(ToolSuccess[self.output_model] | ToolFailure)

    def run(self, **kwargs):
        try:
            result = self.func(**kwargs)
        except (TypeError, ValueError):
            return fail('BAD_ARGUMENT', '입력값이 규약과 다릅니다.')
        except Exception:
            return fail('UPSTREAM_ERROR', 'Tool 실행 중 오류가 발생했습니다.')
        try:
            return self.result_adapter.validate_python(result).model_dump(mode='json')
        except ValidationError:
            return fail('UPSTREAM_ERROR', 'Tool 응답 형식이 명세와 다릅니다.')

# ③ 외부 API
KOBIS_URL = 'https://www.kobis.or.kr/kobisopenapi/webservice/rest'

def _get(url, *, params=None, headers=None):
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code in (401, 403):
            if url.startswith('https://dapi.kakao.com/'):
                if response.status_code == 401:
                    message = '카카오 HTTP 401: 앱의 REST API 키와 키 활성 상태를 확인해 주세요. JavaScript 키는 사용할 수 없습니다.'
                else:
                    message = '카카오 HTTP 403: 카카오맵 사용 설정(ON), REST API 키의 활성 상태·API 사용 권한·호출 허용 IP 설정을 확인해 주세요.'
                return fail('INVALID_KEY', message)
            return fail('INVALID_KEY', f'외부 API HTTP {response.status_code}: 키 또는 사용 권한을 확인해 주세요.')
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            return fail('UPSTREAM_ERROR', '외부 API 응답 형식이 올바르지 않습니다.')
        if body.get('faultInfo'):
            code = str(body['faultInfo'].get('errorCode', ''))
            return fail('INVALID_KEY' if code in {'010', '011', '012'} else 'UPSTREAM_ERROR', 'KOBIS 사용 설정을 확인해 주세요.')
        return ok(body)
    except (requests.RequestException, ValueError):
        return fail('UPSTREAM_ERROR', '외부 API 응답을 받지 못했습니다. 잠시 후 다시 시도해 주세요.')

def get_boxoffice(target_date: str | None = None):
    yesterday = datetime.now(timezone(timedelta(hours=9))).date() - timedelta(days=1)
    try:
        if target_date is not None and (not isinstance(target_date, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', target_date)):
            raise ValueError('invalid date format')
        requested = date.fromisoformat(target_date) if target_date is not None else yesterday
    except (ValueError, TypeError):
        return fail('BAD_ARGUMENT', 'target_date는 YYYY-MM-DD 형식이어야 합니다.')
    query_date = min(requested, yesterday)
    key = os.getenv('KOBIS_API_KEY')
    if not key:
        return fail('INVALID_KEY', '.env에 KOBIS_API_KEY를 설정해 주세요.')
    result = _get(f'{KOBIS_URL}/boxoffice/searchDailyBoxOfficeList.json', params={'key': key, 'targetDt': query_date.strftime('%Y%m%d')})
    if not result['ok']:
        return result
    try:
        raw = result['data']['boxOfficeResult']['dailyBoxOfficeList']
        items = [{'movie_cd': it['movieCd'], 'movie_nm': it['movieNm'], 'rank': it.get('rank')} for it in raw if it.get('movieCd') and it.get('movieNm')]
    except (KeyError, TypeError, AttributeError):
        return fail('UPSTREAM_ERROR', '박스오피스 응답 형식이 올바르지 않습니다.')
    if not items:
        return fail('NO_DATA', '해당 기준일의 박스오피스 결과가 없습니다.')
    return ok({'items': items, 'requested_date': requested.isoformat(), 'query_date': query_date.isoformat(), 'estimated': requested != query_date, 'source': 'KOBIS 일별 박스오피스'})

def get_movie_detail(movie_cd: str):
    if not isinstance(movie_cd, str) or not re.fullmatch(r'\d{8}', movie_cd):
        return fail('BAD_ARGUMENT', 'movie_cd는 8자리 영화코드여야 합니다.')
    key = os.getenv('KOBIS_API_KEY')
    if not key:
        return fail('INVALID_KEY', '.env에 KOBIS_API_KEY를 설정해 주세요.')
    result = _get(f'{KOBIS_URL}/movie/searchMovieInfo.json', params={'key': key, 'movieCd': movie_cd})
    if not result['ok']:
        return result
    try:
        info = result['data']['movieInfoResult']['movieInfo']
        if not info:
            return fail('NOT_FOUND', '영화 상세정보가 없습니다.')
        runtime = str(info.get('showTm', '')).strip()
        if not runtime.isdigit() or int(runtime) <= 0:
            return fail('NO_RUNTIME', '러닝타임이 없어 시간 조건을 판단할 수 없습니다.')
        return ok({'movie_cd': info['movieCd'], 'movie_nm': info['movieNm'], 'runtime_minutes': int(runtime), 'genres': [v['genreNm'] for v in info.get('genres', [])], 'ratings': [v['watchGradeNm'] for v in info.get('audits', [])], 'source': 'KOBIS 영화 상세정보'})
    except (KeyError, TypeError, AttributeError):
        return fail('UPSTREAM_ERROR', '영화 상세 응답 형식이 올바르지 않습니다.')

def search_cinemas(region: str):
    if not isinstance(region, str) or not region.strip() or len(region) > 100:
        return fail('BAD_ARGUMENT', '검색할 지역을 입력해 주세요.')
    key = os.getenv('KAKAO_REST_API_KEY')
    if not key:
        return fail('INVALID_KEY', '.env에 KAKAO_REST_API_KEY를 설정해 주세요.')
    result = _get('https://dapi.kakao.com/v2/local/search/keyword.json', params={'query': f'{region.strip()} 영화관', 'size': 5}, headers={'Authorization': f'KakaoAK {key}'})
    if not result['ok']:
        return result
    try:
        items = [{'name': it['place_name'], 'address': it.get('road_address_name') or it.get('address_name'), 'url': it.get('place_url'),
                  'lat': float(it['y']) if it.get('y') else None, 'lng': float(it['x']) if it.get('x') else None} for it in result['data']['documents']]
    except (KeyError, TypeError, ValueError):
        return fail('UPSTREAM_ERROR', '영화관 응답 형식이 올바르지 않습니다.')
    if not items:
        return fail('NO_DATA', '해당 지역의 영화관을 찾지 못했습니다.')
    return ok({'items': items, 'source': '카카오 로컬', 'notice': '주변 영화관 정보이며 영화 상영 여부·시간표는 확인되지 않았습니다.'})

from app.showtimes import ShowtimesData
from app.showtime_search import search_showtimes as get_showtimes
from app.places import PlaceData, search_places
from app.movie_lookup import MovieMatches, search_movies

# ④ 등록: 모두 외부 API Tool. 로컬 서버 Tool은 심화 범위다.
TOOLS = {t.name: t for t in [
    Tool('search_movies','불완전한 영화 제목이나 출연자 이름으로 KOBIS 영화 목록·필모그래피를 검색해 사용자에게 확인할 후보를 찾는다.',
         {'type':'object','properties':{'query':{'type':'string','minLength':1,'maxLength':100}},'required':['query'],'additionalProperties':False},search_movies,MovieMatches),
    Tool('search_places','선택한 영화관·식당 또는 기억한 지역 주변의 실제 식당/카페를 카카오에서 검색한다. 평점·영업시간·가격을 생성하지 않는다.',
         {'type':'object','properties':{'region':{'type':'string'},'kind':{'enum':['restaurant','cafe','place']},'cuisine':{'type':['string','null']},'anchor_name':{'type':['string','null']},'lat':{'type':['number','null']},'lng':{'type':['number','null']}},'required':['region','kind'],'additionalProperties':False},search_places,PlaceData),
    Tool('get_boxoffice', '후보를 정하지 않았거나 대안 영화가 필요할 때 일별 순위와 영화코드를 조회한다.', {'type': 'object', 'properties': {'target_date': {'type': ['string', 'null'], 'description': 'YYYY-MM-DD. 생략하면 한국시간 어제. 미래는 어제로 보정.'}}, 'additionalProperties': False}, get_boxoffice, BoxofficeData),
    Tool('get_movie_detail', '후보 영화코드의 러닝타임·장르·등급으로 조건을 판단할 때 조회한다.', {'type': 'object', 'properties': {'movie_cd': {'type': 'string', 'pattern': '^\\d{8}$'}}, 'required': ['movie_cd'], 'additionalProperties': False}, get_movie_detail, MovieDetailData),
    Tool('search_cinemas', '사용자가 지정한 지역의 영화관 이름·주소·링크가 필요할 때 검색한다. 시간표는 제공하지 않는다.', {'type': 'object', 'properties': {'region': {'type': 'string', 'minLength': 1, 'maxLength': 100}}, 'required': ['region'], 'additionalProperties': False}, search_cinemas, CinemaData),
    Tool('get_showtimes', '영화명·지역·날짜의 실제 CGV·롯데시네마·메가박스 회차와 잔여석을 통합 조회한다. KOBIS 영화코드는 사용하지 않는다.',
         {'type': 'object', 'properties': {'region': {'type': 'string'}, 'movie_nm': {'type': 'string'}, 'watch_date': {'type': 'string', 'description': 'YYYY-MM-DD'}, 'start_time': {'type': 'string', 'description': 'HH:MM, 이 시각 포함 이후'}, 'deadline': {'type': ['string', 'null']}, 'deadline_inclusive': {'type': 'boolean', 'description': '까지=true, 전에/이전=false'}, 'buffer_minutes': {'type': 'integer', 'minimum': 0, 'maximum': 240}, 'brands': {'type': 'array', 'items': {'enum': ['cgv', 'lotte', 'megabox']}, 'minItems': 1, 'maxItems': 3}}, 'required': ['region', 'movie_nm', 'watch_date'], 'additionalProperties': False}, get_showtimes, ShowtimesData),
]}

def catalog():
    return [{'name': t.name, 'description': t.description, 'tool_type': t.tool_type,
             'parameters': t.parameters, 'output_schema': t.result_adapter.json_schema()} for t in TOOLS.values()]

if __name__ == '__main__':
    import json
    print(json.dumps(catalog(), ensure_ascii=False, indent=2))
    for name, args in [('get_boxoffice', {}), ('get_movie_detail', {'movie_cd': '20124079'}), ('search_cinemas', {'region': '강남'}), ('get_movie_detail', {'movie_cd': ''})]:
        print(name, TOOLS[name].run(**args))
