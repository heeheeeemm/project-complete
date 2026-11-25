from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.test import override_settings
from unittest.mock import patch
from urllib.error import URLError
import json

from .models import Book


@override_settings(GMS_API_KEY='')
class BookTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='reader', password='Book-test-pass-42')
        cls.book = Book.objects.create(title='도서', description='설명', rating=8, author='저자')

    def test_public_pages_and_hidden_mutation_links(self):
        response = self.client.get(reverse('books:index'))
        self.assertContains(response, self.book.title)
        self.assertNotContains(response, reverse('books:create'))
        response = self.client.get(reverse('books:detail', args=[self.book.pk]))
        for value in ['도서', '설명', '저자', '8 / 10']:
            self.assertContains(response, value)
        self.assertNotContains(response, reverse('books:update', args=[self.book.pk]))

    def test_mutations_require_login(self):
        for name, args in [('create', []), ('update', [self.book.pk]), ('delete', [self.book.pk])]:
            response = self.client.post(reverse('books:' + name, args=args), {})
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith(reverse('accounts:login')))
        self.assertEqual(Book.objects.count(), 1)

    def test_create_update_and_delete(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('books:create'), {
            'title': '새 도서', 'description': '새 설명', 'rating': 10, 'author': '작가',
        })
        book = Book.objects.get(title='새 도서')
        self.assertRedirects(response, reverse('books:detail', args=[book.pk]))
        response = self.client.get(reverse('books:update', args=[book.pk]))
        self.assertContains(response, '새 설명')
        response = self.client.post(reverse('books:update', args=[book.pk]), {
            'title': '수정 도서', 'description': '수정 설명', 'rating': 7, 'author': '작가2',
        })
        self.assertRedirects(response, reverse('books:detail', args=[book.pk]))
        book.refresh_from_db()
        self.assertEqual((book.title, book.rating, book.author), ('수정 도서', 7, '작가2'))
        self.assertRedirects(self.client.post(reverse('books:delete', args=[book.pk])), reverse('books:index'))
        self.assertFalse(Book.objects.filter(pk=book.pk).exists())

    def test_invalid_data_is_not_saved(self):
        self.client.force_login(self.user)
        for rating in [-1, 11, 'invalid']:
            response = self.client.post(reverse('books:create'), {
                'title': '거절 도서', 'description': '설명', 'rating': rating, 'author': '저자',
            })
            self.assertEqual(response.status_code, 200)
            self.assertIn('rating', response.context['form'].errors)
        response = self.client.post(reverse('books:update', args=[self.book.pk]), {})
        self.assertEqual(response.status_code, 200)
        self.book.refresh_from_db()
        self.assertEqual(self.book.title, '도서')
        self.assertEqual(Book.objects.count(), 1)

    def test_http_methods_and_missing_book(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('books:delete', args=[self.book.pk])).status_code, 405)
        self.assertEqual(self.client.post(reverse('books:index')).status_code, 405)
        self.assertEqual(self.client.post(reverse('books:detail', args=[self.book.pk])).status_code, 405)
        self.assertEqual(self.client.put(reverse('books:create')).status_code, 405)
        self.assertEqual(self.client.get(reverse('books:detail', args=[99999])).status_code, 404)

    @patch('books.views._try_author_info')
    def test_genre_is_saved_edited_and_displayed(self, generate_info):
        self.client.force_login(self.user)
        values = {'title': '장르 테스트 도서', 'author': '작가', 'description': '설명', 'rating': 8, 'genre': 'NOVEL'}
        response = self.client.post(reverse('books:create'), values)
        book = Book.objects.get(title=values['title'])
        self.assertEqual(book.genre, 'NOVEL')
        self.assertRedirects(response, reverse('books:detail', args=[book.pk]))
        self.assertContains(self.client.get(reverse('books:detail', args=[book.pk])), '소설')
        response = self.client.get(reverse('books:update', args=[book.pk]))
        self.assertEqual(response.context['form']['genre'].value(), 'NOVEL')
        values['genre'] = 'SCIENCE'
        self.client.post(reverse('books:update', args=[book.pk]), values)
        book.refresh_from_db()
        self.assertEqual(book.genre, 'SCIENCE')
        self.assertContains(self.client.get(reverse('books:detail', args=[book.pk])), '과학')
        values['genre'] = 'NOT_A_GENRE'
        response = self.client.post(reverse('books:update', args=[book.pk]), values)
        self.assertIn('genre', response.context['form'].errors)
        book.refresh_from_db()
        self.assertEqual(book.genre, 'SCIENCE')

    def test_genre_filter_and_all_books(self):
        novel = Book.objects.create(title='소설 필터 도서', description='설명', author='작가', genre='NOVEL')
        science = Book.objects.create(title='과학 필터 도서', description='설명', author='작가', genre='SCIENCE')
        url = reverse('books:index')
        response = self.client.get(url)
        self.assertEqual(set(response.context['books'].values_list('pk', flat=True)), {self.book.pk, novel.pk, science.pk})
        response = self.client.get(url, {'genre': 'NOVEL'})
        self.assertEqual(list(response.context['books']), [novel])
        self.assertEqual(response.context['selected_genre'], 'NOVEL')
        self.assertContains(response, '1권')
        self.assertContains(response, novel.title)
        self.assertNotContains(response, science.title)
        response = self.client.get(url, {'genre': 'UNCLASSIFIED'})
        self.assertEqual(list(response.context['books']), [self.book])
        response = self.client.get(url, {'genre': 'POETRY'})
        self.assertContains(response, '이 장르의 책은 아직 없어요.')
        self.assertContains(response, '0권')
        response = self.client.get(url, {'genre': 'INVALID'})
        self.assertEqual(response.context['selected_genre'], '')
        self.assertEqual(response.context['books'].count(), 3)

    @patch('books.views._try_author_info')
    def test_subgenre_is_saved_and_parent_change_clears_selection(self, generate_info):
        self.client.force_login(self.user)
        values = {
            'title': '세부 장르 도서', 'author': '작가', 'description': '설명',
            'rating': 8, 'genre': 'NOVEL', 'subgenre': 'NOVEL_FANTASY',
        }
        self.client.post(reverse('books:create'), values)
        book = Book.objects.get(title=values['title'])
        self.assertEqual(book.subgenre, 'NOVEL_FANTASY')
        self.assertContains(self.client.get(reverse('books:detail', args=[book.pk])), '판타지')
        response = self.client.get(reverse('books:update', args=[book.pk]))
        self.assertEqual(response.context['form']['subgenre'].value(), 'NOVEL_FANTASY')
        self.assertIn(('NOVEL_MYSTERY', '추리·미스터리'), response.context['form'].fields['subgenre'].choices)
        self.assertNotIn(('SCIENCE_PHYSICS', '물리·천문'), response.context['form'].fields['subgenre'].choices)
        values.update(genre='SCIENCE', subgenre='NOVEL_FANTASY')
        response = self.client.post(reverse('books:update', args=[book.pk]), values)
        self.assertIn('subgenre', response.context['form'].errors)
        book.refresh_from_db()
        self.assertEqual(book.genre, 'NOVEL')
        values.update(subgenre='SCIENCE_PHYSICS')
        self.client.post(reverse('books:update', args=[book.pk]), values)
        book.refresh_from_db()
        self.assertEqual((book.genre, book.subgenre), ('SCIENCE', 'SCIENCE_PHYSICS'))
        values.update(genre='NOVEL', subgenre='')
        self.client.post(reverse('books:update', args=[book.pk]), values)
        book.refresh_from_db()
        self.assertEqual(book.subgenre, '')

    def test_subgenre_filter_and_invalid_parent_combinations(self):
        fantasy = Book.objects.create(title='판타지 도서', description='설명', author='작가', genre='NOVEL', subgenre='NOVEL_FANTASY')
        mystery = Book.objects.create(title='추리 도서', description='설명', author='작가', genre='NOVEL', subgenre='NOVEL_MYSTERY')
        general = Book.objects.create(title='일반 소설', description='설명', author='작가', genre='NOVEL')
        science = Book.objects.create(title='과학 도서', description='설명', author='작가', genre='SCIENCE', subgenre='SCIENCE_PHYSICS')
        url = reverse('books:index')
        response = self.client.get(url, {'genre': 'NOVEL', 'subgenre': 'NOVEL_FANTASY'})
        self.assertEqual(list(response.context['books']), [fantasy])
        self.assertEqual(response.context['selected_subgenre'], 'NOVEL_FANTASY')
        self.assertContains(response, '1권')
        self.assertNotContains(response, mystery.title)
        response = self.client.get(url, {'genre': 'NOVEL'})
        self.assertEqual(set(response.context['books'].values_list('pk', flat=True)), {fantasy.pk, mystery.pk, general.pk})
        response = self.client.get(url, {'genre': 'NOVEL', 'subgenre': 'SCIENCE_PHYSICS'})
        self.assertEqual(response.context['selected_subgenre'], '')
        self.assertEqual(response.context['books'].count(), 3)
        response = self.client.get(url, {'genre': 'SCIENCE', 'subgenre': 'SCIENCE_PHYSICS'})
        self.assertEqual(list(response.context['books']), [science])
        self.assertNotContains(response, '>추리·미스터리</a>')
        response = self.client.get(url, {'subgenre': 'NOVEL_FANTASY'})
        self.assertEqual(response.context['selected_genre'], 'NOVEL')
        self.assertEqual(list(response.context['books']), [fantasy])
        self.assertContains(response, '소설 / 판타지')
        response = self.client.get(url)
        self.assertContains(response, '세부 장르로 둘러보기')
        self.assertContains(response, '<optgroup label="소설">', html=False)

    def test_model_rejects_mismatched_subgenre(self):
        from django.core.exceptions import ValidationError

        book = Book(title='도서', description='설명', author='작가', genre='ART', subgenre='NOVEL_FANTASY')
        with self.assertRaises(ValidationError) as error:
            book.full_clean()
        self.assertIn('subgenre', error.exception.message_dict)


class BookCoverTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        domestic = patch('books.views._aladin_cover', return_value=None)
        self.domestic_cover = domestic.start()
        self.addCleanup(domestic.stop)
        stored = patch('books.views._stored_cover', return_value=None)
        stored.start()
        self.addCleanup(stored.stop)
        storage = patch('books.views._store_cover', side_effect=lambda key, result: result)
        storage.start()
        self.addCleanup(storage.stop)

    @patch('books.views._request_json')
    def test_domestic_cover_is_used_before_foreign_catalogs(self, request_json):
        self.domestic_cover.return_value = {
            'url': 'https://image.aladin.co.kr/product/4086/97/cover200/8936434128_2.jpg',
            'source': '알라딘', 'source_url': 'https://www.aladin.co.kr/shop/wproduct.aspx?ItemId=40869703',
        }
        response = self.client.get(reverse('books:cover_lookup'), {'title': '소년이 온다', 'author': '한강'})
        self.assertEqual(response.json()['source'], '알라딘')
        self.assertIn('image.aladin.co.kr', response.json()['url'])
        request_json.assert_not_called()

    def test_domestic_parser_keeps_book_results_separate(self):
        from .views import _AladinBooksParser, _cover_match

        parser = _AladinBooksParser()
        parser.feed('''<div class="ss_book_box"><div><img src="https://image.aladin.co.kr/product/1/cover200/one.jpg"></div>
        <a class="bo3" href="https://www.aladin.co.kr/shop/wproduct.aspx?ItemId=1"><b>다른 책</b></a><span>다른 작가</span></div>
        <div class="ss_book_box"><div><img src="https://image.aladin.co.kr/product/2/cover200/two.jpg"></div>
        <div><a class="bo3" href="https://www.aladin.co.kr/shop/wproduct.aspx?ItemId=2"><b>소년이 온다</b> - 한강 장편소설</a><span>한강 (지은이)</span></div></div>''')
        self.assertEqual(len(parser.books), 2)
        self.assertFalse(_cover_match('소년이 온다', '한강', parser.books[0]['title'], [parser.books[0]['text']]))
        self.assertTrue(_cover_match('소년이 온다', '한강', parser.books[1]['title'], [parser.books[1]['text']]))
        self.assertIn('two.jpg', parser.books[1]['image'])

    @patch('books.views._request_json')
    def test_cover_matches_title_author_and_uses_cached_result(self, request_json):
        request_json.return_value = {'docs': [
            {'title': '소년이 온다', 'author_name': ['다른 작가'], 'cover_i': 1},
            {'title': '소년이 온다', 'author_name': ['한강'], 'cover_i': 1234, 'key': '/works/OL123W'},
        ]}
        url = reverse('books:cover_lookup')
        response = self.client.get(url, {'title': '소년이 온다', 'author': '한강'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('/1234-L.jpg', response.json()['url'])
        self.assertEqual(response.json()['source_url'], 'https://openlibrary.org/works/OL123W')
        self.client.get(url, {'title': '소년이 온다', 'author': '한강'})
        self.assertEqual(request_json.call_count, 1)

    @patch('books.views._request_json')
    def test_korean_edition_cover_is_preferred(self, request_json):
        request_json.return_value = {'docs': [{
            'title': 'Human Acts', 'author_name': ['한강'], 'cover_i': 123,
            'editions': {'docs': [{'title': '소년이 온다', 'cover_i': 456}]},
        }]}
        response = self.client.get(reverse('books:cover_lookup'), {'title': '소년이 온다', 'author': '한강'})
        self.assertIn('/456-L.jpg', response.json()['url'])

    @patch('books.views._request_json')
    def test_google_fallback_upgrades_image_to_https(self, request_json):
        request_json.side_effect = [{'docs': []}, {'items': [{
            'id': 'book-id', 'volumeInfo': {'title': '소년이 온다', 'authors': ['한강'],
                'imageLinks': {'thumbnail': 'http://books.google.com/books/content?id=book-id'}},
        }]}]
        response = self.client.get(reverse('books:cover_lookup'), {'title': '소년이 온다', 'author': '한강'})
        self.assertEqual(response.json()['url'], 'https://books.google.com/books/content?id=book-id')

    @patch('books.views._request_json')
    def test_failures_and_wrong_books_fall_back_without_breaking_page(self, request_json):
        request_json.side_effect = URLError('offline')
        response = self.client.get(reverse('books:cover_lookup'), {'title': '소년이 온다', 'author': '한강'})
        self.assertEqual(response.json()['url'], '')
        request_json.side_effect = [{'docs': []}, {'items': [{'volumeInfo': {
            'title': '다른 책', 'authors': ['한강'], 'imageLinks': {'thumbnail': 'https://books.google.com/cover'}
        }}]}]
        response = self.client.get(reverse('books:cover_lookup'), {'title': '채식주의자', 'author': '한강'})
        self.assertEqual(response.json()['url'], '')

    @patch('books.views._request_json')
    def test_endpoint_validates_input_and_limits_methods(self, request_json):
        url = reverse('books:cover_lookup')
        self.assertEqual(self.client.get(url).status_code, 400)
        self.assertEqual(self.client.get(url, {'title': 'x' * 101}).status_code, 400)
        self.assertEqual(self.client.post(url).status_code, 405)
        request_json.assert_not_called()


@override_settings(GMS_API_KEY='test-key', GMS_MODEL='gpt-5-nano')
class AuthorInfoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='author-reader')
        cls.book = Book.objects.create(title='소년이 온다', description='장편소설', author='한강', rating=9)

    def setUp(self):
        self.client.force_login(self.user)

    @staticmethod
    def wiki_result():
        return {'query': {'pages': [{
            'title': '한강 (작가)', 'extract': '대한민국의 소설가.',
            'thumbnail': {'source': 'https://upload.wikimedia.org/portrait.jpg'},
            'fullurl': 'https://ko.wikipedia.org/wiki/한강_(작가)',
        }]}}

    @staticmethod
    def ai_result(info='대한민국의 소설가.', works=None):
        return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({
            'author_info': info, 'author_works': ['채식주의자'] if works is None else works,
        })}}]}

    @patch('books.views._request_json')
    def test_generation_queries_wikipedia_calls_nano_saves_and_displays(self, request_json):
        request_json.side_effect = [self.wiki_result(), self.ai_result()]
        response = self.client.post(reverse('books:author_info', args=[self.book.pk]))
        self.assertRedirects(response, reverse('books:detail', args=[self.book.pk]))
        self.book.refresh_from_db()
        self.assertEqual(self.book.author_works, ['채식주의자'])
        self.assertIn('wikipedia.org', self.book.author_source)
        self.assertIn('upload.wikimedia.org', self.book.author_image)
        calls = request_json.call_args_list
        self.assertIn('gsrsearch=', calls[0].args[0])
        payload = calls[1].args[1]
        self.assertEqual(payload['model'], 'gpt-5-nano')
        self.assertEqual(payload['response_format'], {'type': 'json_object'})
        self.assertIn('대한민국의 소설가', payload['messages'][1]['content'])
        response = self.client.get(reverse('books:detail', args=[self.book.pk]))
        self.assertContains(response, '채식주의자')
        self.assertContains(response, '작가 대표작과 작가 정보는 AI가 생성한 정보로, 정확하지 않을 수 있습니다.')

    @patch('books.views._request_json')
    def test_create_generates_info_and_author_change_replaces_it(self, request_json):
        request_json.side_effect = [self.wiki_result(), self.ai_result()]
        response = self.client.post(reverse('books:create'), {
            'title': '작별하지 않는다', 'description': '소설', 'rating': 8, 'author': '한강',
        })
        book = Book.objects.get(title='작별하지 않는다')
        self.assertRedirects(response, reverse('books:detail', args=[book.pk]))
        self.assertEqual(book.author_works, ['채식주의자'])
        request_json.side_effect = URLError('unavailable')
        self.client.post(reverse('books:update', args=[book.pk]), {
            'title': book.title, 'description': '다른 작가로 수정', 'rating': 7, 'author': '다른 작가',
        })
        book.refresh_from_db()
        self.assertEqual(book.author_info, '')
        self.assertEqual(book.author_works, [])
        self.assertEqual(book.author_image, '')

    @patch('books.views._request_json')
    def test_failed_regeneration_preserves_previous_data(self, request_json):
        self.book.author_info = '기존 소개'
        self.book.author_works = ['기존 대표작']
        self.book.save()
        for bad_response in [self.ai_result(works='wrong type'), {'choices': []}, self.ai_result(info='')]:
            request_json.side_effect = [self.wiki_result(), bad_response]
            response = self.client.post(reverse('books:author_info', args=[self.book.pk]), follow=True)
            self.assertContains(response, '작가 정보를 가져오지 못했습니다.')
            self.book.refresh_from_db()
            self.assertEqual(self.book.author_info, '기존 소개')
            self.assertEqual(self.book.author_works, ['기존 대표작'])

    @override_settings(GMS_API_KEY='')
    @patch('books.views._request_json')
    def test_no_key_keeps_book_and_does_not_make_network_request(self, request_json):
        response = self.client.post(reverse('books:create'), {
            'title': '키 없는 등록', 'description': '설명', 'rating': 5, 'author': '작가',
        }, follow=True)
        self.assertContains(response, '아직 생성된 작가 정보가 없습니다.')
        self.assertContains(response, '작가 정보 생성 서비스를 아직 사용할 수 없습니다.')
        self.assertTrue(Book.objects.filter(title='키 없는 등록').exists())
        request_json.assert_not_called()

    def test_generation_requires_login_and_post(self):
        self.assertEqual(self.client.get(reverse('books:author_info', args=[self.book.pk])).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.post(reverse('books:author_info', args=[self.book.pk])).status_code, 302)

    @patch('books.views._request_json')
    def test_wikipedia_english_fallback_and_missing_search_result(self, request_json):
        from .views import _wikipedia_author

        request_json.side_effect = [{}, self.wiki_result()]
        result = _wikipedia_author('author')
        self.assertTrue(result['extract'])
        self.assertIn('en.wikipedia.org', request_json.call_args_list[1].args[0])
        request_json.side_effect = [{}, {}]
        self.assertEqual(_wikipedia_author('unknown')['extract'], '')

    @patch('books.views._request_json')
    def test_wikipedia_selects_writer_instead_of_river(self, request_json):
        from .views import _wikipedia_author

        writer = self.wiki_result()['query']['pages'][0]
        river = {'title': '한강', 'extract': '한강은 한반도 중부를 흐르는 강이다.', 'fullurl': 'https://ko.wikipedia.org/wiki/한강'}
        request_json.return_value = {'query': {'pages': [river, writer]}}
        result = _wikipedia_author('한강')
        self.assertEqual(result['title'], '한강 (작가)')
        self.assertEqual(result['source'], writer['fullurl'])
        from urllib.parse import parse_qs, urlparse
        params = parse_qs(urlparse(request_json.call_args.args[0]).query)
        self.assertEqual(params['gsrsearch'], ['한강 작가'])

    @patch('books.views._request_json')
    def test_wikipedia_does_not_use_non_writer_result(self, request_json):
        from .views import _wikipedia_author

        request_json.return_value = {'query': {'pages': [{'title': '한강', 'extract': '서울을 흐르는 강이다.'}]}}
        result = _wikipedia_author('한강')
        self.assertEqual(result['source'], '')
        self.assertEqual(result['extract'], '')

    @patch('books.views._request_json')
    def test_untrusted_image_and_source_are_not_saved(self, request_json):
        wiki = self.wiki_result()
        wiki['query']['pages'][0]['thumbnail']['source'] = 'javascript:alert(1)'
        wiki['query']['pages'][0]['fullurl'] = 'https://unrelated.example/author'
        request_json.side_effect = [wiki, self.ai_result()]
        self.client.post(reverse('books:author_info', args=[self.book.pk]))
        self.book.refresh_from_db()
        self.assertEqual(self.book.author_image, '')
        self.assertEqual(self.book.author_source, '')

    @patch('books.views.urlopen')
    def test_http_client_json_encoding_headers_and_timeout(self, urlopen):
        from .views import _request_json

        urlopen.return_value.__enter__.return_value.read.return_value = b'{"ok":true}'
        result = _request_json('https://example.com', {'author': '한강'}, {'Authorization': 'Bearer dummy'}, timeout=45)
        self.assertTrue(result['ok'])
        request = urlopen.call_args.args[0]
        self.assertEqual(json.loads(request.data), {'author': '한강'})
        self.assertEqual(request.get_header('Authorization'), 'Bearer dummy')
        self.assertEqual(urlopen.call_args.kwargs['timeout'], 45)

    @patch('books.views._request_json')
    def test_network_errors_and_truncated_output_do_not_overwrite(self, request_json):
        self.book.author_info = '기존 소개'
        self.book.save()
        truncated = self.ai_result()
        truncated['choices'][0]['finish_reason'] = 'length'
        for replies in [[self.wiki_result(), truncated], [URLError('unavailable'), URLError('unavailable')]]:
            request_json.side_effect = replies
            response = self.client.post(reverse('books:author_info', args=[self.book.pk]), follow=True)
            self.assertContains(response, '작가 정보를 가져오지 못했습니다.' if len(replies) == 2 and isinstance(replies[0], dict) else 'GMS 서버에 연결하지 못했거나')
            self.book.refresh_from_db()
            self.assertEqual(self.book.author_info, '기존 소개')

    @patch('books.views._request_json')
    def test_wikipedia_failure_still_calls_gms(self, request_json):
        request_json.side_effect = [URLError('Wikipedia unavailable'), self.ai_result()]
        response = self.client.post(reverse('books:author_info', args=[self.book.pk]), follow=True)
        self.assertContains(response, '작가 정보와 대표작을 생성했습니다.')
        self.assertContains(response, '위키피디아 자료를 가져오지 못해')
        self.book.refresh_from_db()
        self.assertEqual(self.book.author_works, ['채식주의자'])
        self.assertEqual(request_json.call_args_list[1].args[1]['model'], 'gpt-5-nano')

    @patch('books.views._request_json')
    def test_gms_errors_explain_authentication_and_quota(self, request_json):
        from urllib.error import HTTPError

        for code, text in [(401, 'GMS 인증에 실패했습니다'), (429, 'GMS 사용 한도'), (400, 'GMS가 생성 요청을 처리하지 못했습니다')]:
            request_json.side_effect = [self.wiki_result(), HTTPError('https://example.com', code, 'error', {}, None)]
            response = self.client.post(reverse('books:author_info', args=[self.book.pk]), follow=True)
            self.assertContains(response, text)
            self.assertContains(response, str(code))


