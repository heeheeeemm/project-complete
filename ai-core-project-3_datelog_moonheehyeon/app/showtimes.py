"""CGV 공식 웹의 읽기 전용 조회. 접근 제한은 우회하지 않는다."""
import re
import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlencode
from typing import Literal

import requests
from pydantic import BaseModel, Field

KST = timezone(timedelta(hours=9))
CGV_BASE = 'https://cgv.co.kr'
BOOK_URL = CGV_BASE + '/cnm/movieBook'
WEB_HEADERS = {
    'Accept': 'application/json',
    'Referer': BOOK_URL + '/cinema',
    # 공식 웹에서 확인한 일반 공개 조회 헤더. 쿠키·인증 토큰·서명은 사용하지 않는다.
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36',
}


class Showtime(BaseModel):
    schedule_id: str
    brand: Literal['cgv', 'lotte', 'megabox'] = 'cgv'
    brand_name: str = 'CGV'
    movie_nm: str
    movie_id: str | None = None
    cgv_movie_id: str | None = None
    cinema: str
    cinema_id: str
    screen: str
    format: str
    business_date: date
    watch_date: date
    start_time: str
    end_time: str
    start_label: str
    end_label: str
    starts_at: datetime
    ends_at: datetime
    remaining_seats: int | None = Field(default=None, ge=0)
    total_seats: int | None = Field(default=None, gt=0)
    availability: str
    checked_at: datetime
    booking_url: str
    source: str = 'CGV 상영시간표'


class ShowtimesData(BaseModel):
    items: list[Showtime]
    checked_at: datetime
    checked_theaters: list[str]
    complete: bool
    warnings: list[str]
    booking_url: str = BOOK_URL
    providers: list[dict] = Field(default_factory=list)
    booking_urls: list[dict] = Field(default_factory=list)
    notice: str = '잔여석은 조회 시점 기준이며 예매 과정에서 바뀔 수 있습니다. 해당 영화관에서 최종 확인해 주세요.'


class CgvError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def failure(code, message):
    return {'ok': False, 'error': {'code': code, 'message': message}}


def normalized(value):
    return re.sub(r'[^\w]', '', unicodedata.normalize('NFKC', value)).casefold().replace('_', '')


def fetch(path, **params):
    try:
        result = requests.get(CGV_BASE + path, params={'coCd': 'A420', **params},
                              headers=WEB_HEADERS, timeout=(3, 8))
        if result.status_code in (401, 403):
            raise CgvError('ACCESS_DENIED', 'CGV가 시간표 조회 접근을 제한했습니다. CGV 공식 예매 화면에서 확인해 주세요.')
        if result.status_code == 429:
            raise CgvError('UPSTREAM_ERROR', 'CGV 조회 요청이 많아 잠시 제한되었습니다. 잠시 후 다시 조회해 주세요.')
        if result.status_code != 200:
            raise CgvError('UPSTREAM_ERROR', 'CGV 시간표 서버가 정상 응답하지 않았습니다. 잠시 후 다시 조회해 주세요.')
        body = result.json()
        if not isinstance(body, dict) or body.get('statusCode') != 0 or 'data' not in body:
            raise ValueError('invalid envelope')
        return body['data']
    except requests.Timeout:
        raise CgvError('TIMEOUT', 'CGV 시간표 응답 시간이 초과되었습니다. 잠시 후 다시 조회해 주세요.') from None
    except requests.RequestException:
        raise CgvError('CONNECTION_ERROR', 'CGV 서버에 연결하지 못했습니다. 네트워크 상태를 확인해 주세요.') from None
    except (ValueError, TypeError, KeyError):
        raise CgvError('UPSTREAM_ERROR', 'CGV 응답 형식이 변경되었거나 올바르지 않아 시간표를 확인하지 못했습니다.') from None


