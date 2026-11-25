# 요구사항 충족표

원본 명세서 5~20쪽의 기능·비기능 요구사항과 22쪽의 제출 항목을 기준으로 정리했습니다.
실행일: 2026-11-06. 캡처는 실제 웹 화면이며, 외부 호출 대역을 사용하는 자동 테스트와 구분합니다.

| 번호 | 구현 파일·확인 내용 | 실제 실행 증빙 |
|---|---|---|
| F701 | `web/recommend/models.py`, `forms.py`, `views.recommend_form` / 필수 입력, 정상 저장, 301자 거절 | [빈 입력](screenshots/F701_empty.png), [정상 저장](screenshots/F701_saved.png), [길이 오류](screenshots/F701_length.png) |
| F702 | `proxy/main.py:chat_completions` / 도서·추천 이유 생성 | [추천 결과](screenshots/F702_F709_text_score.png) |
| F703 | `chat_guardrail`, `ensure_appropriate` / 실제 부적절한 입력 403 | [거절 화면](screenshots/F703_rejected.png) |
| F704 | `decide_route` / 소설 추천과 이미지 요청이 서로 다른 route로 분류 | [텍스트 경로](screenshots/F704_text_route.png), [이미지 경로](screenshots/F704_image_route.png) |
| F705 | `image_generations` / Gemini Interactions 호출, JPEG base64 반환 | [실제 생성 이미지](screenshots/F705_F712_image_media.png) |
| F706 | `gms_post`, `proxy_error_page` / 오류를 503 안내로 처리 | [연결 실패 화면](screenshots/F706_connection_error.png), [자동 오류 테스트](test-results/proxy-tests.txt) |
| F707 | `image_analysis` / 표지 업로드, 제목·저자 인식, 유사 도서 추천 | [분석 결과](screenshots/F707_cover_analysis.png), [입력 예시](samples/book-cover.png) |
| F708 | `views.recommend_flow` / 경로 결정 → 실행 → 결과, 거절 분기 | [텍스트](screenshots/F708_F710_flow_complex.png), [이미지](screenshots/F708_flow_image.png), [거절](screenshots/F708_flow_rejected.png) |
| F709 | `chat_score`, `text_recommend` / 0~100 점수·이유 저장·표시 | [점수·이유](screenshots/F702_F709_text_score.png) |
| F710 | `decide_model_tier` / 자동 선택 활성화 후 simple=nano, complex=mini | [단순 요청](screenshots/F710_simple_nano.png), [복잡 요청](screenshots/F708_F710_flow_complex.png) |
| F711 | `generate_speech`, `views.tts`, `result_audio.html` / nova MP3 생성, 실제 재생 확인 | [오디오 플레이어](screenshots/F711_audio.png) |
| F712 | `views.image_recommend` / JPEG 저장, UUID 파일명, media URL 제공 | [생성 이미지·주소](screenshots/F705_F712_image_media.png), [보관한 생성 결과](samples/generated-cover.jpg) |
| NF701 | `recommend/urls.py`의 `app_name`, 템플릿 `{% url %}` / URL 이름 공간 | 소스 코드, 전체 입력 화면 정상 응답 검사 |
| NF702 | `.env`에서 키 로드, 프록시만 GMS 인증, `.gitignore` / 키 제외 | `.env.example`만 포함, 제출 파일의 실제 키 포함 여부 검사 |
| NF703 | 모든 POST 폼 CSRF 토큰, Django CSRF 미들웨어 | [CSRF 포함 자동 테스트](test-results/django-tests.txt) |
| NF704 | GMS 호출 120초, Django → Proxy 호출 180초 | 소스 코드, [timeout 자동 테스트](test-results/proxy-tests.txt) |
| 추가 기능 | 후속 대화·문맥 유지·접근 제어·질문 보존·새로고침 보호 | [대화 화면](screenshots/F702_F709_text_score.png), [모바일](screenshots/extra_mobile_chat.png), [대화 자동 테스트](test-results/django-tests.txt) |

## 증빙에 관한 설명

- F706은 운영 서버의 키를 바꾸지 않고 별도의 Django 테스트 인스턴스에서 존재하지 않는
  프록시 주소로 요청해 실제 연결 실패와 503 화면을 확인했습니다. GMS 400·401·403·429·500을
  503으로 변환하는 경우는 별도의 자동 테스트로 검증했습니다.
- F707 입력은 제목·저자를 표시한 **직접 제작한 테스트용 표지**입니다. 실제 출판 표지 사진으로
  제시하지 않으며, 해당 PNG를 실제 GMS에 보내 분석한 결과를 캡처했습니다.
- F711은 플레이어 존재만 확인한 것이 아니라 `play()` 후 재생 시간이 증가하고 오류가 없는지 확인했습니다.
- 이미지 모델은 GMS에서 미지원인 명세서 모델 대신 사용자가 알려준 지원 모델을 사용했습니다.
  변경 이유와 API 계약 유지 방식은 README에 설명했습니다.
