from unittest.mock import patch

import requests
from django.test import Client, TestCase
from django.urls import reverse

from .models import ConversationMessage, Recommendation
from .tests import proxy_response


class ConversationTests(TestCase):
    def setUp(self):
        session = self.client.session
        session['reading'] = True
        session.save()
        self.result = Recommendation.objects.create(
            request_text='가벼운 소설', content='첫 추천: **어린 왕자**',
            model_used='gpt-5-nano', session_key=session.session_key,
            use_tier_routing=True,
        )
        self.url = reverse('recommend:conversation', args=[self.result.pk])

    @patch('recommend.views.requests.post')
    def test_followup_includes_initial_and_previous_conversation(self, post):
        ConversationMessage.objects.create(recommendation=self.result, role='user', content='더 짧은 책은?')
        ConversationMessage.objects.create(recommendation=self.result, role='assistant', content='짧은 책 추천')
        post.return_value = proxy_response({'content': '두 책의 차이는...', 'model_used': 'gpt-5-nano'})
        response = self.client.post(self.url, {'question': '두 책을 비교해줘'}, follow=True)
        self.assertContains(response, '두 책의 차이는...')
        sent = post.call_args.kwargs['json']
        self.assertEqual([m['role'] for m in sent['messages']], ['developer', 'user', 'assistant', 'user', 'assistant', 'user'])
        self.assertEqual(sent['messages'][1]['content'], '가벼운 소설')
        self.assertEqual(sent['messages'][2]['content'], '첫 추천: **어린 왕자**')
        self.assertEqual(sent['messages'][-1]['content'], '두 책을 비교해줘')
        self.assertTrue(sent['use_tier_routing'])
        self.assertEqual(self.result.messages.count(), 4)
        self.client.get(self.url)
        post.assert_called_once()

    @patch('recommend.views.requests.post')
    def test_guardrail_and_failure_preserve_history_and_question(self, post):
        for status in [403, 503]:
            post.return_value = proxy_response(status=status)
            response = self.client.post(self.url, {'question': '다른 책은?'})
            self.assertEqual(response.status_code, status)
            self.assertContains(response, '다른 책은?', status_code=status)
            self.assertContains(response, '어린 왕자', status_code=status)
            self.assertEqual(self.result.messages.count(), 0)
        post.side_effect = requests.Timeout()
        response = self.client.post(self.url, {'question': '다른 책은?'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.result.messages.count(), 0)

    @patch('recommend.views.requests.post')
    def test_only_owner_session_can_read_or_reply(self, post):
        other = Client()
        session = other.session
        session['reading'] = True
        session.save()
        for client in [Client(), other]:
            self.assertEqual(client.get(self.url).status_code, 404)
            self.assertEqual(client.post(self.url, {'question': '누구의 대화?'}).status_code, 404)
        post.assert_not_called()

    @patch('recommend.views.requests.post')
    def test_invalid_followups_do_not_call_model(self, post):
        for question in ['', '   ', '가' * 301]:
            response = self.client.post(self.url, {'question': question})
            self.assertEqual(response.status_code, 200)
            self.assertIn('question', response.context['followup_form'].errors)
        post.assert_not_called()
        self.assertEqual(self.result.messages.count(), 0)

    @patch('recommend.views.requests.post')
    def test_context_is_bounded_and_ordered(self, post):
        for index in range(12):
            ConversationMessage.objects.create(recommendation=self.result, role='user', content=f'질문{index}')
            ConversationMessage.objects.create(recommendation=self.result, role='assistant', content=f'답변{index}')
        post.return_value = proxy_response({'content': '새 답변'})
        self.client.post(self.url, {'question': '계속'})
        messages = post.call_args.kwargs['json']['messages']
        self.assertEqual(len(messages), 24)
        self.assertEqual(messages[3]['content'], '질문2')
        self.assertEqual(messages[-2]['content'], '답변11')

    def test_model_html_is_escaped_and_bold_is_readable(self):
        self.result.content = '**추천** <script>alert(1)</script>'
        self.result.save()
        response = self.client.get(self.url)
        self.assertContains(response, '<strong>추천</strong>')
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