def select_theaters(data, region, *, brand='CGV', aliases=None):
    if not isinstance(data, dict) or not isinstance(data.get('siteInfo'), list) or not isinstance(data.get('regionInfo'), list):
        raise CgvError('UPSTREAM_ERROR', f'{brand} 지점 목록의 응답 형식이 올바르지 않습니다.')
    query = normalized(region).replace(normalized(brand), '')
    # 광역 지역은 CGV의 지역 그룹과 대조하되 나머지 지점명도 함께 일치시킨다.
    group = None
    for item in data['regionInfo']:
        for name in str(item.get('comCdvalNm', '')).split('/'):
            if name and query.startswith(normalized(name)):
                group = str(item.get('comCdval'))
                query = query[len(normalized(name)):]
                for suffix in ('광역시', '특별시', '특별자치시'):
                    if query.startswith(suffix):
                        query = query[len(suffix):]
                break
        if group is not None:
            break
    if not query:
        raise CgvError('BAD_ARGUMENT', '구체적인 동네나 영화관 지점명을 알려 주세요. 예: 부산 서면, 서울 강남.')
    query = (aliases or {}).get(query, query)
    matches = []
    for item in data['siteInfo']:
        if not isinstance(item, dict) or not item.get('siteNo') or not item.get('siteNm'):
            raise CgvError('UPSTREAM_ERROR', f'{brand} 지점 정보의 응답 형식이 올바르지 않습니다.')
        if group is not None and str(item.get('regnGrpCd')) != group:
            continue
        if query in normalized(item['siteNm']).replace('cgv', ''):
            matches.append(item)
    if not matches:
        raise CgvError('NOT_FOUND', f'해당 지역 이름에 맞는 {brand} 지점을 찾지 못했습니다.')
    if len(matches) > 8:
        raise CgvError('BAD_ARGUMENT', '검색 범위가 넓습니다. 구체적인 동네나 CGV 지점명을 알려 주세요.')
    return list({str(item['siteNo']): item for item in matches}.values())


def service_datetime(value, business_date):
    if not isinstance(value, str) or not re.fullmatch(r'(?:[0-3]\d|4[0-7])[0-5]\d', value):
        raise ValueError('invalid service clock')
    return datetime.combine(business_date, time(), KST) + timedelta(hours=int(value[:2]), minutes=int(value[2:]))


def seat_count(value):
    if value is None or value == '':
        return None
    if isinstance(value, bool) or not re.fullmatch(r'\d+', str(value)):
        raise ValueError('invalid seats')
    return int(value)


def label(value, business_date):
    return ('익일 ' if value.date() > business_date else '') + value.strftime('%H:%M')


def make_showtime(*, brand, brand_name, schedule_id, movie_nm, movie_id, cinema_id, cinema_name,
                  screen, format_name, day, start_raw, end_raw, remaining, total, bookable,
                  earliest, latest, buffer_minutes, checked_at, booking_url, sale_end_raw=None, deadline_inclusive=True):
    """각 브랜드가 검증한 필드를 공통 회차로 만든다. 좌석 수를 역산하지 않는다."""
    start = service_datetime(start_raw.replace(':', ''), day)
    end = service_datetime(end_raw.replace(':', ''), day)
    if end < start and end_raw.replace(':', '')[:2] < '24':
        end += timedelta(days=1)
    if end <= start or end - start > timedelta(hours=12):
        raise ValueError('invalid interval')
    free, total = seat_count(remaining), seat_count(total)
    if total == 0 or (free is not None and total is not None and free > total):
        raise ValueError('invalid seat range')
    finish = end + timedelta(minutes=buffer_minutes)
    if start < earliest or start <= checked_at or (latest is not None and (finish > latest if deadline_inclusive else finish >= latest)):
        return None
    status = 'unknown' if free is None else 'sold_out' if free == 0 else 'available'
    sale_end = service_datetime(sale_end_raw.replace(':', ''), day) if sale_end_raw else start
    if bookable is False or checked_at >= sale_end:
        status = 'unavailable'
    cinema = cinema_name if cinema_name.upper().startswith(brand_name.upper()) else brand_name + ' ' + cinema_name
    return Showtime(
        schedule_id=str(schedule_id), brand=brand, brand_name=brand_name, movie_nm=movie_nm,
        movie_id=str(movie_id), cgv_movie_id=str(movie_id) if brand == 'cgv' else None,
        cinema=cinema, cinema_id=str(cinema_id), screen=screen or '상영관 미확인', format=format_name or '상영 방식 미확인',
        business_date=day, watch_date=start.date(), start_time=start.strftime('%H:%M'), end_time=end.strftime('%H:%M'),
        start_label=label(start, day), end_label=label(end, day), starts_at=start, ends_at=end,
        remaining_seats=free, total_seats=total, availability=status, checked_at=checked_at,
        booking_url=booking_url, source=brand_name + ' 상영시간표',
    )


