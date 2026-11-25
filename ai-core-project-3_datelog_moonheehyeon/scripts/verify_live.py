"""실제 외부 API/LLM 연동 점검. 키·요청 URL·외부 오류 원문은 출력하지 않는다.

실행: venv/Scripts/python.exe -m scripts.verify_live
"""
import os
import sys

from app.llm import AgentConfigurationError, analyze_request
from tools_start import TOOLS


def main():
    names = ['KOBIS_API_KEY', 'KAKAO_REST_API_KEY', 'OPENAI_API_KEY', 'OPENAI_MODEL']
    missing = [name for name in names if not os.getenv(name, '').strip()]
    if missing:
        print('Missing configuration: ' + ', '.join(missing))
        return 1

    boxoffice = TOOLS['get_boxoffice'].run()
    items = boxoffice.get('data', {}).get('items', [])
    # 후보 조회가 실패해도 상세 API 자체의 접근 가능 여부는 별도 확인한다.
    movie_cd = items[0]['movie_cd'] if items else '20124079'
    results = {
        'KOBIS boxoffice': boxoffice,
        'KOBIS movie detail': TOOLS['get_movie_detail'].run(movie_cd=movie_cd),
        'Kakao cinema search': TOOLS['search_cinemas'].run(region='강남'),
    }
    passed = True
    for label, result in results.items():
        if result['ok']:
            print(label + ': OK')
        else:
            passed = False
            print(label + ': FAILED (' + result['error']['code'] + ') ' + result['error']['message'])
    try:
        analysis = analyze_request('안녕, 사용법을 알려 줘', {})
        if analysis['intent'] != 'help' or analysis.get('tool_names'):
            passed = False
            print('LLM analysis: FAILED (unexpected greeting analysis)')
        else:
            print('LLM analysis: OK (valid structured response)')
    except AgentConfigurationError as error:
        passed = False
        print('LLM analysis: FAILED (' + error.code + ') ' + str(error))

    print('All live integrations passed.' if passed else 'Live integration verification did not pass.')
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
