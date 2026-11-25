"""롯데시네마·메가박스의 공식 웹 읽기 전용 조회 어댑터."""
import html
import json
import re
from datetime import date, datetime, time

import requests

from .showtimes import (CgvError, KST, ShowtimesData, WEB_HEADERS, failure, make_showtime,
                        normalized, select_theaters)

LOTTE_BOOK = 'https://www.lottecinema.co.kr/NLCHS/Ticketing'
MEGA_BOOK = 'https://www.megabox.co.kr/booking'


def post_json(url, *, brand, referer, data=None, files=None):
    try:
        result = requests.post(url, data=data, files=files,
                               headers={**WEB_HEADERS, 'Referer': referer, 'X-Requested-With': 'XMLHttpRequest'}, timeout=(3, 8))
        if result.status_code in (401, 403):
            raise CgvError('ACCESS_DENIED', f'{brand}가 시간표 조회 접근을 제한했습니다. 공식 예매 화면에서 확인해 주세요.')
        if result.status_code != 200:
            raise CgvError('UPSTREAM_ERROR', f'{brand} 시간표 서버가 정상 응답하지 않았습니다.')
        body = result.json()
        if not isinstance(body, dict):
            raise ValueError('invalid envelope')
        return body
    except requests.Timeout:
        raise CgvError('TIMEOUT', f'{brand} 시간표 응답 시간이 초과되었습니다.') from None
    except requests.RequestException:
        raise CgvError('CONNECTION_ERROR', f'{brand} 서버에 연결하지 못했습니다.') from None
    except (ValueError, TypeError):
        raise CgvError('UPSTREAM_ERROR', f'{brand} 시간표 응답 형식이 올바르지 않습니다.') from None


def list_at(data, *keys):
    for key in keys:
        if not isinstance(data, dict) or key not in data:
            raise ValueError('missing response field')
        data = data[key]
    if not isinstance(data, list) or any(not isinstance(x, dict) for x in data):
        raise ValueError('invalid list')
    return data


def query_context(region, movie_nm, watch_date, start_time, deadline, buffer_minutes, deadline_inclusive=True):
    if not isinstance(region, str) or not region.strip() or len(region) > 100 or not isinstance(movie_nm, str) or not normalized(movie_nm) or len(movie_nm) > 200:
        raise ValueError('invalid query')
    day = date.fromisoformat(watch_date)
    if day.isoformat() != watch_date:
        raise ValueError('invalid date')
    for value in (start_time, deadline):
        if value is not None and (not isinstance(value, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value)):
            raise ValueError('invalid time')
    if not isinstance(buffer_minutes, int) or isinstance(buffer_minutes, bool) or not 0 <= buffer_minutes <= 240:
        raise ValueError('invalid buffer')
    if not isinstance(deadline_inclusive, bool):
        raise ValueError('invalid boundary')
    earliest = datetime.combine(day, time.fromisoformat(start_time), KST)
    latest = datetime.combine(day, time.fromisoformat(deadline), KST) if deadline else None
    if latest and latest <= earliest:
        raise ValueError('invalid deadline')
    return day, earliest, latest


def lotte_request(method, **fields):
    payload = {'MethodName': method, 'channelType': 'HO', 'osType': 'W', 'osVersion': WEB_HEADERS['User-Agent'], **fields}
    result = post_json('https://www.lottecinema.co.kr/LCWS/Ticketing/TicketingData.aspx', brand='롯데시네마', referer=LOTTE_BOOK,
                       files={'paramList': (None, json.dumps(payload, ensure_ascii=False))})
    if result.get('IsOK') not in (True, 'true'):
        raise CgvError('UPSTREAM_ERROR', '롯데시네마가 정상 시간표 응답을 반환하지 않았습니다.')
    return result


