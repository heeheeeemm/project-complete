"""식당·카페 후속 요청은 영화 조건을 지우지 않고 별도로 분석한다."""
import re

from .time_conditions import TIME


def parse_place_request(message,memory):
    # '밥 약속 때문에 영화가 5시 전에 끝나야 해'는 영화 종료 조건이다.
    if TIME.search(message) and re.search(r'끝|종료|마치',message) and not re.search(r'추천|식당\s*찾|카페\s*찾',message):
        return None
    cafe=bool(re.search(r'카페|커피|디저트',message))
    meal=bool(re.search(r'밥집|식당|맛집|양식|한식|중식|일식|파스타|(?:밥|음식).*(?:추천|찾|먹고\s*싶)',message))
    if not cafe and not meal:
        if memory.get('active_intent')=='places' and memory.get('pending_field')=='region' and re.fullmatch(r'[가-힣A-Za-z0-9 ]{1,50}',message.strip()):
            return {'intent':'places','conditions':{'place_region':message.strip()},'reason':'장소 검색 지역 확인','tool_names':['search_places']}
        return None
    updates={'place_kind':'cafe' if cafe else 'restaurant','place_anchor':None}
    if not cafe:
        cuisine=re.search(r'양식|한식|중식|일식|파스타',message)
        if cuisine:
            updates['cuisine']=cuisine.group()
    region=re.search(r'([가-힣A-Za-z0-9]+(?:\s+[가-힣A-Za-z0-9]+){0,2})\s*(?:근처|주변|에서)',message)
    if not region:
        # '서면 카페', '홍대 양식 밥집'처럼 조사 없이 입력한 지역도 보존한다.
        region=re.match(r'^\s*(?:나는\s+|나\s+|저는\s+|그럼\s+)?([가-힣A-Za-z0-9]+(?:\s+[가-힣A-Za-z0-9]+){0,2}?)\s+(?:(?:양식|한식|중식|일식|파스타)\s+)?(?:카페|커피|디저트|밥집|식당|맛집)(?:\s|$)',message)
    if region:
        name=re.sub(r'^(?:나는|나|저는|그럼)\s+','',region[1].strip())
        name=re.sub(r'\s*(?:근처|주변)$','',name).strip()
        if name and name not in {'그','거기','그곳','영화관','극장','식당','밥집','카페','근처','주변','나','나는','저는','다른','조용한','예쁜','괜찮은','좋은','새로운','분위기 좋은','맛있는','저렴한','유명한'}:
            updates['place_region']=name
    if re.search(r'영화관\s*(?:근처|주변)|극장\s*(?:근처|주변)',message):
        updates['place_region']=None
        updates['place_anchor']='cinema'
    elif re.search(r'(?:식당|밥집)\s*(?:근처|주변)',message):
        updates['place_region']=None
        updates['place_anchor']='restaurant'
    elif re.search(r'카페\s*(?:근처|주변)',message):
        updates['place_region']=None
        updates['place_anchor']='cafe'
    return {'intent':'places','conditions':updates,'reason':'기억한 영화관·선택한 코스 주변의 실제 장소 검색','tool_names':['search_places']}
