# 요구사항 구현 및 검증 기록

## 기능 요구사항

| 번호 | 요구사항 | 구현 위치 | 검증 결과 | 캡처 |
|---|---|---|---|---|
| F601 | 회사명 입력 및 검증 | `analyzer/forms.py`, `analyzer/views.py`, `templates/analyzer/index.html` | 전체·일부 문자열 입력 가능. 빈 값은 브라우저와 Django Form에서 차단 | `01`, `06` |
| F602 | DB 스키마 구성 | `analyzer/models.py`, `analyzer/migrations/0001_initial.py` | `analyzer.0001_initial` 적용. 분석 결과 8건과 단계별 JSON 저장 확인 | `04` |
| F603 | 회사 검색 및 선택 | `06_pipeline/crawler.py` | 검색어 `엑스게이트`의 첫 결과를 자동 선택. 실제 종목명과 코드 `A356680` 저장 | `08` |
| F604 | 커뮤니티 댓글 수집 | `06_pipeline/crawler.py` | 선택 종목 상세 화면에서 원본 댓글 20개 수집 | `09` |
| F605 | 댓글 데이터 정제 | `06_pipeline/preprocess.py` | 공백·특수문자 정리, 부적절 댓글 분류, IQR 5~42자 적용 후 17개 생성 | `10` |
| F606 | 텍스트 데이터 증강 | `06_pipeline/augment.py`, `06_pipeline/llm.py` | `gpt-5-nano`로 의미 보존 문장 17개 생성 | `11` |
| F607 | 데이터 통합 관리 | `06_pipeline/run_pipeline.py`, `analyzer/views.py`, 결과 템플릿 | 정제 17개와 증강 17개를 출처와 함께 최종 34개로 통합 | `02`, `12` |
| F610 | 댓글 요약 생성 | `06_pipeline/llm.py`, 결과 템플릿 | 전체 댓글 기반 핵심 요약 생성·DB 저장·화면 출력 | `03` |
| F611 | 예외 상황 처리 및 안내 | `analyzer/views.py`, `06_pipeline/crawler.py`, `06_pipeline/llm.py` | 검색 실패, 댓글 없음, DOM 변경, API 지연 시 이해하기 쉬운 상태 안내 | `05` |

## 추가 구현

| 항목 | 구현 내용 | 증빙 |
|---|---|---|
| 진행 상태 | 제출 후 수집부터 AI 증강까지 처리 중임을 화면에 표시 | `07` |
| 결과 재조회 | `/results/latest/`, `/results/<id>/`에서 외부 호출 없이 DB 결과 조회 | `02` |
| 반응형 UI | 데스크톱과 모바일에서 검색 폼과 콘텐츠 재배치 | `01`, `13` |
| 오류 정보 보호 | 내부 스택 트레이스 대신 재시도 가능한 사용자 안내 출력 | `05` |

## DB 저장 필드

- 입력 회사명, 실제 종목명, 종목 코드
- 원본 댓글, 정제 댓글, 증강 댓글, 제거 댓글
- IQR 하한·상한
- AI 댓글 요약
- 상태 메시지와 생성일시

## 검증 명령

```powershell
python manage.py check
python manage.py showmigrations analyzer
python manage.py runserver 127.0.0.1:8000
```

`python manage.py check` 결과는 `System check identified no issues (0 silenced).`이며, `analyzer.0001_initial` 마이그레이션이 적용된 상태입니다.
