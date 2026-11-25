"""종류와 순서를 강제하지 않는 데이트 일정의 저장·조회 API."""
import json
from datetime import date, datetime
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import store
from .schemas import PlanIn


class Stop(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True,extra='forbid')
    id: str = Field(default_factory=lambda:uuid4().hex,max_length=100)
    kind: Literal['movie','restaurant','cafe','place']
    name: str = Field(min_length=1,max_length=200)
    venue: str | None = Field(default=None,max_length=200)
    address: str | None = Field(default=None,max_length=300)
    start_time: str | None = None
    end_time: str | None = None
    source_date: date | None = None
    lat: float | None = Field(default=None,ge=-90,le=90)
    lng: float | None = Field(default=None,ge=-180,le=180)
    url: str | None = Field(default=None,max_length=1000)
    _times=field_validator('start_time','end_time')(PlanIn.validate_time.__func__)


class ItineraryIn(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True,extra='forbid')
    title: str = Field(default='우리의 데이트',min_length=1,max_length=100)
    watch_date: date
    stops: list[Stop] = Field(min_length=1,max_length=50)

    @model_validator(mode='after')
    def unique_stops(self):
        if len({stop.id for stop in self.stops})!=len(self.stops):
            raise ValueError('일정 항목 식별자는 중복될 수 없습니다.')
        return self


class ItineraryOut(ItineraryIn):
    # 기존 버전의 무날짜 저장본은 지우거나 날짜를 지어내지 않고 초안으로 읽는다.
    watch_date: date | None = None
    itinerary_id: int
    created_at: datetime
    overlap_itinerary_ids: list[int] = Field(default_factory=list)
    overlap_plan_ids: list[int] = Field(default_factory=list)
    overlapping_stop_ids: list[list[str]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def decode(row):
    return {**json.loads(row['payload']),'itinerary_id':row['itinerary_id'],'created_at':row['created_at']}


def intervals(payload,legacy=False):
    day=payload.get('watch_date')
    if not day:
        return []
    offset=date.fromisoformat(day).toordinal()*1440
    result=[]
    stops=[payload] if legacy else payload.get('stops',[])
    for stop in stops:
        start,end=stop.get('start_time'),stop.get('end_time')
        if not start or not end or start==end:
            continue
        begin=int(start[:2])*60+int(start[3:])
        finish=int(end[:2])*60+int(end[3:])
        if finish<begin:
            finish+=1440
        result.append((offset+begin,offset+finish,stop.get('id','legacy'),stop.get('name') or stop.get('movie_nm','')))
    return result


def overlaps(a,b):
    return a[0]<b[1] and b[0]<a[1]


def with_warnings(db,item):
    own=intervals(item)
    conflicts=[]
    legacy_conflicts=[]
    internal=[]
    warnings=[]
    if not item.get('watch_date'):
        warnings.append('이전 버전의 날짜 없는 초안입니다. 날짜를 정한 뒤 다시 저장해 주세요.')
    for i,left in enumerate(own):
        for right in own[i+1:]:
            if overlaps(left,right):
                internal.append([left[2],right[2]])
                warnings.append(f'일정 안에서 {left[3]}과(와) {right[3]}의 시간이 겹칩니다.')
    for row in db.execute('SELECT * FROM itineraries WHERE itinerary_id != ? ORDER BY itinerary_id',(item['itinerary_id'],)):
        other=decode(row)
        if any(overlaps(a,b) for a in own for b in intervals(other)):
            conflicts.append(other['itinerary_id'])
            warnings.append(f"다른 약속 ‘{other['title']}’(#{other['itinerary_id']})과 시간이 겹칩니다. 저장은 유지됩니다.")
    for row in db.execute('SELECT * FROM plans ORDER BY plan_id'):
        other=json.loads(row['payload'])
        if any(overlaps(a,b) for a in own for b in intervals(other,legacy=True)):
            legacy_conflicts.append(row['plan_id'])
            warnings.append(f"기존 관람 약속 ‘{other['movie_nm']}’(#{row['plan_id']})과 시간이 겹칩니다. 저장은 유지됩니다.")
    unknown=len(item['stops'])-len(own)
    if unknown:
        warnings.append(f'시간이 미정이거나 시작·종료가 같은 항목 {unknown}개는 시간 겹침을 판단할 수 없습니다.')
    return {**item,'overlap_itinerary_ids':conflicts,'overlap_plan_ids':legacy_conflicts,'overlapping_stop_ids':internal,'warnings':warnings}


def save_itinerary(plan,itinerary_id=None):
    payload=json.dumps(plan.model_dump(mode='json'),ensure_ascii=False)
    with store.connect() as db:
        if itinerary_id is None:
            itinerary_id=db.execute('INSERT INTO itineraries(payload,created_at) VALUES (?,?)',(payload,store.now())).lastrowid
        elif not db.execute('UPDATE itineraries SET payload=? WHERE itinerary_id=?',(payload,itinerary_id)).rowcount:
            return None
        return with_warnings(db,decode(db.execute('SELECT * FROM itineraries WHERE itinerary_id=?',(itinerary_id,)).fetchone()))


def list_itineraries():
    with store.connect() as db:
        return [with_warnings(db,decode(row)) for row in db.execute('SELECT * FROM itineraries ORDER BY itinerary_id DESC')]


def get_itinerary(itinerary_id):
    with store.connect() as db:
        row=db.execute('SELECT * FROM itineraries WHERE itinerary_id=?',(itinerary_id,)).fetchone()
        return with_warnings(db,decode(row)) if row else None


def delete_itinerary(itinerary_id):
    with store.connect() as db:
        return bool(db.execute('DELETE FROM itineraries WHERE itinerary_id=?',(itinerary_id,)).rowcount)


router=APIRouter(prefix='/api/itineraries',tags=['itineraries'])


@router.post('',response_model=ItineraryOut,status_code=201)
def create(plan:ItineraryIn):
    return save_itinerary(plan)


@router.get('',response_model=list[ItineraryOut])
def list_all():
    return list_itineraries()


@router.get('/{itinerary_id}',response_model=ItineraryOut)
def get_one(itinerary_id:int):
    item=get_itinerary(itinerary_id)
    if item is None:
        raise HTTPException(404,'저장한 일정이 없습니다.')
    return item


@router.put('/{itinerary_id}',response_model=ItineraryOut)
def update(itinerary_id:int,plan:ItineraryIn):
    item=save_itinerary(plan,itinerary_id)
    if item is None:
        raise HTTPException(404,'저장한 일정이 없습니다.')
    return item


@router.delete('/{itinerary_id}',status_code=204)
def delete(itinerary_id:int):
    if not delete_itinerary(itinerary_id):
        raise HTTPException(404,'저장한 일정이 없습니다.')
