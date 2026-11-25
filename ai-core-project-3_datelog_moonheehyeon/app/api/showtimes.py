"""LLM 없이도 사용할 수 있는 3사 실제 회차 조회 API."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Query

from tools_start import TOOLS, ToolFailure, ToolSuccess
from ..showtimes import ShowtimesData

router = APIRouter(prefix='/api/showtimes', tags=['showtimes'])


@router.get('', response_model=ToolSuccess[ShowtimesData] | ToolFailure)
def showtimes(region: str = Query(min_length=1, max_length=100),
              movie_nm: str = Query(min_length=1, max_length=200),
              watch_date: date = Query(),
              start_time: str = Query(default='00:00', pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$'),
              deadline: str | None = Query(default=None, pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$'),
              buffer_minutes: int = Query(default=0, ge=0, le=240),
              deadline_inclusive: bool = Query(default=True),
              brands: list[Literal['cgv', 'lotte', 'megabox']] = Query(default=['cgv', 'lotte', 'megabox'])):
    return TOOLS['get_showtimes'].run(region=region, movie_nm=movie_nm, watch_date=watch_date.isoformat(),
                                     start_time=start_time, deadline=deadline, buffer_minutes=buffer_minutes, brands=brands, deadline_inclusive=deadline_inclusive)