def normalize_rows(rows, theater, movie_nm, day, earliest, latest, buffer_minutes, checked_at, deadline_inclusive=True):
    if not isinstance(rows, list):
        raise ValueError('invalid schedule list')
    items = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('invalid schedule')
        # CGV 영화명 필드를 우선 사용한다. 상품명은 상영 방식 접미사만 제거한다.
        title = row.get('movNm') or re.sub(r'\((?:2D|3D|IMAX.*|4DX.*|SCREENX.*)\)$', '', str(row.get('expoProdNm', ''))).strip()
        if normalized(str(title)) != normalized(movie_nm):
            continue
        if row.get('scnYmd') != day.strftime('%Y%m%d') or str(row.get('siteNo')) != str(theater['siteNo']):
            raise ValueError('mismatched schedule')
        if not row.get('scnsNo') or not row.get('scnSseq') or not row.get('movNo'):
            raise ValueError('missing identity')
        item = make_showtime(brand='cgv', brand_name='CGV',
            schedule_id=':'.join(str(row[k]) for k in ('siteNo', 'scnYmd', 'scnsNo', 'scnSseq')),
            movie_nm=title, movie_id=row['movNo'], cinema_name=str(theater['siteNm']), cinema_id=theater['siteNo'],
            screen=row.get('scnsNm') or row.get('expoScnsNm'), format_name=row.get('movkndDsplNm'), day=day,
            start_raw=row['scnsrtTm'], end_raw=row['scnendTm'], remaining=row.get('frSeatCnt'), total=row.get('stcnt'),
            bookable=row.get('cntlYn') != 'Y', earliest=earliest, latest=latest, buffer_minutes=buffer_minutes,
            checked_at=checked_at, sale_end_raw=row.get('salEndTm'),
            deadline_inclusive=deadline_inclusive,
            booking_url=BOOK_URL + '?' + urlencode({'siteNo': theater['siteNo'], 'scnYmd': day.strftime('%Y%m%d')}),
        )
        if item is not None:
            items.append(item)
    return items


def get_showtimes(region, movie_nm, watch_date, start_time='00:00', deadline=None, buffer_minutes=0, deadline_inclusive=True):
    try:
        if not isinstance(region, str) or not region.strip() or len(region) > 100 or not isinstance(movie_nm, str) or not normalized(movie_nm) or len(movie_nm) > 200:
            raise ValueError('invalid query')
        day = date.fromisoformat(watch_date)
        if day.isoformat() != watch_date:
            raise ValueError('invalid date')
        for value in (start_time, deadline):
            if value is not None and (not isinstance(value, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value)):
                raise ValueError('invalid clock')
        if not isinstance(buffer_minutes, int) or isinstance(buffer_minutes, bool) or not 0 <= buffer_minutes <= 240:
            raise ValueError('invalid buffer')
        if not isinstance(deadline_inclusive, bool):
            raise ValueError('invalid boundary')
        earliest = datetime.combine(day, time.fromisoformat(start_time), KST)
        latest = datetime.combine(day, time.fromisoformat(deadline), KST) if deadline else None
        if latest and latest <= earliest:
            raise ValueError('invalid deadline')
    except (ValueError, TypeError):
        return failure('BAD_ARGUMENT', '지역·영화명·날짜(YYYY-MM-DD)·시각(HH:MM)을 확인해 주세요.')
    try:
        theaters = select_theaters(fetch('/api/v1/content/site/searchAllRegionAndSite'), region)
        items, warnings, errors, checked = [], [], [], []
        for theater in theaters:
            try:
                rows = fetch('/api/v1/booking/searchMovScnInfo', siteNo=str(theater['siteNo']), scnYmd=day.strftime('%Y%m%d'), rtctlScopCd='08')
                # 각 응답의 수신 시각을 기록한다. 좌석 데이터는 캐시하지 않는다.
                received = datetime.now(KST)
                items.extend(normalize_rows(rows, theater, movie_nm.strip(), day, earliest, latest, buffer_minutes, received, deadline_inclusive))
                checked.append('CGV ' + theater['siteNm'].removeprefix('CGV '))
            except (ValueError, TypeError, KeyError):
                error = CgvError('UPSTREAM_ERROR', 'CGV 시간표 응답 형식이 올바르지 않아 회차를 확인하지 못했습니다.')
                errors.append(error)
                warnings.append(f"CGV {theater['siteNm']}: {error.message}")
            except CgvError as error:
                errors.append(error)
                warnings.append(f"CGV {theater['siteNm']}: {error.message}")
        if not checked:
            raise errors[0]
        unique = {item.schedule_id: item for item in items}
        data = ShowtimesData(items=sorted(unique.values(), key=lambda x: (x.starts_at, x.cinema, x.screen)),
                             checked_at=datetime.now(KST), checked_theaters=checked, complete=not errors, warnings=warnings)
        return {'ok': True, 'data': data.model_dump(mode='json')}
    except CgvError as error:
        return failure(error.code, error.message)
