import unittest
from unittest.mock import Mock, patch

from test_showtimes import response, row, sites


def lotte_page():
    return {'IsOK': 'true', 'CinemaDivison': {'AreaDivisions': {'Items': [
        {'DetailDivisionCode': '0101', 'GroupNameKR': '경남/부산/울산'}, {'DetailDivisionCode': '0001', 'GroupNameKR': '서울'}]}},
        'Cinemas': {'Cinemas': {'Items': [
            {'DivisionCode': 1, 'DetailDivisionCode': '0101', 'CinemaID': 2004, 'CinemaNameKR': '부산본점'},
            {'DivisionCode': 2, 'DetailDivisionCode': '0986', 'CinemaID': 2004, 'CinemaNameKR': '부산본점'},
            {'DivisionCode': 1, 'DetailDivisionCode': '0001', 'CinemaID': 1004, 'CinemaNameKR': '건대입구'}]}},
        'Movies': {'Movies': {'Items': [{'RepresentationMovieCode': '25121', 'MovieNameKR': '폭설'}]}}}


def lotte_row(**changes):
    return {'CinemaID': 2004, 'CinemaNameKR': '부산본점', 'RepresentationMovieCode': '25121', 'MovieNameKR': '폭설',
            'PlayDt': '2026-11-21', 'ScreenID': 200407, 'PlaySequence': 0, 'StartTime': '18:00', 'EndTime': '19:39',
            'ScreenNameKR': '7관', 'FilmNameKR': '2D', 'TotalSeatCount': 100, 'BookingSeatCount': 3, 'IsBookingYN': 'Y', **changes}


def mega_page(rows=None):
    return {'statCd': 0, 'areaBrchList': [{'areaCd': '55', 'areaCdNm': '부산/대구/경상', 'brchNo': '0082', 'brchNm': '서면대한'}],
            'movieList': [{'movieNo': '26070000', 'movieNm': '폭설'}], 'movieFormList': [] if rows is None else rows}


def mega_row(**changes):
    return {'playDe': '20261121', 'brchNo': '0082', 'brchNm': '서면대한', 'playSchdlNo': '2611210082029',
            'movieNo': '26070001', 'rpstMovieNo': '26070000', 'movieNm': '폭설', 'rpstMovieNm': '폭설',
            'theabNo': '04', 'theabExpoNm': '리클라이너 4관', 'playKindNm': '2D&#40;자막&#41;',
            'playStartTime': '18:10', 'playEndTime': '19:48', 'restSeatCnt': 5, 'totSeatCnt': 81,
            'bokdAbleAt': 'Y', 'brchBokdUnableAt': 'N', **changes}


def http(body, status=200):
    result = Mock(status_code=status)
    result.json.return_value = body
    return result


class OtherCinemaTests(unittest.TestCase):
    def search(self, brand, replies, **changes):
        from app.cinema_providers import get_lotte_showtimes, get_megabox_showtimes
        function = get_lotte_showtimes if brand == 'lotte' else get_megabox_showtimes
        with patch('app.cinema_providers.requests.post', side_effect=[http(x) for x in replies]) as request:
            result = function(region='부산 서면', movie_nm='폭설', watch_date='2026-11-21', start_time='18:00', **changes)
        return result, request

    def test_lotte_seomyeon_alias_remaining_not_booked_and_zero_sequence(self):
        result, request = self.search('lotte', [lotte_page(), {'IsOK': 'true', 'PlaySeqs': {'Items': [lotte_row()]}}])
        self.assertTrue(result['ok'], result)
        item = result['data']['items'][0]
        self.assertEqual(item['remaining_seats'], 3)
        self.assertEqual(item['brand'], 'lotte')
        self.assertEqual(item['cinema'], '롯데시네마 부산본점')
        self.assertEqual(request.call_count, 2)

    def test_megabox_exact_movie_html_entities_and_real_remaining(self):
        result, _ = self.search('megabox', [mega_page(), mega_page([mega_row(), mega_row(movieNm='다른 영화', rpstMovieNm='다른 영화')])])
        self.assertTrue(result['ok'], result)
        items = result['data']['items']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['remaining_seats'], 5)
        self.assertEqual(items[0]['format'], '2D(자막)')
        self.assertEqual(items[0]['brand'], 'megabox')

    def test_missing_seats_and_sold_out_not_invented(self):
        for value, expected in [(None, 'unknown'), (0, 'sold_out')]:
            for brand, page, rows in [('lotte', lotte_page(), {'IsOK': 'true', 'PlaySeqs': {'Items': [lotte_row(BookingSeatCount=value)]}}),
                                      ('megabox', mega_page(), mega_page([mega_row(restSeatCnt=value)]))]:
                with self.subTest(value=value, brand=brand):
                    result, _ = self.search(brand, [page, rows])
                    self.assertEqual(result['data']['items'][0]['remaining_seats'], value)
                    self.assertEqual(result['data']['items'][0]['availability'], expected)

    def test_wrong_day_or_theater_is_not_published(self):
        for brand, page, rows in [('lotte', lotte_page(), {'IsOK': 'true', 'PlaySeqs': {'Items': [lotte_row(CinemaID=9999)]}}),
                                  ('megabox', mega_page(), mega_page([mega_row(playDe='20261120')]))]:
            result, _ = self.search(brand, [page, rows])
            self.assertFalse(result['ok'])

    def test_malformed_and_declined_json_are_not_empty_successes(self):
        for brand, bad in [('lotte', {'IsOK': 'false', 'ResultMessage': 'sensitive'}), ('megabox', {'statCd': -1, 'msg': 'sensitive'}),
                           ('lotte', {'IsOK': 'true'}), ('megabox', {'statCd': 0})]:
            result, _ = self.search(brand, [bad])
            self.assertFalse(result['ok'])
            self.assertNotIn('sensitive', str(result))

    def test_lotte_extended_midnight_and_closed_status(self):
        result, _ = self.search('lotte', [lotte_page(), {'IsOK': 'true', 'PlaySeqs': {'Items': [lotte_row(StartTime='24:00', EndTime='25:39', IsBookingYN='N')]}}])
        item = result['data']['items'][0]
        self.assertEqual(item['start_label'], '익일 00:00')
        self.assertEqual(item['watch_date'], '2026-11-22')
        self.assertEqual(item['availability'], 'unavailable')


