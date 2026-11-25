# 제출 자료 안내

`수정 명세서.pdf` 28~30쪽의 제출 목록을 기준으로 구성했다. 압축을 풀면 `DateLog/` 아래에서 바로 실행할 수 있다. `.env`, 가상환경, 실제 DB, 기존 개인 대화 기록은 포함하지 않는다. 설정 예시는 빈 키만 들어 있다.

| PDF 제출 항목 | 포함 파일 |
|---|---|
| 1. 요구사항 정의서 | docs/requirements.md (F3001~F3019, NF3001~NF3007, 심화 선택 여부·도메인·기획 검증) |
| 2. Agent 설계 문서 | docs/agent-design.md, docs/agent-graph.mmd |
| 3. Tool 정의서 | docs/tool-definitions.md, docs/tool-catalog.json |
| 4. API 명세서 | docs/api-spec.md, docs/openapi.json |
| 5. 검증 결과·실행 로그·스크린샷 | docs/validation.md, tests.txt, sample-execution.json, live-*.json, submission-*.png |
| 6. 제공 셀프 체크리스트 작성본 | docs/셀프체크리스트_점검완료.xlsx |
| 7. 백엔드·프론트엔드·Tool 소스 | app/, index.html, tools_start.py, serve_frontend.py, scripts/, tests/ |
| 8. README | README.md, docs/external-services.md |

체크리스트는 통과 26건, 해당없음 6건(고위험 도메인 1건과 선택하지 않은 심화 5행)이다. 수식·병합·양식을 유지하고 현재 집계 캐시를 대조했다. 작성자 성명은 제공되지 않아 `제출자 성명 미기입`으로 남겼다. 학번·성명을 임의로 만들지 않았다.

실제 외부 호출과 고정 응답 검증은 구분되어 있다. sample-execution.json과 상한/재계획/부분 실패 화면은 재현 가능한 고정 응답 검증이다. live-*.json 및 submission-live-*.png는 실제 실행 중인 서버를 호출한 결과다. 좌석·장소 정보는 점검 시각 이후 달라질 수 있다.

필수 구현/검증 범위는 requirements.md에서 확인한다. 계정별 잔여 할당량, 영화관 내부 API의 공개 서비스 사용 허락, 사진 공개 배포 권한은 검증 완료로 표기하지 않았다. 선택 심화 F3020~F3023은 구현 대상에 포함하지 않았다.

`manifest.json`은 포함된 파일별 SHA-256을 기록하며 `docs/package-verification.json`에 ZIP 무결성·금지 파일·압축 해제본 검증 결과가 있다. ZIP 자체의 SHA-256은 함께 제공되는 `.sha256` 파일에 있다. lab.ssafy.com 업로드는 수행하지 않았다.
