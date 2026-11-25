# Tool 정의서

공통 성공 `{ok:true,data:{...}}`, 실패 `{ok:false,error:{code,message}}`. 모든 Tool은 외부 API Tool이다. 전체 입출력 JSON Schema는 [tool-catalog.json](tool-catalog.json)에 코드에서 생성했다.

## search_movies

불완전한 영화 제목이나 출연자 이름으로 KOBIS 영화 목록·필모그래피를 검색해 사용자에게 확인할 후보를 찾는다.

입력:

```json

{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "minLength": 1,
      "maxLength": 100
    }
  },
  "required": [
    "query"
  ],
  "additionalProperties": false
}

```

성공/실패 출력: tool-catalog.json의 `search_movies.output_schema`.

## search_places

선택한 영화관·식당 또는 기억한 지역 주변의 실제 식당/카페를 카카오에서 검색한다. 평점·영업시간·가격을 생성하지 않는다.

입력:

```json

{
  "type": "object",
  "properties": {
    "region": {
      "type": "string"
    },
    "kind": {
      "enum": [
        "restaurant",
        "cafe",
        "place"
      ]
    },
    "cuisine": {
      "type": [
        "string",
        "null"
      ]
    },
    "anchor_name": {
      "type": [
        "string",
        "null"
      ]
    },
    "lat": {
      "type": [
        "number",
        "null"
      ]
    },
    "lng": {
      "type": [
        "number",
        "null"
      ]
    }
  },
  "required": [
    "region",
    "kind"
  ],
  "additionalProperties": false
}

```

성공/실패 출력: tool-catalog.json의 `search_places.output_schema`.

## get_boxoffice

후보를 정하지 않았거나 대안 영화가 필요할 때 일별 순위와 영화코드를 조회한다.

입력:

```json

{
  "type": "object",
  "properties": {
    "target_date": {
      "type": [
        "string",
        "null"
      ],
      "description": "YYYY-MM-DD. 생략하면 한국시간 어제. 미래는 어제로 보정."
    }
  },
  "additionalProperties": false
}

```

성공/실패 출력: tool-catalog.json의 `get_boxoffice.output_schema`.

## get_movie_detail

후보 영화코드의 러닝타임·장르·등급으로 조건을 판단할 때 조회한다.

입력:

```json

{
  "type": "object",
  "properties": {
    "movie_cd": {
      "type": "string",
      "pattern": "^\\d{8}$"
    }
  },
  "required": [
    "movie_cd"
  ],
  "additionalProperties": false
}

```

성공/실패 출력: tool-catalog.json의 `get_movie_detail.output_schema`.

## search_cinemas

사용자가 지정한 지역의 영화관 이름·주소·링크가 필요할 때 검색한다. 시간표는 제공하지 않는다.

입력:

```json

{
  "type": "object",
  "properties": {
    "region": {
      "type": "string",
      "minLength": 1,
      "maxLength": 100
    }
  },
  "required": [
    "region"
  ],
  "additionalProperties": false
}

```

성공/실패 출력: tool-catalog.json의 `search_cinemas.output_schema`.

## get_showtimes

영화명·지역·날짜의 실제 CGV·롯데시네마·메가박스 회차와 잔여석을 통합 조회한다. KOBIS 영화코드는 사용하지 않는다.

입력:

```json

{
  "type": "object",
  "properties": {
    "region": {
      "type": "string"
    },
    "movie_nm": {
      "type": "string"
    },
    "watch_date": {
      "type": "string",
      "description": "YYYY-MM-DD"
    },
    "start_time": {
      "type": "string",
      "description": "HH:MM, 이 시각 포함 이후"
    },
    "deadline": {
      "type": [
        "string",
        "null"
      ]
    },
    "deadline_inclusive": {
      "type": "boolean",
      "description": "까지=true, 전에/이전=false"
    },
    "buffer_minutes": {
      "type": "integer",
      "minimum": 0,
      "maximum": 240
    },
    "brands": {
      "type": "array",
      "items": {
        "enum": [
          "cgv",
          "lotte",
          "megabox"
        ]
      },
      "minItems": 1,
      "maxItems": 3
    }
  },
  "required": [
    "region",
    "movie_nm",
    "watch_date"
  ],
  "additionalProperties": false
}

```

성공/실패 출력: tool-catalog.json의 `get_showtimes.output_schema`.

## 실패 처리

BAD_ARGUMENT 입력 형식/누락, INVALID_KEY 인증/권한·키 누락, NO_DATA/NOT_FOUND 결과 없음, NO_RUNTIME 러닝타임 없음, TIMEOUT/CONNECTION_ERROR/ACCESS_DENIED/UPSTREAM_ERROR 외부 오류를 공통 구조로 반환한다. 실제 허용 코드는 각 출력 스키마와 공급자 구현을 따른다. 0석과 좌석 미확인은 구분하고 미확인 종료·러닝타임은 계산 근거로 쓰지 않는다. 개별 영화/브랜드 실패는 다른 성공 결과를 유지한다. 원문 오류·인증 URL은 반환하지 않는다.

## 등록/확장

함수와 입력 JSON Schema, 설명/사용 시점, Pydantic 성공 data 모델을 만든 후 `Tool(name,description,parameters,fn,Model)`을 TOOLS에 등록한다. catalog()가 실패를 포함한 출력 스키마를 노출한다. Agent의 허용 tool_names와 의존 인자 연결을 추가하고 정상/잘못된 인자/키 누락/응답 계약/부분 실패를 검증한다. 기존 ok/fail/Tool.run 공통 구조를 유지한다.
