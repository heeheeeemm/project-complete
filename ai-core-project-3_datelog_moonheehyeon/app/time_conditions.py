"""관람 시작/종료 시각 수정과 오전·오후 확인 상태. 외부 일정 시각은 덮어쓰지 않는다."""
import re

TIME = re.compile(r'(?P<period>오전|오후|저녁|아침|밤)?\s*(?P<hour>\d{1,2})\s*(?::(?P<colon>\d{2})|시(?:\s*(?P<minute>\d{1,2})\s*분|\s*(?P<half>반))?)\s*(?P<after>이후(?:에)?|부터)?')
TIME_RANGE = re.compile(r'(?<!\d)(?P<p1>오전|오후|저녁|아침|밤)?\s*(?P<h1>\d{1,2})(?::(?P<m1>\d{2})|\s*시(?:\s*(?P<min1>\d{1,2})분|\s*(?P<half1>반))?)?\s*(?:[-~〜～–—]|부터)\s*(?P<p2>오전|오후|저녁|아침|밤)?\s*(?P<h2>\d{1,2})(?::(?P<m2>\d{2})|\s*시(?:\s*(?P<min2>\d{1,2})분|\s*(?P<half2>반))?)?\s*(?P<suffix>사이|까지)?(?!\d)')


def clock_minutes(value):
    return int(value[:2]) * 60 + int(value[3:])


def resolve_clock(hour, minute, period, field, conditions, explicit_24=False):
    if minute > 59 or hour > 23 or (period and not 1 <= hour <= 12):
        return None
    if period:
        hour = hour % 12 + (12 if period in {'오후', '저녁', '밤'} else 0)
        if period == '밤' and hour == 12:
            hour = 0
        return f'{hour:02}:{minute:02}'
    if hour == 0 or hour > 12 or explicit_24:
        return f'{hour:02}:{minute:02}'
    candidates = [hour % 12 * 60 + minute, (hour % 12 + 12) * 60 + minute]
    if field == 'deadline' and conditions.get('start_time'):
        candidates = [value for value in candidates if value > clock_minutes(conditions['start_time'])]
    elif field == 'start_time' and conditions.get('deadline'):
        candidates = [value for value in candidates if value < clock_minutes(conditions['deadline'])]
    if len(candidates) == 1:
        return f'{candidates[0] // 60:02}:{candidates[0] % 60:02}'
    previous = conditions.get(field)
    if previous:
        same_period = [value for value in candidates if (value >= 720) == (clock_minutes(previous) >= 720)]
        if len(same_period) == 1:
            return f'{same_period[0] // 60:02}:{same_period[0] % 60:02}'
    return None


