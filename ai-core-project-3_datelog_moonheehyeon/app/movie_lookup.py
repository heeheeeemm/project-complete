"""제목 검색과 동명이인을 포함한 영화인 필모그래피로 확인용 후보를 조회한다."""
import os
import re
from datetime import date
from pydantic import BaseModel, Field


class MovieMatch(BaseModel):
    movie_cd: str = Field(pattern=r'^\d{8}$')
    movie_nm: str = Field(min_length=1)
    year: str | None = None
    open_date: str | None = None


class MovieMatches(BaseModel):
    items: list[MovieMatch]
    source: str = 'KOBIS 영화 목록·영화인 필모그래피'
    warnings: list[str] = Field(default_factory=list)


def search_movies(query):
    from tools_start import _get, ok, fail, KOBIS_URL
    if not isinstance(query,str) or not 1 <= len(query.strip()) <= 100:
        return fail('BAD_ARGUMENT','찾으려는 영화나 출연자 이름을 알려 주세요.')
    key=os.getenv('KOBIS_API_KEY')
    if not key:
        return fail('INVALID_KEY','영화 검색을 위한 KOBIS 키 설정을 확인해 주세요.')
    query=query.strip()
    titles=_get(f'{KOBIS_URL}/movie/searchMovieList.json',params={'key':key,'movieNm':query,'itemPerPage':20})
    people=_get(f'{KOBIS_URL}/people/searchPeopleList.json',params={'key':key,'peopleNm':query,'itemPerPage':10})
    items={}
    warnings=[]
    def add(movie):
        code=str(movie.get('movieCd',''))
        if re.fullmatch(r'\d{8}',code) and movie.get('movieNm'):
            opened=str(movie.get('openDt',''))
            try:
                opened=date.fromisoformat(f'{opened[:4]}-{opened[4:6]}-{opened[6:]}').isoformat() if re.fullmatch(r'\d{8}',opened) else None
            except ValueError:
                opened=None
            items.setdefault(code,{'movie_cd':code,'movie_nm':movie['movieNm'],'year':movie.get('prdtYear') or None,'open_date':opened})
    try:
        if titles['ok']:
            for movie in titles['data']['movieListResult']['movieList']:
                add(movie)
        if people['ok']:
            exact=[p for p in people['data']['peopleListResult']['peopleList'] if p.get('peopleNm')==query]
            for person in exact[:3]:
                details=_get(f'{KOBIS_URL}/people/searchPeopleInfo.json',params={'key':key,'peopleCd':person['peopleCd']})
                if not details['ok']:
                    warnings.append('일부 영화인의 참여 작품을 확인하지 못했어요.')
                    continue
                for movie in details['data']['peopleInfoResult']['peopleInfo'].get('filmos',[]):
                    add(movie)
        if not titles['ok'] or not people['ok']:
            warnings.append('영화명 또는 영화인 검색 일부가 완료되지 않았어요.')
        if not items and (not titles['ok'] or not people['ok']):
            return titles if not titles['ok'] else people
        exact=[m for m in items.values() if re.sub(r'\W','',m['movie_nm']).casefold()==re.sub(r'\W','',query).casefold()]
        ordered=sorted(exact or items.values(),key=lambda m:(m['open_date'] or '',m['year'] or '',m['movie_cd']),reverse=True)
        return ok(MovieMatches(items=ordered[:20],warnings=warnings).model_dump(mode='json'))
    except (KeyError,TypeError,AttributeError):
        return fail('UPSTREAM_ERROR','영화 검색 결과를 읽지 못했어요. 잠시 후 다시 시도해 주세요.')