class StoredCoverTests(TestCase):
    @patch('books.views.urlopen')
    def test_downloaded_cover_is_saved_served_and_reused(self, urlopen):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import base64
        from .views import _store_cover, _stored_cover

        raw = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a/T8AAAAASUVORK5CYII=')
        remote_url = 'https://image.aladin.co.kr/product/1/cover200/book.png'
        result = {'url': remote_url, 'source': '알라딘', 'source_url': 'https://www.aladin.co.kr/shop/wproduct.aspx?ItemId=1'}
        response = urlopen.return_value.__enter__.return_value
        response.geturl.return_value = remote_url
        response.read.return_value = raw
        with TemporaryDirectory() as directory, patch('books.views._cover_directory', return_value=Path(directory)):
            stored = _store_cover('a' * 64, result)
            self.assertTrue(stored['url'].startswith('/books/covers/'))
            self.assertEqual(_stored_cover('a' * 64), stored)
            image = self.client.get(stored['url'])
            self.assertEqual(image.status_code, 200)
            self.assertEqual(image['Content-Type'], 'image/png')
            self.assertEqual(b''.join(image.streaming_content), raw)
            self.assertEqual(self.client.get('/books/covers/' + '0' * 64 + '.png/').status_code, 404)

    @patch('books.views.urlopen')
    def test_invalid_image_and_untrusted_host_are_not_stored(self, urlopen):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from .views import _store_cover

        result = {'url': 'https://untrusted.example/photo.jpg', 'source': '', 'source_url': ''}
        self.assertEqual(_store_cover('a' * 64, result), result)
        urlopen.assert_not_called()
        result['url'] = 'https://image.aladin.co.kr/product/1/cover200/book.jpg'
        response = urlopen.return_value.__enter__.return_value
        response.geturl.return_value = result['url']
        response.read.return_value = b'<html>not an image</html>'
        with TemporaryDirectory() as directory, patch('books.views._cover_directory', return_value=Path(directory)):
            self.assertEqual(_store_cover('a' * 64, result), result)
            self.assertEqual(list(Path(directory).iterdir()), [])
