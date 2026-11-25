"""로그는 세션별 조회와 삭제만 제공하며 수정은 허용하지 않는다."""
from fastapi import APIRouter, HTTPException

from .. import store
from ..schemas import LogDetail, LogSummary

router = APIRouter(prefix='/api/logs', tags=['logs'])


@router.get('', response_model=list[LogSummary])
def list_logs():
    return store.list_logs()


@router.get('/{session_id}', response_model=LogDetail)
def get_logs(session_id: str):
    events = store.get_logs(session_id)
    if not events:
        raise HTTPException(status_code=404, detail='해당 세션의 실행 로그가 없습니다.')
    return {'session_id': session_id, 'events': events}


@router.delete('/{session_id}', status_code=204)
def delete_logs(session_id: str):
    if not store.delete_logs(session_id):
        raise HTTPException(status_code=404, detail='해당 세션의 실행 로그가 없습니다.')
