# DateLog 요구사항 정의서

기준: 제공된 `수정 명세서.pdf`(30쪽), `셀프체크리스트.xlsx`. 검증일 2026-11-20.

## 도메인과 결과물

데이트 장소를 찾고 자유로운 순서의 일정을 저장한다. 카페만 방문하거나 같은 종류 장소를 여러 번 넣을 수 있다. 영화는 선택 사항이다. 날짜 없는 작업 초안은 브라우저에 유지하고, 최종 약속은 날짜·제목·장소 목록·시간·생성 일시를 SQLite에 저장한다. 시간 겹침은 저장을 막지 않고 경고한다. 기존 영화 관람 계획도 읽기·수정·삭제를 지원한다.

외부 API는 KOBIS 일별 박스오피스, KOBIS 영화 상세, 카카오 키워드 검색의 3개 이상이다. 추가로 KOBIS 작품/인물 목록·필모그래피, 카카오 지도 SDK, CGV·롯데시네마·메가박스 시간표 조회를 사용한다. LLM은 복잡한 요청의 조건과 Tool을 선택한다. 상영 여부/잔여석/장소 정보는 실제 API 응답으로만 표시한다.

제약 요청 예: “2026-11-21 오후 3시 이후 오후 5시 전에 끝나는 영화 추천”, “같은 조건에서 여유 시간 30분도 포함해줘”, “서울 강남에서 오늘 오후 2-6시 사이에 <폭설> 보고싶어”. 종료 조건은 러닝타임 또는 실제 회차 종료+명시된 여유 시간으로 판단한다. 예산, 평점, 영업시간, 이동시간은 확인하지 않은 값을 만들어 충족한다고 말하지 않는다.

## 필수 대응표

