import base64
import io
import tempfile
from unittest.mock import Mock, patch

import requests
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .forms import RecommendationForm
from .models import Recommendation, ImageAnalysis, Speech


def proxy_response(data=None, status=200):
    response = Mock(status_code=status)
    response.json.return_value = data or {}
    return response


class RecommendationTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        setting = override_settings(MEDIA_ROOT=self.media.name)
        setting.enable()
        self.addCleanup(setting.disable)

    def test_all_input_pages_render(self):
        for name in ['form', 'text', 'route', 'image', 'analyze', 'flow', 'tts']:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse('recommend:' + name)).status_code, 200)

    def test_required_and_length_validation(self):
        for text in ['', '   ', '가' * 301]:
            form = RecommendationForm({'request_text': text})
            self.assertFalse(form.is_valid())
            self.assertIn('request_text', form.errors)
        self.assertTrue(RecommendationForm({'request_text': '가' * 300}).is_valid())
        self.client.post(reverse('recommend:form'), {'request_text': '소설 추천'})
        self.assertEqual(Recommendation.objects.get().request_text, '소설 추천')

    @patch('recommend.views.requests.post')
    def test_invalid_input_never_calls_proxy(self, post):
        for name in ['text', 'route', 'image', 'flow', 'tts']:
            self.client.post(reverse('recommend:' + name), {'request_text': '', 'text': ''})
        post.assert_not_called()
        self.assertEqual(Recommendation.objects.count(), 0)

    @patch('recommend.views.requests.post')
    def test_text_score_and_model_are_saved(self, post):
        post.side_effect = [
            proxy_response({'content': '추천 도서', 'model_used': 'gpt-5-mini'}),
            proxy_response({'score': 90, 'reason': '취향 일치'}),
        ]
        response = self.client.post(reverse('recommend:text'), {'request_text': '소설', 'use_tier_routing': 'on'}, follow=True)
        self.assertContains(response, '90')
        result = Recommendation.objects.get()
        self.assertEqual((result.score, result.model_used), (90, 'gpt-5-mini'))
        self.assertTrue(post.call_args_list[0].kwargs['json']['use_tier_routing'])
        self.assertEqual(post.call_args_list[1].kwargs['json']['answer'], '추천 도서')
        self.assertTrue(all(call.kwargs['timeout'] == 180 for call in post.call_args_list))

    @patch('recommend.views.requests.post')
    def test_score_failure_preserves_recommendation(self, post):
        post.side_effect = [proxy_response({'content': '추천 도서', 'model_used': 'gpt-5-nano'}), requests.Timeout()]
        response = self.client.post(reverse('recommend:text'), {'request_text': '소설'}, follow=True)
        self.assertContains(response, '추천 도서')
        self.assertIsNone(Recommendation.objects.get().score)

    @patch('recommend.views.requests.post')
    def test_rejected_and_failed_requests_are_not_saved(self, post):
        for name in ['text', 'image']:
            for status, expected, template in [(403, 403, 'rejected'), (503, 503, 'error')]:
                post.return_value = proxy_response(status=status)
                response = self.client.post(reverse('recommend:' + name), {'request_text': 'request'})
                self.assertEqual(response.status_code, expected)
                self.assertTemplateUsed(response, f'recommend/{template}.html')
        self.assertEqual(Recommendation.objects.count(), 0)

    @patch('recommend.views.requests.post')
    def test_flow_routes_before_generation(self, post):
        for route, data in [
            ('/chat/completions', {'content': '책 추천', 'model_used': 'gpt-5-nano'}),
            ('/images/generations', {'image_base64': 'aW1hZ2U='}),
        ]:
            post.reset_mock()
            post.side_effect = [proxy_response({'route': route}), proxy_response(data)]
            response = self.client.post(reverse('recommend:flow'), {'request_text': 'request'}, follow=True)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(post.call_args_list[0].args[0].endswith('/decide-route'))
            self.assertTrue(post.call_args_list[1].args[0].endswith(route))
            self.assertEqual(post.call_count, 2)
            self.assertEqual(response.context['result'].route, route)

    @patch('recommend.views.requests.post')
    def test_flow_stops_on_route_failure_and_generation_rejection(self, post):
        post.return_value = proxy_response(status=503)
        response = self.client.post(reverse('recommend:flow'), {'request_text': 'request'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(post.call_count, 1)
        post.side_effect = [proxy_response({'route': '/chat/completions'}), proxy_response(status=403)]
        response = self.client.post(reverse('recommend:flow'), {'request_text': 'request'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Recommendation.objects.count(), 0)

    @patch('recommend.views.requests.post')
    def test_image_saved_and_served_by_media_url(self, post):
        image = io.BytesIO()
        Image.new('RGB', (2, 2)).save(image, format='JPEG')
        post.return_value = proxy_response({'image_base64': base64.b64encode(image.getvalue()).decode()})
        response = self.client.post(reverse('recommend:image'), {'request_text': '표지'})
        result = Recommendation.objects.get()
        self.assertTrue(result.image.name.startswith('images/'))
        self.assertTrue(result.image.name.endswith('.jpg'))
        with result.image.open('rb') as saved:
            self.assertEqual(saved.read(), image.getvalue())
        self.assertContains(response, result.image.url)
        self.assertNotContains(response, 'data:image/jpeg;base64,')

    @patch('recommend.views.requests.post')
    def test_uploaded_cover_is_encoded(self, post):
        image = io.BytesIO()
        Image.new('RGB', (2, 2)).save(image, format='PNG')
        uploaded = SimpleUploadedFile('cover.png', image.getvalue(), content_type='image/png')
        post.return_value = proxy_response({'content': '분석 결과'})
        response = self.client.post(reverse('recommend:analyze'), {'image': uploaded, 'question': '비슷한 책'})
        self.assertContains(response, '분석 결과')
        self.assertEqual(base64.b64decode(post.call_args.kwargs['json']['image_base64']), image.getvalue())
        self.assertEqual(ImageAnalysis.objects.get().content, '분석 결과')

    @patch('recommend.views.requests.post')
    def test_tts_player(self, post):
        post.return_value = proxy_response({'audio_data': 'SUQz'})
        response = self.client.post(reverse('recommend:tts'), {'text': '추천 이유'})
        self.assertContains(response, '<audio controls')
        self.assertContains(response, 'data:audio/mp3;base64,SUQz')
        self.assertEqual(Speech.objects.get().text, '추천 이유')

    @patch('recommend.views.requests.post', side_effect=requests.ConnectionError())
    def test_connection_failure_shows_retry_page(self, post):
        response = self.client.post(reverse('recommend:text'), {'request_text': '소설'})
        self.assertEqual(response.status_code, 503)
        self.assertTemplateUsed(response, 'recommend/error.html')

    def test_csrf_is_required(self):
        response = Client(enforce_csrf_checks=True).post(reverse('recommend:form'), {'request_text': '소설'})
        self.assertEqual(response.status_code, 403)