def mega_request(day, theater=None):
    fields = {'playDe': day.strftime('%Y%m%d'), 'sellChnlCd': 'ONLINE', 'brchNoListCnt': '1',
              'areaCd1': theater['regnGrpCd'] if theater else '11', 'spclbYn1': 'N', 'theabKindCd1': ''}
    if theater:
        fields['brchNo1'] = theater['siteNo']
    result = post_json('https://www.megabox.co.kr/on/oh/ohb/SimpleBooking/selectBokdList.do', brand='메가박스', referer=MEGA_BOOK, data=fields)
    if result.get('statCd') not in (0, '0'):
        raise CgvError('UPSTREAM_ERROR', '메가박스가 정상 시간표 응답을 반환하지 않았습니다.')
    return result


def lotte_catalog(page, region, movie_nm):
    groups = list_at(page, 'CinemaDivison', 'AreaDivisions', 'Items')
    raw = list_at(page, 'Cinemas', 'Cinemas', 'Items')
    movies = list_at(page, 'Movies', 'Movies', 'Items')
    theaters = [{'siteNo': str(x['CinemaID']), 'siteNm': x['CinemaNameKR'], 'regnGrpCd': str(x['DetailDivisionCode']), 'division': str(x['DivisionCode'])}
                for x in raw if str(x.get('DivisionCode')) == '1']
    data = {'siteInfo': theaters, 'regionInfo': [{'comCdval': str(x['DetailDivisionCode']), 'comCdvalNm': x['GroupNameKR']} for x in groups]}
    # 공식 지점명은 부산본점이며 서면(부전동)에 위치한다. 지점 코드는 목록에서 받는다.
    selected = select_theaters(data, region, brand='롯데시네마', aliases={'서면': '부산본점'})
    movie_ids = {str(x['RepresentationMovieCode']) for x in movies if normalized(str(x.get('MovieNameKR', ''))) == normalized(movie_nm)}
    if len(movie_ids) > 1:
        raise CgvError('BAD_ARGUMENT', '롯데시네마에서 같은 제목의 작품이 여러 개 조회되었습니다. 작품을 구체적으로 알려 주세요.')
    return selected, next(iter(movie_ids), None)


def mega_catalog(page, region):
    raw = list_at(page, 'areaBrchList')
    theaters = [{'siteNo': str(x['brchNo']), 'siteNm': html.unescape(x['brchNm']), 'regnGrpCd': str(x['areaCd'])} for x in raw]
    groups = {str(x['areaCd']): str(x['areaCdNm']) for x in raw}
    return select_theaters({'siteInfo': theaters, 'regionInfo': [{'comCdval': code, 'comCdvalNm': name} for code, name in groups.items()]}, region, brand='메가박스')