| ID | 요구사항/구현 | 구현 근거 | 검증 근거 |
|---|---|---|---|
| F3001 | 외부 Tool 등록·입출력 계약 | tools_start.py, tool-catalog.json | test_requirements.ToolTests |
| F3002 | KOBIS 일별 후보·기본 KST 어제·요청일/집계일 표시 | tools_start.get_boxoffice | 미래일 보정/형식 검사, live-kobis.json |
| F3003 | 후보 코드에 연결한 러닝타임·장르·등급 조회 | tools_start.get_movie_detail | 러닝타임 누락 NO_RUNTIME, live-kobis.json |
| F3004 | 영화관 위치·주소·링크 검색 | search_cinemas, app/places.py | 좌표·빈 결과·키 실패 테스트, 실제 카페 검색 |
| F3005 | 사용자 의도·조건 분석, 누락·모호함 확인 | app/llm.py, *_request.py, time_conditions.py | test_movie_dialogue.py, test_conversation_context.py |
| F3006 | LangGraph 단계·Tool 선택·순서 계획 | app/agent.py | sample-execution.json의 work_plan 및 Tool 불필요 사례 |
| F3007 | 후보→상세 인자 의존·캐시·부분 실패 | app/agent.py execute | partial_failure 시나리오, 잘못된 출력 계약 테스트 |
| F3008 | 러닝타임/시작·종료/장르/여유 시간 제약 판단 | app/agent.py judge, app/showtime_search.py | single_pass, 시간 범위/미확인 종료/자정 테스트 |
| F3009 | 대안 후보 재계획·캐시·반복 상한 | judge→plan, MAX_REPLANS 0~3 | replan/limit 시나리오, 상한 notice 화면 |
| F3010 | 세션별 대화 요약·변경 조건 병합 | app/store.py, app/agent.py analyze/run | 기존 오후·작품·날짜 유지, 삭제된 anchor 제거 회귀 테스트 |
| F3011 | 출처·판단 근거·제외 이유·카드 표시 | index.html showResult, showShowtimes, showPlaces | 성공 안내 중복 제거, 없음/오류/질문만 대화 표시 |
| F3012 | 단계·Tool·LLM 결정·재계획 이벤트 | app/events.py, app/agent.py | 각 시나리오 전체 events, 시작/종료·실패 이벤트 검사 |
| F3013 | 독립 로깅 Agent, LLM 미사용·구독 장애 격리 | EventBus, LoggingAgent | logger-isolation.json, 세션 격리/구독자 실패 테스트 |
| F3014 | 로그 세션 목록·상세·삭제, 수정 불가 | app/api/logs.py | test_requirements 로그 API, openapi.json |
| F3015 | 날짜·생성 일시 포함 최종 약속 저장·목록·겹침 경고 | app/itineraries.py, app/store.py | crud-verification.json, test_submission_compliance.py |
| F3016 | 약속 수정·삭제·목록 갱신 | /api/itineraries, /api/plans, index.html | 실제 API CRUD, 자유 순서/초안 유지/저장 중 조작 방지 |
| F3017 | FastAPI 라우터·요청 응답 스키마 | app/main.py, app/api, app/schemas.py | openapi.json 및 API 통합 테스트 |
| F3018 | 분리된 화면 서버와 백엔드 HTTP 연동 | serve_frontend.py, index.html | localhost:5500→8000 실제 브라우저 호출 |
| F3019 | 단계별 실행 기록·재계획·처리 중·오류 안내 | index.html showEvents, busy/savingCourse | submission-*.png, 실패 후 재활성화 테스트 |
| NF3001 | 환경변수·키 미포함 제출 | 빈 .env.example, 화이트리스트 ZIP | package-verification.json |
| NF3002 | 안전한 오류·정적 서버 비공개 파일 차단 | app/llm.py, tools_start.py, serve_frontend.py | 오류 원문/키 비노출 및 내부 경로 404 테스트 |
| NF3003 | 개별 Tool 실패와 전체 서비스 분리 | Tool.run, execute | partial_failure 시나리오 |
| NF3004 | 재계획 유한 상한 | MAX_REPLANS 최대 3회 | limit 시나리오: 재계획 3회 후 중단 |
| NF3005 | 요청 타임아웃·캐시·응답 시간 측정 | 외부 HTTP 타임아웃, 공급자 병렬 조회 | validation.md의 고정/실제 측정 분리 |
| NF3006 | 화면/Agent/Tool/저장/이벤트 모듈 분리 | app/, tools_start.py, index.html | agent-design.md, 소스 트리 |
| NF3007 | 외부 출처·한도·약관 및 제약 문서화 | external-services.md | 공식 문서 확인, 계정별 잔여량/내부 API 사용 허락은 미확인 |

## 선택 심화

F3020 이상 탐지, F3021 Planner/Worker 분리, F3022 RAG, F3023 Google Calendar는 선택하지 않았다. 모두 체크리스트에서 해당없음이다. 기본 로깅 Agent와 자유 일정 CRUD는 심화 완료로 표기하지 않는다.

## 기획 검증과 변경

고정 응답으로 Tool 출력 계약과 LangGraph 설계를 시험하고, 실제 서버로 LLM·카카오·KOBIS·시간표를 확인했다. 결과는 validation.md와 원본 JSON에 구분한다. 사용자가 제목/날짜를 말하지 않았을 때 빈 상영으로 판단하던 흐름을 작품 확인→필수 조건 질문으로 수정했다. 오후 2-6시 범위가 후속 발화에서 유실되는 오류와 지도 자동 검색이 영화 카드를 관광지로 덮는 오류를 회귀 테스트로 수정했다. 고정 영화→식사→카페 구조를 사용자 순서의 일정 배열로 변경했다.

제출 점검에서 최종 약속의 날짜 필수, 새 일정과 이전 계획 간 양방향 겹침 경고, 재계획 상한 안내, 조사 없는 “서면 카페” 지역 추출을 추가 보완했다. 실제 단순 박스오피스 요청의 LLM 오분류는 명시적인 사실 조회 규칙으로 수정했다. 무날짜 기존 저장본은 삭제하거나 날짜를 지어내지 않고 초안으로 읽는다.
