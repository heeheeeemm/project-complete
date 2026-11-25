"""
관통 프로젝트로 가는 다리 : 회사명 하나로 전체 파이프라인 실행하기

학습 목표
  1. 단계별로 만든 함수를 모듈(파일)로 나누고, import 해서 조립한다
  2. if __name__ == '__main__' 이 왜 필요한지 이해한다
  3. run_pipeline() 한 줄이 웹 서비스의 View 안으로 들어가는 구조를 그려 본다

지금까지의 실습 파일은 "직접 실행"하는 파일이었습니다
  - 01_filter_bad_comments.py 처럼 파일 이름이 숫자로 시작하면 import 할 수 없습니다
  - 그래서 같은 함수(수집, LLM 호출)를 파일마다 복사해서 써 왔습니다
  => 06_pipeline 폴더에서는 역할별로 파일을 나누고, 필요한 함수를 import 해서 씁니다

모듈 구성 (06_pipeline 폴더, 모두 완성된 파일이니 열어서 읽어 보세요)
  crawler.py     : fetch_comments()                       수집
  llm.py         : run_llm(), parse_json_array()           LLM 호출 (공통)
  preprocess.py  : filter_inappropriate(), clean_comments() 전처리
  augment.py     : augment_comments(), merge_with_source() 증강
  run_pipeline.py: run_pipeline()                          조립 (이 파일)

관통 프로젝트에서는
  [회사명 입력 폼] => View 에서 run_pipeline(company) 호출 => 결과를 화면(템플릿) 또는 JSON 으로 응답

진행 방법
  - [STEP 1]부터 순서대로 코드 블록을 선택하고 Ctrl + / 로 주석을 해제합니다
  - 실행하면 터미널에서 회사명을 입력받습니다. Enter 만 누르면 삼성전자로 진행합니다
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from augment import augment_comments, merge_with_source
from crawler import fetch_company_data
from llm import run_llm
from preprocess import CRITERIA, clean_comments_with_stats, filter_inappropriate

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / 'data'


def save_json(data, file_path):
    """data 를 JSON 파일로 저장한다"""
    file_path.parent.mkdir(exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'[저장] {file_path.name}')


# ------------------------------------------------------------
# [STEP 1] 파이프라인 함수 : 회사명 => 결과 딕셔너리
# ------------------------------------------------------------
# import : 다른 파일(모듈)에 있는 함수를 가져와 이 파일에서 쓰기
#   from crawler import fetch_comments
#   => crawler.py 파일 안의 fetch_comments 함수를 가져옵니다 (파일 이름에서 .py 는 빼고 씀)
#   => 같은 폴더에 있는 파일이라 경로 없이 이름만 적으면 됩니다
#
# 이때 crawler.py 맨 아래의 if __name__ == '__main__': 부분은 실행되지 않습니다
#   - 파일을 "직접 실행"하면  __name__ == '__main__'   => 아래 코드 실행 (테스트용 수집)
#   - 다른 파일이 "import"하면 __name__ == 'crawler'    => 실행 안 함 (함수만 가져감)
#   => 이 구분이 없으면 import 하는 순간 크롬이 열리고 크롤링이 시작됩니다
#
# run_pipeline(company)
#   - 지금까지 파일마다 나눠서 실행한 4단계를 함수 하나로 이어 붙였습니다
#     수집 => 부적절 제거 => 정제 => 증강
#   - 댓글이 없으면(없는 회사명 등) 뒤 단계를 건너뛰고 안내 메시지만 돌려줍니다
#   - 결과를 딕셔너리 하나로 돌려주는 이유 : 웹 화면(템플릿)이나 JSON 응답에 그대로 넘기기 쉽기 때문
#
# headless 매개변수
#   - 웹 서비스 안에서 실행할 때는 화면에 크롬 창을 띄울 수 없으므로 True 로 실행합니다
#   - 수업에서는 진행 과정을 눈으로 보기 위해 기본값 False 로 둡니다

def summarize_comments(comments):
    """심화 요구사항 F610: 전체 댓글의 주요 내용을 짧게 요약한다."""
    if not comments:
        return ''
    numbered = '\n'.join(f'- {comment}' for comment in comments)
    return run_llm(
        '다음 주식 커뮤니티 댓글의 주요 의견과 분위기를 3문장 이내로 '
        f'객관적으로 요약해줘.\n\n{numbered}'
    ).strip()


def run_pipeline(company, limit=20, criteria_name='strict', headless=True, summarize=False):
    """수집 => 부적절 제거 => 정제 => 증강을 실행하고 각 단계 결과를 돌려준다."""
    company = company.strip()
    if not company:
        return {'company': '', 'message': '회사명을 입력해주세요.', 'counts': {}, 'records': []}
    if criteria_name not in CRITERIA:
        criteria_name = 'strict'

    print(f'===== [{company}] 파이프라인 시작 =====')
    started_at = time.perf_counter()
    crawled = fetch_company_data(company, limit=limit, headless=headless)
    comments = crawled['comments']
    print(f'[시간] 크롤링 {time.perf_counter() - started_at:.1f}초')
    if not comments:
        return {
            'company': company,
            'actual_company': crawled['actual_company'],
            'message': f'{company} 검색 결과 또는 댓글을 찾지 못했습니다.',
            'counts': {'collected': 0},
            'raw_comments': [], 'cleaned_comments': [], 'augmented_comments': [],
            'records': [],
        }

    # 요약은 원본 댓글만 필요하므로 전처리·증강과 동시에 실행할 수 있다.
    with ThreadPoolExecutor(max_workers=2) as executor:
        summary_future = (
            executor.submit(summarize_comments, comments) if summarize else None
        )

        stage_started_at = time.perf_counter()
        kept, removed = filter_inappropriate(comments, CRITERIA[criteria_name])
        print(f'[시간] 부적절 필터 {time.perf_counter() - stage_started_at:.1f}초')

        cleaned, iqr = clean_comments_with_stats(kept)

        stage_started_at = time.perf_counter()
        augmented = augment_comments(cleaned) if cleaned else []
        print(f'[시간] 데이터 증강 {time.perf_counter() - stage_started_at:.1f}초')

        summary = summary_future.result() if summary_future else ''

    print(f'[시간] 전체 {time.perf_counter() - started_at:.1f}초')

    return {
        'company': company,
        'actual_company': crawled['actual_company'] or company,
        'stock_code': crawled['stock_code'],
        'message': '',
        'collected_at': datetime.now().isoformat(timespec='seconds'),
        'criteria': CRITERIA[criteria_name],
        'iqr': iqr,
        'counts': {
            'collected': len(comments), 'filtered': len(kept),
            'cleaned': len(cleaned), 'augmented': len(augmented),
        },
        'raw_comments': comments,
        'cleaned_comments': cleaned,
        'augmented_comments': augmented,
        'removed': removed,
        'summary': summary,
        'records': merge_with_source(cleaned, augmented),
    }


# ------------------------------------------------------------
# [STEP 2] 사용자 입력으로 실행하기
# ------------------------------------------------------------
# input('안내 문구') : 터미널에서 사용자가 입력한 글자를 받아 옵니다
#   .strip() or '삼성전자' : 아무것도 입력하지 않으면('' 은 False) 삼성전자를 사용
#
# 관통 프로젝트에서는 이 input() 자리가 "웹 페이지의 입력 폼"으로 바뀝니다
#   터미널 : company = input(...)              => result = run_pipeline(company) => print
#   웹     : company = request.GET['company']  => result = run_pipeline(company) => 화면에 표시
#   => run_pipeline 은 그대로 두고, 입력을 받는 곳과 결과를 보여 주는 곳만 바뀝니다
#
# 확인 포인트
#   - 단계마다 댓글 수(collected => filtered => cleaned => augmented)가 어떻게 변했나요?
#   - 없는 회사명(예: 'ㅁㄴㅇㄹ')을 입력하면 어떻게 되나요?
#   - 회사명 하나를 처리하는 데 시간이 얼마나 걸렸나요?
#     웹 서비스라면 사용자는 그동안 무엇을 보고 있어야 할까요? (로딩 화면이 필요한 이유)

if __name__ == '__main__':
    company = input('회사명을 입력하세요: ').strip()
    if company:
        result = run_pipeline(company, headless=False)
        if result['message']:
            print(result['message'])
        else:
            print(f'\n===== [{result["actual_company"]}] 결과 =====')
            for step, count in result['counts'].items():
                print(f'  {step:<10}: {count}개')
            save_json(result, DATA_DIR / 'pipeline_result.json')
