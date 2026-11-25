"""요청·응답 스키마. 기존 관람 계획 입력 필드를 유지한다."""
from datetime import date, datetime
from typing import Literal
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class SelectedPlace(BaseModel):
    name: str = Field(min_length=1,max_length=200)
    lat: float = Field(ge=-90,le=90)
    lng: float = Field(ge=-180,le=180)
    address: str | None = Field(default=None,max_length=300)
    url: str | None = Field(default=None,max_length=1000)

class PlanIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    movie_nm: str = Field(min_length=1, max_length=200)
    watch_date: date
    start_time: str | None = None
    end_time: str | None = None
    movie_cd: str | None = None
    cinema: str | None = None
    restaurant: SelectedPlace | None = None
    cafe: SelectedPlace | None = None

    @field_validator('start_time', 'end_time')
    @classmethod
    def validate_time(cls, value):
        if value is not None and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
            raise ValueError('시각은 HH:MM 형식이어야 합니다.')
        return value

    @model_validator(mode='after')
    def check_interval(self):
        if self.end_time and not self.start_time:
            raise ValueError('종료 시각에는 시작 시각이 필요합니다.')
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValueError('종료 시각은 같은 날짜의 시작 시각보다 늦어야 합니다.')
        return self

class PlanOut(PlanIn):
    plan_id: int
    created_at: datetime
    overlap_plan_ids: list[int] = Field(default_factory=list)
    overlap_itinerary_ids: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

class Conditions(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    watch_date: date | None = None
    start_time: str | None = None
    deadline: str | None = None
    deadline_inclusive: bool | None = None
    region: str | None = Field(default=None, max_length=100)
    genre: str | None = None
    movie_cd: str | None = Field(default=None, pattern=r'^\d{8}$')
    movie_nm: str | None = Field(default=None, min_length=1, max_length=200)
    movie_query: str | None = Field(default=None,min_length=1,max_length=100)
    brands: list[Literal['cgv', 'lotte', 'megabox']] | None = Field(default=None, min_length=1, max_length=3)
    budget: int | None = Field(default=None, ge=0)
    buffer_minutes: int | None = Field(default=None, ge=0, le=240)
    place_kind: Literal['restaurant','cafe'] | None = None
    cuisine: str | None = Field(default=None,max_length=40)
    place_region: str | None = Field(default=None,max_length=100)
    place_anchor: Literal['cinema','restaurant','cafe'] | None = None
    _times = field_validator('start_time', 'deadline')(PlanIn.validate_time.__func__)

class PendingTime(BaseModel):
    field: Literal['start_time', 'deadline']
    hour: int = Field(ge=0, le=23)
    minute: int = Field(ge=0, le=59)
    inclusive: bool = True
    end_hour: int | None = Field(default=None,ge=0,le=23)
    end_minute: int | None = Field(default=None,ge=0,le=59)

class Analysis(BaseModel):
    intent: Literal['plan', 'facts', 'help', 'save', 'showtimes', 'places']
    conditions: Conditions = Field(default_factory=Conditions)
    reason: str
    question: str | None = None
    pending_field: Literal['movie_nm', 'movie_confirmation', 'region', 'watch_date', 'start_time', 'deadline'] | None = None
    pending_time: PendingTime | None = None
    different_movie: bool = False
    movie_preference: Literal['recent'] | None = None
    tool_names: list[Literal['get_boxoffice', 'get_movie_detail', 'search_cinemas', 'get_showtimes', 'search_places','search_movies']] = Field(default_factory=list)

class SelectedMovie(BaseModel):
    movie_nm: str = Field(min_length=1,max_length=200)
    cinema: str = Field(min_length=1,max_length=200)
    watch_date: date
    start_time: str | None = None
    end_time: str | None = None
    brand: Literal['cgv','lotte','megabox'] | None = None
    schedule_id: str | None = Field(default=None,max_length=200)
    _times = field_validator('start_time','end_time')(PlanIn.validate_time.__func__)

class CourseAnchor(BaseModel):
    name: str = Field(min_length=1,max_length=200)
    lat: float | None = Field(default=None,ge=-90,le=90)
    lng: float | None = Field(default=None,ge=-180,le=180)

class CourseContext(BaseModel):
    movie: SelectedMovie | None = None
    restaurant: SelectedPlace | None = None
    cafe: SelectedPlace | None = None
    anchor: CourseAnchor | None = None

class ChatIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    course: CourseContext | None = None

class ChatOut(BaseModel):
    session_id: str
    run_id: str
    answer: str
    question: str | None = None
    notice: str | None = None
    movie_matches: list[dict] = Field(default_factory=list)
    conditions: Conditions
    recommendations: list[dict] = Field(default_factory=list)
    excluded: list[dict] = Field(default_factory=list)
    cinemas: list[dict] = Field(default_factory=list)
    showtimes: list[dict] = Field(default_factory=list)
    showtime_search: dict | None = None
    places: list[dict] = Field(default_factory=list)
    place_search: dict | None = None
    course: dict = Field(default_factory=dict)
    events: list[dict] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)
    replans: int = 0

class LogSummary(BaseModel):
    session_id: str
    event_count: int
    updated_at: datetime

class LogDetail(BaseModel):
    session_id: str
    events: list[dict]
