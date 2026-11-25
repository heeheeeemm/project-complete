"""관람 계획 라우터. 기존 경로와 상태 코드를 유지한다."""
from fastapi import APIRouter, HTTPException
from ..schemas import PlanIn, PlanOut
from .. import store

router = APIRouter(prefix='/api/plans', tags=['plans'])
NOT_FOUND = '그런 관람 계획이 없습니다.'

@router.post('', response_model=PlanOut, status_code=201)
def create_plan(plan: PlanIn):
    return store.save_plan(plan)

@router.get('', response_model=list[PlanOut])
def list_plans():
    return store.list_plans()

@router.get('/{plan_id}', response_model=PlanOut)
def get_plan(plan_id: int):
    item = store.get_plan(plan_id)
    if item is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return item

@router.put('/{plan_id}', response_model=PlanOut)
def update_plan(plan_id: int, plan: PlanIn):
    item = store.save_plan(plan, plan_id)
    if item is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return item

@router.delete('/{plan_id}', status_code=204)
def delete_plan(plan_id: int):
    if not store.delete_plan(plan_id):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
