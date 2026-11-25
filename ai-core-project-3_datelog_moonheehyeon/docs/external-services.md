# 외부 API 출처와 이용 조건

확인일: 2026-11-20. 공개 정책 문서를 확인한 범위와 계정에 로그인해야 확인되는 사항을 구분한다. 아래 기록은 서비스 운영 허락을 받았다는 뜻이 아니다.

| 출처 | 사용하는 데이터 | 인증 | 한도·조건 |
|---|---|---|---|
| [KOBIS 제공 서비스](https://www.kobis.or.kr/kobisopenapi/homepg/apiservice/searchServiceInfo.do) | 일별 박스오피스, 영화 상세, 영화/영화인 목록·필모그래피 | 서버의 KOBIS_API_KEY | 회원가입·키 발급 후 사용. 계정별 적용 한도·남은 호출 수는 미확인. 임의의 수치를 한도로 단정하지 않음 |
| [카카오맵 REST API](https://developers.kakao.com/docs/ko/local/dev-guide) | 영화관·음식점·카페·일반 장소, 좌표 | 서버 REST API 키 | 공개 쿼터의 키워드 검색 일 100,000건. 앱·권한·계정 적용 조건에 따라 달라질 수 있음 |
| [카카오 지도 SDK](https://apis.map.kakao.com/web/guide/) | 지도·마커·브라우저 장소 검색 | 공개 JavaScript 키와 SDK 도메인 등록 | 공개 쿼터의 Web SDK 일 300,000건. 개발자 계정에서 처음 활성화한 앱만 무료 쿼터 적용. 실제 앱 잔여량은 미확인 |
| CGV·롯데시네마·메가박스 공식 웹 조회 | 회차·상영관·좌석 | 별도 개발자 키 미사용 | 공식 웹에서 관찰한 내부 조회 API. 외부 개발자 공개 API 계약·공개 호출 한도·재배포 허락은 확인되지 않음. 구조 변경·접근 제한 가능 |
| [SSAFY GMS](https://gms.ssafy.io/) 또는 설정한 OpenAI 호환 공급자 | 조건 분석 JSON | 서버 OPENAI_API_KEY | 계정·모델별 요청 속도/토큰/잔여 크레딧을 따름. 잔여 크레딧과 순간 호출 제한은 별개. 계정 화면의 실제 한도는 미확인 |

카카오 수치는 [공식 쿼터 문서](https://developers.kakao.com/docs/ko/getting-started/quota)의 확인일 기준이다. 월간 전체 API 무료 제공량은 3,000,000건이며 추가 쿼터·권한별 예외가 있다. 앱 관리의 쿼터와 카카오맵 이용 정책을 기준으로 실제 적용량을 확인한다. [운영 정책](https://developers.kakao.com/terms/ko/site-policies)과 [서비스 약관](https://developers.kakao.com/terms/ko/terms)을 적용받는다. 키를 용도에 맞게 분리하고 JavaScript 키에 허용 도메인을 등록한다. 장소 상세·길찾기는 카카오맵으로 연결하며 지도 출처 표기를 유지한다.

[KOBIS 이용약관](https://www.kobis.or.kr/kobisopenapi/homepg/board/findProvisionInfo.do)은 키 공유 금지·출처 명시와 실시간 결과 사용, 결과 복제·저장·재전송 제한을 명시한다. 본 프로젝트의 수업 요구사항은 Tool 결과 실행 로그 저장을 포함하므로, 장기 운영·공개 배포 시에는 해당 저장 방식과 권리자의 허용 범위를 별도로 확인해야 한다. 제출 JSON은 점검 시점의 실행 증빙이며 운영용 데이터셋으로 사용하지 않는다. 계정별 제한은 [서비스 이용안내](https://www.kobis.or.kr/kobisopenapi/homepg/board/findServiceGuideList.do)와 키 관리·공지에서 확인한다.

영화관 원 출처: [CGV](https://cgv.co.kr/), [롯데시네마](https://www.lottecinema.co.kr/), [메가박스](https://www.megabox.co.kr/). 내부 API 접근 가능성을 이용 허락 또는 공개 API 제공으로 해석하지 않는다. 예약·결제·좌석 점유는 수행하지 않고 공식 예매 링크를 제공한다. 좌석은 조회 시점 값으로 표시하고 다시 조회할 수 있다. 실패를 상영 없음으로 바꾸지 않으며 인증 우회는 하지 않는다.

호출 절약: 요청 내 Tool 결과 재사용, 미평가 후보만 상세 조회, 재계획 최대 3회, 공급자 병렬 조회와 타임아웃을 사용한다. 429는 안전한 코드·재시도 안내로 처리한다. 고정 응답 테스트는 외부 호출을 하지 않는다.

사진은 사용자가 제공한 `딸기케익.jpg`, 글꼴은 Google Fonts의 Gowun Dodum/Noto Sans KR을 사용한다. 사진의 공개 배포 권한은 별도로 확인하지 않았다. 제출물은 과제 코드와 검증 증빙을 묶은 것이다.
