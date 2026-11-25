# 검증 결과

검증일 2026-11-20. 현재 DateLog 코드를 실제 LangGraph/SQLite, unittest와 브라우저로 점검했다. 이전 디자인/이전 실패 기록은 제출 묶음에 포함하지 않는다. 고정 응답 검증과 실제 외부 호출을 분리한다.

## 자동 검증

전체 unittest **126개 통과**, 건너뜀 없음. Python 컴파일, JavaScript 구문, OpenAPI 생성도 확인했다. 원문 출력은 tests.txt, 환경은 verification-environment.json이다. requirements.txt의 수업 지정 버전 목록은 유지했으며 검증 환경에는 langchain-core 등 일부 더 최신 전이 의존성이 설치되어 있다. 이번 작업에서 지정 버전 전체를 새 환경에 재설치한 것은 아니다.

## 필수 대표 시나리오 5개

실제 그래프·SQLite를 실행하고 LLM 분석과 외부 HTTP 경계만 고정 응답으로 대체했다. 전체 최종 응답·모든 이벤트·기대/실제·차이·호출 인자는 sample-execution.json에 있다. 결과/상한을 재현하기 위한 가상 후보이며 실제 개봉작이나 상영 시간표의 증거가 아니다.

| 유형 | 재계획 | 추천 | 오류 | 전체 시간(ms) | 기대/실제 차이 |

|---|---:|---:|---|---:|---|

| single_pass | 0 | 1 | 없음 | 1039.91 | 없음 |

| replan | 1 | 1 | 없음 | 541.24 | 없음 |

| limit | 3 | 0 | 없음 | 1124.33 | 없음 |

| partial_failure | 1 | 1 | UPSTREAM_ERROR, INVALID_KEY | 577.84 | 없음 |

| no_tool | 0 | 0 | 없음 | 203.15 | 없음 |

single_pass: 15~17시 90분 영화의 최신 시작 15:30. replan: 180분 후보 3개 제외 후 90분 후보 탐색. limit: 30분 범위에 모든 180분 후보, 재계획 3회에서 중단. partial_failure: 상세/영화관 실패를 기록하고 다른 영화 추천 유지. no_tool: 외부 Tool 호출 0회. 모든 시나리오에서 동일 인자 중복 호출 없음과 반환/저장 이벤트 동일성을 검증했다.

## 실제 서버·외부 API 검증

브라우저 HTTP 클라이언트로 실행 중인 8000 서버를 호출했다. 요청·전체 응답·이벤트는 live-integration.json, live-kobis.json, live-ui.json에 있다. LLM 키를 클라이언트에 전달하지 않고 서버가 현재 설정을 사용했다. 인사/복잡한 요청에서 실제 LLM, search_places에서 카카오, search_movies/get_movie_detail/get_boxoffice에서 KOBIS, get_showtimes에서 3사 조회를 확인했다. 실제 성공 호출을 고정 응답 테스트로 대체하지 않았다.

live-integration.json의 직접 API 요청은 약 0.6~3.2초, live-kobis.json의 상세/인물 요청은 약 2.3~4.8초였다. live-ui.json은 요청·화면 렌더링·스크린샷 저장까지 포함해 약 5.2~7.3초이며 API 응답 시간만의 지표로 해석하지 않는다. 네트워크·모델·지점 수에 따라 달라진다. 부하 테스트·전국 전체 지점 성능 보장은 수행하지 않았다.

강남 <폭설> 14~18시 요청은 실제 조회 회차 1개가 표시되었다. CGV/메가박스 상태는 ok, 롯데는 no_theater로 기록되어 해당 검색 범위에서 대상 지점을 찾지 못했다. no_theater를 롯데 전체 장애나 전국 상영 없음으로 해석하지 않는다. 서면 카페는 실제 8개 장소가 표시되었다. 임영웅 요청은 실제 4개 작품 후보 확인 질문으로 이어지고 날짜를 임의로 채우지 않았다.

실제 점검 중 “박스오피스 순위 알려줘”가 관람 날짜 질문으로 오분류되었다(live-kobis.json 첫 요청). 단순 사실 조회 규칙을 추가하고 회귀 테스트와 실제 재호출을 수행했다. 수정 후 live-ui.json의 boxoffice 요청은 get_boxoffice 성공, 질문 없음이다. 실제 LLM 의미 해석을 모든 문장에 대해 보장하지 않는다.

