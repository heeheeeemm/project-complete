# 데이트로그 (DateLog)

가고 싶은 장소를 찾아 자유롭게 순서와 시간을 정하고 약속으로 저장하는 데이트 일정 노트입니다. 영화는 선택 사항이며 카페 두 곳, 식사와 산책만으로도 일정을 만들 수 있습니다.

## 실행

Windows PowerShell, Python 3.10 이상을 사용합니다. 처음 받은 ZIP에는 가상환경과 실제 API 키가 없습니다.

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

기존 .env가 있다면 덮어쓰지 마세요. .env에 키를 설정합니다.

| 변수 | 설정 방법 |
|---|---|
| KOBIS_API_KEY | KOBIS 가입 후 키 발급/관리에서 발급한 키 |
| KAKAO_REST_API_KEY | Kakao Developers 앱의 REST API 키. 카카오맵 사용 설정·권한 확인 |
| KAKAO_JAVASCRIPT_KEY | 지도 SDK용 JavaScript 키. SDK 도메인 localhost:5500, 127.0.0.1:5500 등록 |
| OPENAI_API_KEY | 사용하는 OpenAI 호환 공급자의 키. 변수 이름은 OPEN_API_KEY가 아닌 OPENAI_API_KEY |
| OPENAI_MODEL | 공급자가 허용하는 실제 모델명 |
| OPENAI_BASE_URL | 해당 키의 호환 API 주소. GMS 주소 예시는 .env.example 참고 |
| MAX_REPLANS | 기본 3, 최대 3회 |
| PLANNER_DB_PATH | 기본 data/planner.db, 첫 실행 시 생성 |

터미널 두 개에서 실행합니다.

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

```powershell
.\venv\Scripts\python.exe serve_frontend.py
```

사이트: **http://localhost:5500** · API 문서: http://127.0.0.1:8000/docs . 백엔드 8000의 `/`는 화면 주소가 아닙니다. `Application startup complete`는 서버가 정상 대기 중이라는 뜻입니다. 키 변경 후 백엔드를 재시작합니다.

## 기능

- 카카오 지도·장소 검색과 대화로 식당/카페/영화관/가고 싶은 곳 찾기. 양식 등 명시한 음식 종류와 선택 장소 주변 검색.
- KOBIS 제목/출연자 검색으로 작품 확인. 날짜·오전/오후·영화가 누락되면 필요한 것만 질문하고 후속 대화 조건 유지.
- CGV·롯데시네마·메가박스 시간표·잔여석 통합 조회. 실제 회차의 시작/종료·브랜드 상태·조회 시각·공식 예매 링크 표시. 좌석 새로고침 지원.
- KOBIS 후보와 러닝타임으로 종료 제한·여유 시간 비교, 대안 재계획 최대 3회. 후보 추천과 실제 시간표는 구분.
- 일정에 담기·직접 추가·순서 이동·시간 지정. 날짜 없는 초안은 브라우저에 유지. 최종 약속 저장 때 날짜 필수. 서버에 저장하면 내 약속에서 다시 읽기·수정·삭제.
- 시간이 겹쳐도 저장하고 경고. 새 일정 내부/다른 일정/이전 관람 계획을 비교. 시각 미정은 판단 불가 표시.
- 성공 결과는 선택 카드로 표시. 대화는 필요한 질문·상한·상영 없음 안내에 사용. 실행 기록에서 단계·Tool·실패·재계획 조회/삭제.
- 사용자가 제공한 딸기케익.jpg와 한글 다이어리 디자인. 데스크톱·모바일 지원.

실시간 좌석은 조회 후 변경될 수 있으며 예매/결제는 수행하지 않습니다. 가격·영업시간·이동시간·평점을 만들어 주지 않습니다. 기존 관람 계획은 같은 날 종료만, 자유 일정은 종료가 시작보다 이르면 익일로 해석합니다. 결과 실패와 실제 상영 없음은 구분합니다.

## 필수/선택 기능과 구조

수정 명세서의 필수 F3001~F3019 및 비기능 NF3001~NF3007의 구현·검증 대응은 [요구사항 정의서](docs/requirements.md)에 있습니다. 선택 심화 F3020~F3023(이상 탐지, Planner/Worker 분리, RAG, Calendar)은 선택하지 않았습니다.

LangGraph `analyze → plan → execute → judge → respond`, 조건 미충족 시 `judge → plan`. 로깅 Agent는 이벤트를 독립 구독하며 LLM 없이 저장합니다. 인자별 캐시, 부분 실패 격리, 세션 Memory를 사용합니다.

| 위치 | 역할 |
|---|---|
| app/agent.py, app/llm.py, *_request.py | 그래프·LLM/규칙 분석·판단·Memory |
| tools_start.py, app/showtime_search.py, app/places.py | 6개 Tool 등록·출력 계약·외부 조회 |
| app/events.py, app/store.py | 독립 로깅·SQLite |
| app/api/, app/itineraries.py | 대화·검색·약속·로그 HTTP API |
| index.html, serve_frontend.py | 별도 화면 서버. index.html만 정적 제공 |
| tests/, scripts/ | 회귀 테스트·검증·제출 생성 도구 |

## 제출 문서

- [제출 자료 안내](docs/submission-guide.md)
- [Agent 설계](docs/agent-design.md), [Tool 정의](docs/tool-definitions.md), [API 명세](docs/api-spec.md)
- [검증 결과](docs/validation.md), [대표 실행 전체 로그](docs/sample-execution.json), [작성된 체크리스트](docs/셀프체크리스트_점검완료.xlsx)
- [외부 API 출처·호출 한도·약관·확인 한계](docs/external-services.md)

KOBIS·카카오 계정별 잔여 한도는 확인하지 않았습니다. 영화관 시간표는 공식 웹에서 관찰한 내부 조회 API로 외부 개발자 공개 계약·재배포 허락을 확인한 기능이 아닙니다. KOBIS 결과 저장 제한과 과제 로그 요구의 적용 범위도 외부 운영 전에 확인해야 합니다. 서비스 권한을 확보했다는 주장 없이 이 범위를 문서에 기록했습니다.

## 검증

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\venv\Scripts\python.exe -m scripts.verify_scenarios --output docs/sample-execution.json
.\venv\Scripts\python.exe -m scripts.verify_live
```

전체 126개 테스트와 대표 5개 고정 시나리오가 통과했습니다. 실제 LLM·KOBIS·카카오·3사 조회 결과는 별도 live-*.json과 화면에 기록했습니다. 실제와 고정 결과는 섞어 성공으로 표기하지 않습니다. 검증 환경의 설치 버전과 지정 requirements의 차이, 실제 측정 시간은 validation.md에 있습니다. ZIP은 키·DB·개인 실행 로그·가상환경을 제외하고 압축 해제본에서 다시 점검합니다.

작성자 이름은 전달받지 않아 체크리스트의 성명만 미기입으로 남겼습니다. 제출 사이트 업로드는 수행하지 않았습니다.
