# 실행 결과 캡처 목록

| 파일 | 관련 요구사항 | 확인 내용 |
|---|---|---|
| `01_company_input.png` | F601 | 회사명 전체·일부 문자열 입력 화면 |
| `02_analysis_result.png` | F603~F607 | 엑스게이트 전체 분석 결과와 단계별 개수 |
| `03_summary.png` | F610 | 전체 댓글 기반 AI 핵심 요약 |
| `04_database_check.png` | F602 | 마이그레이션 적용, DB 테이블, 저장 건수와 필드 |
| `05_exception_message.png` | F611 | 외부 수집 실패 시 사용자 안내 |
| `06_empty_input_validation.png` | F601 | 빈 입력 제출 차단과 필수 항목 메시지 |
| `07_loading_state.png` | 추가 | 댓글 수집·분석 중 진행 상태 안내 |
| `08_company_search_selection.png` | F603 | 첫 검색 결과로 선택된 실제 회사명과 종목 코드 |
| `09_raw_comment_collection.png` | F604 | 수집된 원본 댓글 20개 |
| `10_comment_preprocessing.png` | F605 | 정제 및 길이 필터를 통과한 댓글 17개 |
| `11_text_augmentation.png` | F606 | 생성형 모델로 만든 증강 댓글 17개 |
| `12_integrated_dataset.png` | F607 | 정제·증강 데이터를 출처 태그와 함께 통합한 34개 결과 |
| `13_mobile_responsive.png` | 추가 | 390px 모바일 화면의 반응형 배치 |

캡처는 저장된 실제 분석 결과 `/results/latest/`와 입력·예외 화면을 기준으로 생성했습니다.
