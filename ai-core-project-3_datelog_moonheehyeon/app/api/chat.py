"""대화 API. 세션 ID는 클라이언트가 후속 대화에 재사용한다."""
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from ..agent import MovieAgent
from ..llm import AgentConfigurationError
from ..schemas import ChatIn, ChatOut

router = APIRouter(prefix='/api/chat', tags=['chat'])


@router.post('', response_model=ChatOut)
def chat(request: ChatIn):
    try:
        return MovieAgent().run(request.session_id or uuid4().hex, request.message,
                                course=request.course.model_dump(mode='json',exclude_unset=True) if request.course else None)
    except AgentConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from None
