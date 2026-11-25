# 실행 검증 기록

검증일: 2026-11-06 (Asia/Seoul)

## 환경

- Python 3.11 가상환경, Django 5.2.6, FastAPI 0.121.0, Uvicorn 0.38.0
- Django `127.0.0.1:8080`, FastAPI Proxy `127.0.0.1:8081`
- 브라우저 화면: PC 1440×1100, 모바일 390×844
- 이미지 모델: `gemini-3.1-flash-lite-image`
- 텍스트 모델: `gpt-5-nano`, `gpt-5-mini`
- 음성 모델: `gpt-4o-mini-tts`, voice `nova`, MP3

## 자동 검증

| 항목 | 결과 | 원본 출력 |
|---|---|---|
| Django 시스템 검사 | 문제 없음 | [django-check.txt](test-results/django-check.txt) |
| 모델·마이그레이션 일치 | 변경 사항 없음 | [migration-check.txt](test-results/migration-check.txt) |
| Django 테스트 | 19개 통과 | [django-tests.txt](test-results/django-tests.txt) |
| 프록시 테스트 | 12개 통과 | [proxy-tests.txt](test-results/proxy-tests.txt) |

자동 테스트에서는 외부 GMS 응답을 대체합니다. 다음 브라우저 검증은 실제 GMS를 호출했습니다.

## 실제 브라우저 검증

- 필수 입력 누락·301자 입력이 저장되지 않고 오류로 표시됨, 정상 입력은 저장됨.
- 추천 결과의 도서·이유와 0~100점 평가가 표시됨.
- 부적절한 요청은 403으로 거절됨.
- 텍스트 요청은 `/chat/completions`, 표지 제작 요청은 `/images/generations`로 분류됨.
- 이미지 생성이 HTTP 200으로 완료되고 `/media/images/UUID.jpg`가 표시됨.
- 테스트 표지 업로드 후 제목·저자와 유사 도서 추천이 표시됨.
- 통합 흐름의 텍스트·이미지·거절 경로를 각각 확인함.
- 자동 모델 선택 활성화 후 단순 요청은 `gpt-5-nano`, 복잡 요청은 `gpt-5-mini`가 표시됨.
- TTS HTTP 200, 음성 길이 7.248초, 재생 후 `currentTime > 0`, 플레이어 오류 없음.
- 첫 추천 이후 “방금 추천한 두 책 중 무엇부터 읽을까?”에 이전 도서를 참조한 답변이 반환됨.
- 웹 서버 재시작 후 같은 세션의 대화와 문답이 유지됨.
- PC·모바일에서 가로 넘침이 없고 입력 예시 버튼이 동작함.

## 이미지 API 연동 수정

원래 모델 `gpt-image-1-mini` 요청에서 다음 실제 GMS 응답을 확인했습니다.

```text
HTTP 400: [GMS 에러] Model gpt-image-1-mini is not available in Model
```

사용자가 제공한 [GMS 모델 가이드](https://gms.ssafy.io/web/guide/gemini-3.1-flash-lite-image)와
[공개 가이드](https://gms.ssafy.io/web/public/guide/gemini-3.1-flash-lite-image)를 확인해
Gemini Interactions API로 연결했습니다. OpenAI용 Bearer 헤더 대신 `x-goog-api-key`를 사용하며,
실제 `steps[].content[]` 응답에서 이미지를 찾아 JPEG로 변환합니다.
수정 후 개별 이미지 생성·미디어 저장과 통합 흐름의 이미지 생성을 모두 HTTP 200으로 확인했습니다.

## 오류 확인 방식

일반 서버의 GMS 키는 유지했습니다. 포트 8082의 임시 웹 서버만 존재하지 않는 프록시 주소를
사용하도록 실행해 연결 실패와 오류 화면을 캡처했습니다. 캡처 후 임시 서버는 종료합니다.
이는 실제 GMS 인증 실패를 재현한 캡처가 아니며, 인증 실패의 상태 변환은 자동 테스트로 확인했습니다.

## 제한과 재현 시 주의

- 모델 응답은 매번 달라지므로 캡처와 문장이 동일할 필요는 없습니다.
- 도서 정보와 적합도 점수는 AI 출력으로, 실제 출간 정보에 대한 별도 교차 검증은 구현하지 않았습니다.
- 이미지 분석 샘플은 테스트용으로 직접 만든 표지이며 실제 출판 표지는 아닙니다.
- GMS 키와 크레딧, 모델 사용 가능 여부, 인터넷 연결이 필요합니다.
- 개발 도구가 시작한 프로세스의 외부 통신이 차단될 수 있어 실제 GMS 호출은 일반 PowerShell에서 시작한 프록시를 사용했습니다.