## 저장·Memory·화면 검증

crud-verification.json: 무날짜 최종 저장 422, 날짜 포함 저장 성공, 다른 약속과 겹쳐도 저장 성공/경고, 수정 후 경고 해제, 삭제 204. 임시 검증 레코드는 삭제했다. 단위 테스트는 기존 계획과 새 일정의 양방향 겹침·인접 시간·일정 내부 겹침·미정 시각·날짜 없는 기존본을 확인한다.

브라우저에서 직접 장소 2개 추가→순서 이동→날짜 없이 저장 시 필수 입력 차단을 확인했다. 날짜 없는 초안은 유지된다. 1440px 데스크톱과 390px 모바일 가로 넘침 없음. 저장 중 편집 버튼 잠금, 서버 저장 후 다시 읽기·수정·삭제, 삭제된 anchor가 되살아나지 않는 회귀 테스트를 포함한다. 지도 자동 검색은 영화 카드를 관광지로 덮지 않는다.

로깅은 logger-isolation.json의 구독 없음/정상/저장 장애 3모드 모두 메인 성공·LLM 0회. 정상 모드의 반환 이벤트와 저장 이벤트가 완전히 같다. Tool 6개 출력 계약 정상 재생·잘못된 입력·필요한 키 누락은 tool-verification.json에 기록했다. 시간표 Tool은 API 키가 필요 없어 키 누락은 해당없음이다.

## 화면 증빙 대응

| 화면 | 확인 항목 | 실제/고정 |

|---|---|---|

| submission-desktop.png / submission-mobile.png | 디자인·자유 순서·날짜 필수·모바일 | 실제 UI |

| submission-live-cafe.png | 장소·주소·링크·카드 | 실제 외부 호출 |

| submission-live-movie.png | 작품 시간 범위·3사 상태·잔여석 | 실제 외부 호출 |

| submission-live-confirmation.png | 인물명 작품 확인 질문 | 실제 외부 호출 |

| submission-live-boxoffice.png | KOBIS 사실 조회·단계/결과 | 실제 외부 호출 |

| submission-single_pass.png / submission-replan.png | 판단 근거·추천·재계획 | 고정 응답 재생 |

| submission-limit.png | 상한·중단 사유 대화 안내 | 고정 응답 재생 |

| submission-partial_failure.png | 일부 실패 후 성공 결과 유지 | 고정 응답 재생 |

| submission-no_tool.png | 사용법 요청·Tool 불필요 | 고정 응답 재생 |

| submission-replan-events.png | 순서별 단계·Tool·재계획 강조 | 고정 응답 재생 |

| submission-loading.png / submission-missing-key.png | 처리 중 버튼 잠금·설정 오류·재활성화 | 고정 503 |

| submission-no-showtimes.png | 해당 시간 회차 없음 대화 안내 | 빈 결과 재생, 실제 상영 없음 증거 아님 |

| submission-saved-overlap.png | 생성 시각·겹침 경고·수정/삭제 | 실제 API/임시 레코드 |


고정 시나리오 화면은 실제 서버에서 생성한 그래프 결과 JSON을 브라우저 응답에 재생하여 검증했다. 처리 중/키 오류/빈 결과도 외부 계정 설정을 변경하지 않고 브라우저 응답만 대체했다. 실제 좌석 증거와 구분한다. 체크리스트 수식·병합은 보존, cached count를 별도로 재계산·검증했다. Excel 앱 자체 렌더링은 수행하지 않았다.

## 수정 사항과 남은 한계

제출 전 날짜 필수/양방향 겹침 경고/상한 안내/조사 없는 지역 입력/지역 수식어 오인식/박스오피스 사실 조회를 실패 테스트로 재현한 뒤 수정했다. 선택 심화 F3020~F3023은 해당없음이다. 계정별 쿼터 잔여량, 외부 내부 API의 배포 허락, 사진 권한은 확인하지 않았으며 external-services.md에 명시했다. 키·DB·가상환경 제외와 압축 해제본 테스트는 package-verification.json에서 확인한다.

## 재실행

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\venv\Scripts\python.exe -m scripts.verify_scenarios --output docs/sample-execution.json
.\venv\Scripts\python.exe -m scripts.verify_submission
.\venv\Scripts\python.exe -m compileall -q app scripts tools_start.py serve_frontend.py
```
