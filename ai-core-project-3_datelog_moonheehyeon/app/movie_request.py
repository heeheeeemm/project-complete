"""불완전한 제목·인물 설명은 작품 확인 단계를 거치며 임의로 확정하지 않는다."""
import re
from .showtime_request import DATE, TITLE, parse_showtime_request
from .time_conditions import TIME


def parse_movie_request(message,memory):
    text=message.strip()
    pending=memory.get('pending_movies') or []
    recent=bool(re.search(r'최근|최신|새로|이번에|요즘',text) and re.search(r'개봉|나온|나왔|영화|작품',text))
    if recent and pending:
        return {'intent':'showtimes','conditions':{},'movie_preference':'recent','pending_field':'movie_confirmation','reason':'기존 후보의 실제 개봉일로 최근 작품 재확인','tool_names':[]}
    if recent and (memory.get('conditions',{}).get('movie_query') or memory.get('conditions',{}).get('movie_nm')):
        query=memory['conditions'].get('movie_query') or memory['conditions']['movie_nm']
        return {'intent':'showtimes','conditions':{'movie_query':query,'movie_nm':None,'movie_cd':None},'movie_preference':'recent','reason':'기존 영화 후보를 개봉일과 함께 다시 검색','tool_names':['search_movies']}
    selected=None
    if pending:
        number=re.fullmatch(r'(\d{1,2})\s*(?:번|번째)?(?:\s*(?:영화|작품))?(?:이요|요|로|으로)?[.!]?',text)
        if number and 1 <= int(number[1]) <= len(pending):
            selected=pending[int(number[1])-1]
        else:
            selected=next((m for m in pending if text.strip('<>')==m['movie_nm']),None)
        if re.fullmatch(r'(?:응|네|예|맞아|맞아요|그거|그 영화|그거야|응 맞아|네 맞아요)[.!]?',text):
            if len(pending)==1:
                selected=pending[0]
            else:
                return {'intent':'showtimes','conditions':{},'question':'어떤 작품이 맞나요? 아래 영화에서 선택해 주세요.','pending_field':'movie_confirmation','reason':'복수 후보를 임의로 고르지 않음','tool_names':[]}
        if selected:
            return {'intent':'showtimes','conditions':{'movie_nm':selected['movie_nm'],'movie_cd':selected['movie_cd'],'movie_query':None},'reason':'조회된 실제 작품을 사용자 확인으로 확정','tool_names':['get_showtimes']}
        if re.fullmatch(r'(?:아니|아니야|아니요|다른 영화|둘 다 아니야)[.!]?',text):
            return {'intent':'showtimes','conditions':{'movie_query':None,'movie_nm':None,'movie_cd':None},'question':'찾는 영화의 제목 일부나 다른 출연자를 알려 주실래요?','pending_field':'movie_nm','reason':'후보 거절','tool_names':[]}
    if TITLE.search(text):
        return None
    matches=list(re.finditer(r'([가-힣A-Za-z][가-힣A-Za-z0-9·-]{1,39}?)(?:이|가)?\s*(?:(?:나오는|나온다는|나온|출연하는|출연한|출연)\s*)?영화',text))
    ignored={'어떤','다른','좋은','추천','액션','공포','로맨스','짧은','긴','데이트','그','이','저','두','만한','가능한',
             '강남','홍대','서면','부산','서울','대구','대전','광주','인천','수원','잠실'}
    matches=[m for m in matches if m[1] not in ignored and not m[1].endswith(('에서','이후','이전'))]
    if not matches:
        return None
    query=matches[-1][1]
    # 이미 확인된 제목을 반복한 경우에는 기존 회차 조건 파서를 사용한다.
    if query==memory.get('conditions',{}).get('movie_nm') and not pending:
        return None
    parsed=parse_showtime_request(text,{'active_intent':'showtimes','conditions':memory.get('conditions',{})})
    updates=dict((parsed or {}).get('conditions',{}))
    updates.update(movie_query=query,movie_nm=None,movie_cd=None)
    if re.search(r'영화\s*데이트|새\s*(?:데이트|약속)',text):
        for field,pattern in [('watch_date',DATE),('start_time',TIME)]:
            if not pattern.search(text):
                updates[field]=None
        updates.update(deadline=None,deadline_inclusive=None)
    return {'intent':'showtimes','conditions':updates,'reason':'인물명 또는 불완전한 제목으로 영화 후보를 먼저 검색','tool_names':['search_movies']}