def parse_time_updates(message, memory, conditions):
    """이번에 바꾼 시각만 반환하고, 애매한 값은 확인할 항목과 함께 보관한다."""
    updates, pending_field, pending_time, question = {}, None, None, None
    if re.search(r'(?:종료\s*(?:시간|제한)?|마감|끝나는\s*시간).*(?:없애|없어|해제|취소|빼줘)', message):
        return {'deadline': None, 'deadline_inclusive': None}, None, None, None
    period_only = re.fullmatch(r'\s*(?:아니\s*)?(오전|오후|저녁|아침|밤)(?:(?:이야|야|요|입니다|으로|로)|라고\s*(?:했잖아|했잖아요|말했잖아|했어|했는데))?[.!?]*\s*', message)
    pending = memory.get('pending_time')
    if period_only and isinstance(pending, dict):
        field = pending['field']
        value = resolve_clock(pending['hour'], pending['minute'], period_only[1], field, conditions)
        if value:
            updates[field] = value
            if field == 'deadline':
                updates['deadline_inclusive'] = pending.get('inclusive', True)
            if pending.get('end_hour') is not None:
                updates['deadline']=resolve_clock(pending['end_hour'],pending.get('end_minute',0),period_only[1],'deadline',{**conditions,**updates})
                updates['deadline_inclusive']=pending.get('inclusive',True)
        return updates, None, None, None
    if period_only:
        if conditions.get('start_time'):
            for field in ('start_time','deadline'):
                if conditions.get(field):
                    old=conditions[field]
                    updates[field]=resolve_clock(int(old[:2])%12 or 12,int(old[3:]),period_only[1],field,conditions)
            return updates,None,None,None
        return {},f'{period_only[1]} 몇 시 이후에 관람할 수 있나요?', 'start_time',None
    ranges=[m for m in TIME_RANGE.finditer(message) if m['p1'] or m['p2'] or '시' in m[0] or ':' in m[0] or m['suffix']]
    for match in ranges:
        hour1,hour2=int(match['h1']),int(match['h2'])
        min1=int(match['m1'] or match['min1'] or (30 if match['half1'] else 0))
        min2=int(match['m2'] or match['min2'] or (30 if match['half2'] else 0))
        period1,period2=match['p1'],match['p2'] or match['p1']
        inclusive=not bool(re.match(r'(?:이전|전)',message[match.end():].lstrip()))
        start=resolve_clock(hour1,min1,period1,'start_time',conditions,explicit_24=hour1>12 or bool(match['m1'] and match['h1'].startswith('0')))
        end=resolve_clock(hour2,min2,period2,'deadline',{**conditions,**({'start_time':start} if start else {})},explicit_24=hour2>12 or bool(match['m2'] and match['h2'].startswith('0')))
        if start and end:
            updates.update(start_time=start,deadline=end,deadline_inclusive=inclusive)
        else:
            pending_field='start_time'
            if hour1>23 or hour2>23 or min1>59 or min2>59 or (period1 and not 1<=hour1<=12) or (period2 and not 1<=hour2<=12):
                question='올바른 시간 범위를 알려 주세요. 예: 오후 2시~6시.'
            else:
                pending_time={'field':'start_time','hour':hour1,'minute':min1,'end_hour':hour2,'end_minute':min2,'inclusive':inclusive}
                question=f'{hour1}시부터 {hour2}시는 오전인가요, 오후인가요?'
    matches = list(TIME.finditer(message))
    for index, match in enumerate(matches):
        if any(start.start()<=match.start()<start.end() for start in ranges):
            continue
        tail = message[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(message)]
        prefix = message[matches[index - 1].end() if index else 0:match.start()]
        before = re.match(r'(?:이전|전)(?:에|으로|로)?', tail.lstrip())
        until = re.match(r'까지', tail.lstrip())
        finish = bool(re.search(r'끝|종료|마치|마쳐|마칠', tail))
        starts = bool(re.search(r'시작', tail) or re.search(r'시작(?:\s*(?:시간|시각))?(?:은|는|을|를)?\s*$', prefix))
        if finish or ((before or until) and not starts):
            field = 'deadline'
        elif match['after'] or starts:
            field = 'start_time'
        elif re.search(r'밥|식사|약속|출근|퇴근|가야|가려고', tail):
            continue
        else:
            field = memory.get('last_time_field') or 'start_time'
        hour = int(match['hour'])
        minute = int(match['colon'] or match['minute'] or (30 if match['half'] else 0))
        value = resolve_clock(hour, minute, match['period'], field, {**conditions, **updates},
                              explicit_24=bool(match['colon'] and match['hour'].startswith('0')))
        if value is None:
            pending_field = field
            if hour > 23 or minute > 59 or (match['period'] and not 1 <= hour <= 12):
                question = '올바른 시각을 알려 주세요. 예: 오후 5시 30분.'
                continue
            pending_time = {'field': field, 'hour': hour, 'minute': minute, 'inclusive': not bool(before)}
            subject = '종료 제한' if field == 'deadline' else '관람 시작'
            question = f'{subject} 시각 {hour}시{(" " + str(minute) + "분") if minute else ""}는 오전인가요, 오후인가요?'
        else:
            updates[field] = value
            if field == 'deadline':
                updates['deadline_inclusive'] = not bool(before)
    return updates, question, pending_field, pending_time
