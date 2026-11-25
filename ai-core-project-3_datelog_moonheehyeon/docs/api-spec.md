# API 명세서

백엔드 `http://127.0.0.1:8000`, 화면 `http://localhost:5500`. CORS는 로컬 화면 두 호스트만 허용한다. 정확한 필수 필드·길이·타입·응답·검증 오류는 [openapi.json](openapi.json), 실행 중 `/docs`에 있다.

| Method | 경로 | 요청/설명 | 응답 |

|---|---|---|---|

| GET | `/api/plans` | List Plans | 200 |

| POST | `/api/plans` | PlanIn | 201, 422 |

| GET | `/api/plans/{plan_id}` | plan_id 필수 | 200, 422 |

| PUT | `/api/plans/{plan_id}` | plan_id 필수; PlanIn | 200, 422 |

| DELETE | `/api/plans/{plan_id}` | plan_id 필수 | 204, 422 |

| POST | `/api/chat` | ChatIn | 200, 422 |

| GET | `/api/logs` | List Logs | 200 |

| GET | `/api/logs/{session_id}` | session_id 필수 | 200, 422 |

| DELETE | `/api/logs/{session_id}` | session_id 필수 | 204, 422 |

| GET | `/api/maps/config` | Map Config | 200 |

| GET | `/api/cinemas` | region 필수 | 200, 422 |

| GET | `/api/places` | region 필수, kind 필수, cuisine 선택, anchor_name 선택, lat 선택, lng 선택 | 200, 422 |

| GET | `/api/showtimes` | region 필수, movie_nm 필수, watch_date 필수, start_time 선택, deadline 선택, buffer_minutes 선택, deadline_inclusive 선택, brands 선택 | 200, 422 |

| GET | `/api/itineraries` | List All | 200 |

| POST | `/api/itineraries` | ItineraryIn | 201, 422 |

| GET | `/api/itineraries/{itinerary_id}` | itinerary_id 필수 | 200, 422 |

| PUT | `/api/itineraries/{itinerary_id}` | itinerary_id 필수; ItineraryIn | 200, 422 |

| DELETE | `/api/itineraries/{itinerary_id}` | itinerary_id 필수 | 204, 422 |

## 대화

POST /api/chat 요청 예: `{"message":"서면 카페 추천해줘","session_id":null}`. 선택 course는 현재 선택 장소 snapshot이다. 응답은 session_id/run_id/answer/question/notice/conditions/recommendations/excluded/cinemas/showtimes/showtime_search/places/place_search/course/events/errors/replans. 성공은 카드로 표시하고 질문·상한·없음만 대화에 표시한다. 구성·LLM 오류는 503, 입력 오류는 422.

## 자유 일정

POST /api/itineraries 예: `{"title":"서면 데이트","watch_date":"2026-11-21","stops":[{"kind":"cafe","name":"선택한 카페","start_time":"14:00","end_time":"15:00"}]}`. 날짜 필수, stops 1~50개, kind는 movie/restaurant/cafe/place. 순서 그대로 보관하며 장소 종류 횟수 제한은 없다. Stop.id는 생략하면 생성한다. 응답은 itinerary_id/created_at/overlap_itinerary_ids/overlap_plan_ids/overlapping_stop_ids/warnings를 추가한다. 무날짜 기존본은 조회만 허용하고 재저장 시 날짜를 요구한다.

새 일정은 종료가 시작보다 이르면 익일로 해석한다. 시작·종료 누락/동일 시각은 겹침 판단 불가 경고. 반열린 구간으로 비교하여 바로 이어지는 약속은 겹침이 아니다. 새 일정끼리, 일정 내부, 기존 관람 계획과 양방향 비교한다. 겹침은 201/200 저장 성공과 함께 경고한다. PUT은 전체 입력 교체, 없는 ID는 404, DELETE는 204이다.

## 기존 관람 계획

/api/plans 요청 PlanIn의 movie_nm/watch_date 필수. start_time/end_time/movie_cd/cinema/restaurant/cafe는 선택. 시각 HH:MM, 날짜 YYYY-MM-DD. 기존 관람 계획은 같은 날 종료>시작을 요구한다. PlanOut에는 plan_id/created_at/overlap_plan_ids/overlap_itinerary_ids/warnings가 추가된다.

## 로그

GET /api/logs는 session_id/event_count/updated_at 목록, GET /api/logs/{session_id}는 session_id/events 전체를 순서대로 반환한다. DELETE는 204. 없는 세션 404, PUT/PATCH는 제공하지 않는다.

## 검색/공개 설정

/api/cinemas와 /api/places는 LLM 없이 REST 검색. /api/showtimes는 region/movie_nm/watch_date 필수, 시각·종료·여유·브랜드 선택. /api/maps/config는 도메인 제한용 공개 JavaScript 키만 응답하며 비밀 키와 동일한 설정은 차단한다. 히어로 사진 /api/hero-image는 로컬 딸기케익.jpg만 제공한다.
