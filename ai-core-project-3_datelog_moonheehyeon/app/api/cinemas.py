"""LLM 없이 카카오 영화관 검색과 공개 지도 SDK 설정을 제공한다."""
import os
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from tools_start import TOOLS, CinemaData, ToolFailure, ToolSuccess
from ..places import PlaceData

router = APIRouter(tags=['cinemas'])


class MapConfig(BaseModel):
    javascript_key: str | None


@router.get('/api/maps/config', response_model=MapConfig)
def map_config():
    # JavaScript 키는 도메인 제한을 전제로 브라우저에서 사용하는 공개 키다.
    key = os.getenv('KAKAO_JAVASCRIPT_KEY', '').strip()
    private_keys = {os.getenv(name, '').strip() for name in ('KAKAO_REST_API_KEY', 'KOBIS_API_KEY', 'OPENAI_API_KEY')}
    return {'javascript_key': key if key and key not in private_keys else None}


@router.get('/api/cinemas', response_model=ToolSuccess[CinemaData] | ToolFailure)
def cinemas(region: str = Query(min_length=1, max_length=100)):
    return TOOLS['search_cinemas'].run(region=region)


@router.get('/api/places',response_model=ToolSuccess[PlaceData] | ToolFailure)
def places(region:str=Query(min_length=1,max_length=100),kind:Literal['restaurant','cafe','place']=Query(),
           cuisine:str|None=Query(default=None,max_length=40),anchor_name:str|None=Query(default=None,max_length=200),
           lat:float|None=Query(default=None,ge=-90,le=90),lng:float|None=Query(default=None,ge=-180,le=180)):
    return TOOLS['search_places'].run(region=region,kind=kind,cuisine=cuisine,anchor_name=anchor_name,lat=lat,lng=lng)
