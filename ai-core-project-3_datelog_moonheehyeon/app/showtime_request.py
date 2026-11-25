"""명확한 날짜·시간·지역·작품 요청만 규칙으로 분석한다. 일반 대화는 LLM에 맡긴다."""
import re
from datetime import date, datetime, timedelta

from .showtimes import KST
from .time_conditions import TIME, TIME_RANGE, parse_time_updates

DATE = re.compile(r'\d{4}-\d{2}-\d{2}|모레|내일|오늘')
TITLE = re.compile(r'<([^<>\n]{1,200})>|[「『“\"\']([^「」『』“”\"\'\n]{1,200})[」』”\"\']|([가-힣A-Za-z0-9][가-힣A-Za-z0-9 :·-]{0,99}?)(?:이라는|라는)\s*영화')


def parse_showtime_request(message, memory, *, today=None):
    today = today or datetime.now(KST).date()
    title_match = TITLE.search(message)
    conditions = memory.get('conditions', {})
    previous = memory.get('active_intent', memory.get('intent')) == 'showtimes'
    if memory.get('active_intent')=='places' and conditions.get('movie_nm') and TIME.search(message) and '영화' in message:
        previous=True
    # 호환: 수정 이전 세션은 브랜드와 작품 조건은 남았지만 intent가 잘못 바뀌어 있을 수 있다.
    legacy_context = 'active_intent' not in memory and conditions.get('brands') and conditions.get('movie_nm') and conditions.get('watch_date')
    previous = previous or bool(legacy_context)
    pending_field = memory.get('pending_field')
    named_brand = bool(re.search(r'CGV|롯데시네마|롯시|메가박스|메박', message, re.I))
    fresh_date = bool(re.search(r'영화\s*데이트|새\s*(?:데이트|약속)', message))
    initial_showtime = fresh_date or (named_brand and bool(DATE.search(message) or TIME.search(message)))
    if not title_match and not previous and not initial_showtime:
        return None
    # 부정/해제/복잡한 조건은 기존 모델 분석을 사용한다.
    if re.search(r'다른\s*영화|영화.*추천|추천.*영화|박스오피스|사용법|러닝타임|말고|제외|빼고|예산|여유', message):
        return None
    updates, question = {}, None
    if fresh_date:
        for field, pattern in [('watch_date', DATE), ('start_time', TIME)]:
            if not pattern.search(message):
                updates[field] = None
        updates.update(deadline=None, deadline_inclusive=None)
        if not title_match:
            updates.update(movie_nm=None, movie_cd=None, movie_query=None)
    brand_patterns = {'cgv': r'CGV', 'lotte': r'롯데시네마|롯시|롯데', 'megabox': r'메가박스|메박'}
    brand_text = message if title_match is None or title_match.group(3) else message[:title_match.start()] + message[title_match.end():]
    selected = [brand for brand, pattern in brand_patterns.items() if re.search(pattern, brand_text, re.I)]
    if re.search(r'모든\s*영화관|전체\s*브랜드|3사\s*모두|세\s*곳\s*다', brand_text):
        updates['brands'] = ['cgv', 'lotte', 'megabox']
    elif selected:
        additive = previous and not re.search(r'(?:CGV|롯데시네마|롯시|롯데|메가박스|메박)만', brand_text, re.I) and re.search(r'(?:CGV|롯데시네마|롯시|롯데|메가박스|메박)도|추가|같이|함께|포함', brand_text, re.I)
        existing = memory.get('conditions', {}).get('brands') or ['cgv', 'lotte', 'megabox']
        updates['brands'] = list(dict.fromkeys([*existing, *selected])) if additive else selected
    if title_match:
        title = next(value.strip() for value in title_match.groups() if value)
        if title_match.group(3):
            title = re.split(r'에서\s*|이후(?:에)?\s*|부터\s*', title)[-1]
            title = re.sub(r'^(?:저는|나는|난|저|나)\s+', '', title).strip()
        if not title:
            return None
        updates['movie_nm'] = title
    elif (pending_field == 'movie_nm' or (previous and not conditions.get('movie_nm'))) and not named_brand and not DATE.search(message) and not TIME.search(message) and re.fullmatch(r'[가-힣A-Za-z0-9 :·!?-]{1,100}', message.strip()) and not re.search(r'안녕|고마워|감사|설명|어떻게|잘못|오전|오후|저녁|아침', message):
        updates['movie_nm'] = message.strip()
    date_match, time_match = DATE.search(message), TIME.search(message)
    if date_match:
        value = date_match.group()
        try:
            updates['watch_date'] = ((today + timedelta(days={'오늘': 0, '내일': 1, '모레': 2}[value])).isoformat()
                                     if value in {'오늘', '내일', '모레'} else date.fromisoformat(value).isoformat())
        except ValueError:
            question = '관람 날짜를 YYYY-MM-DD 형식으로 다시 알려 주세요.'
    time_updates, time_question, pending_field, pending_time = parse_time_updates(message, memory, {**conditions, **updates})
    updates.update(time_updates)
    question = question or time_question
    previous_time = memory.get('pending_time')
    if not question and isinstance(previous_time, dict) and previous_time['field'] not in time_updates:
        pending_time = previous_time
        pending_field = previous_time['field']
        question = f"앞서 말씀하신 {previous_time['hour']}시는 오전인가요, 오후인가요?"
    if '에서' in message:
        prefix = message.split('에서', 1)[0]
        prefix = TIME_RANGE.sub(' ',prefix)
        for match in (title_match, date_match, time_match):
            if match:
                prefix = prefix.replace(match.group(), ' ')
        prefix = re.sub(r'(?:CGV|롯데시네마|롯시|롯데|메가박스|메박)(?:이랑|하고|만|와|과|랑|도)?', ' ', prefix, flags=re.I)
        if len(selected) > 1:
            prefix = re.sub(r'\b(?:및|그리고|또는)\b|[,&]', ' ', prefix)
        prefix = re.sub(r'^(?:저는|나는|난|저|나)\s+', '', prefix.strip())
        prefix = re.sub(r'^(?:에|이후에?|부터|전에?|이전(?:에|으로)?|까지|사이에?)\s+', '', prefix.strip())
        if re.fullmatch(r'[가-힣A-Za-z0-9· -]{1,60}', prefix.strip()):
            updates['region'] = ' '.join(prefix.split())
    if not title_match and not updates and not question:
        return None
    result = {'intent': 'showtimes', 'conditions': updates, 'question': question,
              'reason': '기존 영화·지역·브랜드를 유지하며 실제 회차 조회 조건만 갱신', 'tool_names': ['get_showtimes']}
    if pending_field:
        result.update(pending_field=pending_field, pending_time=pending_time)
    return result
