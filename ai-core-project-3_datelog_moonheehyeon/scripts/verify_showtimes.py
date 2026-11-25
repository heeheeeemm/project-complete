"""CGV·롯데시네마·메가박스 실제 시간표·잔여석 점검. LLM/API 키 없이 실행한다.

python -m scripts.verify_showtimes --region "부산 서면" --movie "폭설"
"""
import argparse
import sys
from datetime import datetime, timedelta

from app.showtimes import KST
from tools_start import TOOLS


def main():
    parser = argparse.ArgumentParser(description='Read-only live CGV showtime verification')
    parser.add_argument('--region', default='부산 서면')
    parser.add_argument('--movie', default='폭설')
    parser.add_argument('--date', default=(datetime.now(KST).date() + timedelta(days=1)).isoformat())
    parser.add_argument('--after', default='18:00')
    parser.add_argument('--brands', nargs='+', choices=['cgv', 'lotte', 'megabox'], default=['cgv', 'lotte', 'megabox'])
    args = parser.parse_args()
    result = TOOLS['get_showtimes'].run(region=args.region, movie_nm=args.movie, watch_date=args.date, start_time=args.after, brands=args.brands)
    if not result['ok']:
        print(f"Cinema showtimes: FAILED ({result['error']['code']}) {result['error']['message']}")
        return 1
    data = result['data']
    print(f"Cinema showtimes: {'OK' if data['complete'] else 'PARTIAL'} ({len(data['items'])} showtimes)")
    for provider in data['providers']:
        print(provider['label'] + ': ' + provider['status'] + ' (' + str(provider['count']) + ')')
    print('Checked: ' + data['checked_at'])
    print('Theaters: ' + ', '.join(data['checked_theaters']))
    for item in data['items']:
        seats = '?' if item['remaining_seats'] is None else str(item['remaining_seats'])
        print(f"{item['cinema']} | {item['start_label']} - {item['end_label']} | {item['screen']} | remaining={seats} | {item['availability']}")
    for warning in data['warnings']:
        print('WARNING: ' + warning)
    return 0 if data['complete'] else 1


if __name__ == '__main__':
    sys.exit(main())
