"""카카오 장소 검색으로 실제 식당/카페와 지도 좌표를 조회한다."""
import math
import os
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .showtimes import KST, normalized


class Place(BaseModel):
    id: str
    name: str
    category: str
    address: str
    phone: str | None = None
    url: str
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    distance_m: int | None = Field(default=None, ge=0)


class PlaceData(BaseModel):
    items: list[Place]
    kind: Literal['restaurant', 'cafe','place']
    region: str
    cuisine: str | None = None
    anchor: dict | None = None
    checked_at: datetime
    source: str = '카카오 로컬'
    notice: str = '메뉴·영업시간·가격은 카카오맵 장소 상세에서 확인해 주세요.'


def search_places(region, kind, cuisine=None, anchor_name=None, lat=None, lng=None):
    from tools_start import _get, ok, fail
    if kind not in {'restaurant','cafe','place'} or not isinstance(region,str) or not region.strip() or len(region)>100:
        return fail('BAD_ARGUMENT','검색할 지역과 식당/카페 종류를 확인해 주세요.')
    if cuisine is not None and (not isinstance(cuisine,str) or len(cuisine)>40):
        return fail('BAD_ARGUMENT','음식 종류를 확인해 주세요.')
    if anchor_name is not None and (not isinstance(anchor_name,str) or not anchor_name.strip() or len(anchor_name)>200):
        return fail('BAD_ARGUMENT','기준 장소 이름을 확인해 주세요.')
    if (lat is None) != (lng is None) or (lat is not None and (not isinstance(lat,(float,int)) or not isinstance(lng,(float,int)) or not math.isfinite(lat) or not math.isfinite(lng) or not -90<=lat<=90 or not -180<=lng<=180)):
        return fail('BAD_ARGUMENT','기준 장소 좌표를 확인해 주세요.')
    key=os.getenv('KAKAO_REST_API_KEY')
    if not key:
        return fail('INVALID_KEY','.env에 KAKAO_REST_API_KEY를 설정해 주세요.')
    headers={'Authorization':f'KakaoAK {key}'}
    base='https://dapi.kakao.com/v2/local/search/'
    anchor=None
    unresolved=False
    try:
        if anchor_name and lat is None:
            found=_get(base+'keyword.json',params={'query':anchor_name,'size':5},headers=headers)
            if not found['ok']:
                return found
            # 다른 지점의 좌표를 첫 번째 결과라는 이유로 사용하지 않는다.
            exact=[x for x in found['data']['documents'] if normalized(x['place_name'])==normalized(anchor_name)]
            if exact:
                lat,lng=float(exact[0]['y']),float(exact[0]['x'])
            else:
                unresolved=True
        if lat is not None:
            anchor={'name':anchor_name or '선택한 장소','lat':lat,'lng':lng,'radius_m':1000}
        cuisine=cuisine.strip() if cuisine and kind=='restaurant' else None
        category='CE7' if kind=='cafe' else 'FD6' if kind=='restaurant' else None
        params={'size':15}
        if category:
            params['category_group_code']=category
        if anchor:
            params.update(x=lng,y=lat,radius=1000,sort='distance')
            endpoint='keyword.json' if cuisine or kind=='place' else 'category.json'
            if cuisine or kind=='place':
                params['query']=cuisine or region.strip()
        else:
            endpoint='keyword.json'
            params['query']=region.strip() if kind=='place' else region.strip()+' '+(cuisine or ('카페' if kind=='cafe' else '음식점'))
        result=_get(base+endpoint,params=params,headers=headers)
        if not result['ok']:
            return result
        documents=result['data']['documents']
        if not isinstance(documents,list):
            raise ValueError('invalid places')
        items=[]
        for raw in documents:
            if category and raw.get('category_group_code')!=category:
                continue
            actual_category=raw['category_name']
            if cuisine in {'양식','한식','일식','중식'} and cuisine not in actual_category:
                continue
            distance=raw.get('distance')
            items.append(Place(id=str(raw['id']),name=raw['place_name'],category=actual_category,
                address=raw.get('road_address_name') or raw.get('address_name') or '주소 미확인',phone=raw.get('phone') or None,
                url=raw['place_url'],lat=float(raw['y']),lng=float(raw['x']),distance_m=int(distance) if distance not in (None,'') and anchor else None))
        data=PlaceData(items=items[:8],kind=kind,region=region.strip(),cuisine=cuisine,anchor=anchor,checked_at=datetime.now(KST))
        if unresolved:
            data.notice='기준 장소의 정확한 좌표를 확인하지 못해 기억한 지역으로 검색했습니다. '+data.notice
        return ok(data.model_dump(mode='json'))
    except (KeyError,ValueError,TypeError,AttributeError):
        return fail('UPSTREAM_ERROR','카카오 장소 응답 형식이 올바르지 않아 추천 장소를 확인하지 못했습니다.')