def provider_search(brand, region, movie_nm, watch_date, start_time='00:00', deadline=None, buffer_minutes=0, deadline_inclusive=True):
    name, book = ('롯데시네마', LOTTE_BOOK) if brand == 'lotte' else ('메가박스', MEGA_BOOK)
    try:
        day, earliest, latest = query_context(region, movie_nm, watch_date, start_time, deadline, buffer_minutes, deadline_inclusive)
    except (ValueError, TypeError):
        return failure('BAD_ARGUMENT', '지역·영화명·날짜(YYYY-MM-DD)·시각(HH:MM)을 확인해 주세요.')
    try:
        if brand == 'lotte':
            theaters, movie_id = lotte_catalog(lotte_request('GetTicketingPageTOBE', memberOnNo='0'), region, movie_nm)
        else:
            theaters, movie_id = mega_catalog(mega_request(day), region), None
        items, checked, warnings, errors = [], [], [], []
        for theater in theaters:
            try:
                if brand == 'lotte':
                    rows = [] if movie_id is None else list_at(lotte_request('GetPlaySequence', playDate=day.isoformat(),
                        cinemaID='|'.join((theater['division'], theater['regnGrpCd'], theater['siteNo'])), representationMovieCode=movie_id), 'PlaySeqs', 'Items')
                else:
                    rows = list_at(mega_request(day, theater), 'movieFormList')
                received = datetime.now(KST)
                theater_items = []
                for raw in rows:
                    title = raw.get('MovieNameKR', '') if brand == 'lotte' else html.unescape(raw.get('rpstMovieNm') or raw.get('movieNm') or '')
                    if normalized(title) != normalized(movie_nm):
                        continue
                    if brand == 'lotte':
                        if raw.get('PlayDt') != day.isoformat() or str(raw.get('CinemaID')) != theater['siteNo'] or str(raw.get('RepresentationMovieCode')) != movie_id:
                            raise ValueError('mismatched schedule')
                        if raw.get('ScreenID') is None or raw.get('PlaySequence') is None:
                            raise ValueError('missing identity')
                        identity = f"{raw['CinemaID']}:{day.isoformat()}:{raw['ScreenID']}:{raw['PlaySequence']}"
                        fields = dict(schedule_id=identity, movie_id=movie_id, screen=raw.get('ScreenNameKR'), format_name=raw.get('FilmNameKR'),
                            start_raw=raw['StartTime'], end_raw=raw['EndTime'], remaining=raw.get('BookingSeatCount'), total=raw.get('TotalSeatCount'), bookable=raw.get('IsBookingYN') != 'N')
                    else:
                        if raw.get('playDe') != day.strftime('%Y%m%d') or str(raw.get('brchNo')) != theater['siteNo']:
                            raise ValueError('mismatched schedule')
                        if not raw.get('playSchdlNo') or not raw.get('movieNo'):
                            raise ValueError('missing identity')
                        fields = dict(schedule_id=raw['playSchdlNo'], movie_id=raw['movieNo'], screen=html.unescape(raw.get('theabExpoNm') or ''),
                            format_name=html.unescape(raw.get('playKindNm') or ''), start_raw=raw['playStartTime'], end_raw=raw['playEndTime'],
                            remaining=raw.get('restSeatCnt'), total=raw.get('totSeatCnt'), bookable=raw.get('bokdAbleAt') != 'N' and raw.get('brchBokdUnableAt') != 'Y')
                    item = make_showtime(brand=brand, brand_name=name, movie_nm=title, cinema_name=theater['siteNm'], cinema_id=theater['siteNo'],
                        day=day, earliest=earliest, latest=latest, buffer_minutes=buffer_minutes, checked_at=received, booking_url=book, deadline_inclusive=deadline_inclusive, **fields)
                    if item is not None:
                        theater_items.append(item)
                items.extend(theater_items)
                checked.append(name + ' ' + theater['siteNm'])
            except (ValueError, TypeError, KeyError, AttributeError):
                error = CgvError('UPSTREAM_ERROR', f'{name} 시간표 응답 형식이 올바르지 않습니다.')
                errors.append(error)
                warnings.append(f"{name} {theater['siteNm']}: {error.message}")
            except CgvError as error:
                errors.append(error)
                warnings.append(f"{name} {theater['siteNm']}: {error.message}")
        if not checked:
            raise errors[0]
        unique = {item.schedule_id: item for item in items}
        data = ShowtimesData(items=sorted(unique.values(), key=lambda x: (x.starts_at, x.cinema, x.screen)), checked_at=datetime.now(KST),
                            checked_theaters=checked, complete=not errors, warnings=warnings, booking_url=book)
        return {'ok': True, 'data': data.model_dump(mode='json')}
    except CgvError as error:
        return failure(error.code, error.message)
    except (ValueError, TypeError, KeyError, AttributeError):
        return failure('UPSTREAM_ERROR', f'{name} 지점·작품 목록의 응답 형식이 올바르지 않습니다.')


def get_lotte_showtimes(**kwargs):
    return provider_search('lotte', **kwargs)


def get_megabox_showtimes(**kwargs):
    return provider_search('megabox', **kwargs)