class MultiCinemaTests(unittest.TestCase):
    def test_default_three_providers_and_brand_status(self):
        from app.showtime_search import search_showtimes
        from app.showtimes import get_showtimes
        with patch('app.showtimes.requests.get', side_effect=[sites(), response([row()]), response([])]):
            data = get_showtimes(region='부산 서면', movie_nm='폭설', watch_date='2026-11-21', start_time='18:00')
        providers = {name: (label, Mock(return_value=data), url) for name, label, url in [
            ('cgv', 'CGV', 'https://cgv.co.kr'), ('lotte', '롯데시네마', 'https://www.lottecinema.co.kr'), ('megabox', '메가박스', 'https://www.megabox.co.kr')]}
        with patch.dict('app.showtime_search.PROVIDERS', providers, clear=True):
            result = search_showtimes(region='부산 서면', movie_nm='폭설', watch_date='2026-11-21', start_time='18:00')
        self.assertTrue(result['ok'], result)
        self.assertEqual(len(result['data']['items']), 3)
        self.assertEqual(len({x['schedule_id'] for x in result['data']['items']}), 3)
        self.assertEqual(len(result['data']['providers']), 3)
        for _, function, _ in providers.values():
            self.assertEqual(function.call_count, 1)

    def test_partial_provider_failure_does_not_hide_success(self):
        from app.showtime_search import search_showtimes
        from app.showtimes import ShowtimesData, KST
        from datetime import datetime
        success = {'ok': True, 'data': ShowtimesData(items=[], checked_at=datetime.now(KST), checked_theaters=['CGV 서면'], complete=True, warnings=[]).model_dump(mode='json')}
        failure = {'ok': False, 'error': {'code': 'ACCESS_DENIED', 'message': '접근 제한'}}
        providers = {'cgv': ('CGV', Mock(return_value=success), 'https://cgv.co.kr'), 'lotte': ('롯데시네마', Mock(return_value=failure), 'https://www.lottecinema.co.kr')}
        with patch.dict('app.showtime_search.PROVIDERS', providers, clear=True):
            result = search_showtimes(region='서면', movie_nm='폭설', watch_date='2026-11-21', brands=['cgv', 'lotte'])
        self.assertTrue(result['ok'])
        self.assertFalse(result['data']['complete'])
        self.assertIn('롯데시네마', result['data']['warnings'][0])
        self.assertEqual(result['data']['providers'][1]['status'], 'error')

    def test_explicit_brand_selection_and_unknown_brand_rejected(self):
        from app.showtime_search import search_showtimes
        function = Mock(return_value={'ok': False, 'error': {'code': 'NOT_FOUND', 'message': '지점 없음'}})
        with patch.dict('app.showtime_search.PROVIDERS', {'lotte': ('롯데시네마', function, 'https://www.lottecinema.co.kr')}, clear=True):
            search_showtimes(region='서면', movie_nm='폭설', watch_date='2026-11-21', brands=['lotte'])
            self.assertEqual(function.call_count, 1)
            result = search_showtimes(region='서면', movie_nm='폭설', watch_date='2026-11-21', brands=['invalid'])
            self.assertFalse(result['ok'])
            self.assertEqual(function.call_count, 1)

    def test_natural_language_brand_selection_does_not_become_region(self):
        from app.showtime_request import parse_showtime_request
        result = parse_showtime_request('내일 오후 6시 이후에 부산 서면 롯데시네마에서 <폭설> 보고 싶어', {})
        self.assertEqual(result['conditions']['brands'], ['lotte'])
        self.assertEqual(result['conditions']['region'], '부산 서면')

    def test_multiple_brands_do_not_leave_conjunction_in_region(self):
        from app.showtime_request import parse_showtime_request
        result = parse_showtime_request('내일 오후 6시 이후에 부산 서면 CGV와 롯데시네마에서 <폭설> 보고 싶어', {})
        self.assertEqual(result['conditions']['brands'], ['cgv', 'lotte'])
        self.assertEqual(result['conditions']['region'], '부산 서면')

    def test_brand_followup_can_add_or_reset_all(self):
        from app.showtime_request import parse_showtime_request
        memory = {'intent': 'showtimes', 'conditions': {'brands': ['cgv']}}
        result = parse_showtime_request('롯데시네마도 같이 찾아줘', memory)
        self.assertEqual(result['conditions']['brands'], ['cgv', 'lotte'])
        result = parse_showtime_request('CGV 포함해서 3사 모두 찾아줘', memory)
        self.assertEqual(result['conditions']['brands'], ['cgv', 'lotte', 'megabox'])

    def test_explicit_only_and_unquoted_title_preserve_brand_choice(self):
        from app.showtime_request import parse_showtime_request
        result = parse_showtime_request('내일 오후 6시 이후에 부산 서면 롯데시네마에서 폭설이라는 영화를 보고싶어', {})
        self.assertEqual(result['conditions']['brands'], ['lotte'])
        self.assertEqual(result['conditions']['movie_nm'], '폭설')
        result = parse_showtime_request('메가박스만 보여줘', {'intent':'showtimes', 'conditions':{'brands':['cgv','lotte']}})
        self.assertEqual(result['conditions']['brands'], ['megabox'])
