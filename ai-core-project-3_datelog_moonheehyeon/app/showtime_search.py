"""3사 조회 집계. 브랜드별 실패와 성공을 분리하고 회차를 시간순으로 합친다."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from .cinema_providers import (LOTTE_BOOK, MEGA_BOOK, get_lotte_showtimes,
                               get_megabox_showtimes, query_context)
from .showtimes import BOOK_URL, KST, ShowtimesData, failure, get_showtimes

PROVIDERS = {
    'cgv': ('CGV', get_showtimes, BOOK_URL),
    'lotte': ('롯데시네마', get_lotte_showtimes, LOTTE_BOOK),
    'megabox': ('메가박스', get_megabox_showtimes, MEGA_BOOK),
}


def search_showtimes(region, movie_nm, watch_date, start_time='00:00', deadline=None, buffer_minutes=0, brands=None, deadline_inclusive=True):
    selected = brands if brands is not None else ['cgv', 'lotte', 'megabox']
    if not isinstance(selected, list) or not selected or any(not isinstance(x, str) or x not in PROVIDERS for x in selected):
        return failure('BAD_ARGUMENT', '조회 브랜드는 cgv, lotte, megabox 중에서 선택해 주세요.')
    selected = list(dict.fromkeys(selected))
    arguments = dict(region=region, movie_nm=movie_nm, watch_date=watch_date, start_time=start_time, deadline=deadline, buffer_minutes=buffer_minutes, deadline_inclusive=deadline_inclusive)
    try:
        query_context(**arguments)
    except (ValueError, TypeError):
        return failure('BAD_ARGUMENT', '지역·영화명·날짜(YYYY-MM-DD)·시각(HH:MM)을 확인해 주세요.')
    items, checked, warnings, statuses, links, errors = [], [], [], [], [], []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {brand: pool.submit(PROVIDERS[brand][1], **arguments) for brand in selected}
        for brand, future in futures.items():
            name, _, url = PROVIDERS[brand]
            links.append({'brand': brand, 'label': name, 'url': url})
            try:
                result = future.result()
                if not isinstance(result, dict) or not isinstance(result.get('ok'), bool):
                    raise ValueError('invalid result')
                if result['ok']:
                    data = ShowtimesData.model_validate(result['data'])
                    for item in data.items:
                        # 식별자는 브랜드 범위에 속한다. 업체 간 동일 코드는 다른 회차다.
                        item = item.model_copy(update={'schedule_id': brand + ':' + item.schedule_id, 'brand': brand, 'brand_name': name})
                        items.append(item)
                    checked.extend(data.checked_theaters)
                    warnings.extend(data.warnings)
                    statuses.append({'brand': brand, 'label': name, 'status': 'ok' if data.complete else 'partial', 'count': len(data.items), 'booking_url': url})
                else:
                    error = result['error']
                    no_theater = error['code'] == 'NOT_FOUND'
                    statuses.append({'brand': brand, 'label': name, 'status': 'no_theater' if no_theater else 'error', 'count': 0,
                                     'error_code': error['code'], 'message': error['message'], 'booking_url': url})
                    if not no_theater:
                        errors.append(error)
                        warnings.append(f"{name}: {error['message']}")
            except Exception:
                message = name + ' 조회 응답을 처리하지 못했습니다.'
                errors.append({'code': 'UPSTREAM_ERROR', 'message': message})
                warnings.append(message)
                statuses.append({'brand': brand, 'label': name, 'status': 'error', 'count': 0, 'error_code': 'UPSTREAM_ERROR', 'message': message, 'booking_url': url})
    if not any(x['status'] in {'ok', 'partial'} for x in statuses):
        code = errors[0]['code'] if errors else 'NOT_FOUND'
        return failure(code, ' / '.join(x['label'] + ': ' + x.get('message', '조회 실패') for x in statuses))
    unique = {item.schedule_id: item for item in items}
    data = ShowtimesData(items=sorted(unique.values(), key=lambda x: (x.starts_at, x.cinema, x.screen)),
                        checked_at=datetime.now(KST), checked_theaters=list(dict.fromkeys(checked)),
                        complete=all(x['status'] in {'ok', 'no_theater'} for x in statuses), warnings=warnings,
                        providers=statuses, booking_urls=links, booking_url=links[0]['url'])
    return {'ok': True, 'data': data.model_dump(mode='json')}
