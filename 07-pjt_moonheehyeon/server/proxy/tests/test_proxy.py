"""GMS 호출을 대체하여 API의 분기·호출 순서·오류 계약을 검증합니다."""
import base64
import json
import io
import unittest
from unittest.mock import Mock, patch

import requests
from fastapi import HTTPException
from PIL import Image

import main
from schemas import (
    ChatRequest, ChatGuardrailRequest, DecideRouteRequest, ImageGenerationRequest,
    ImageAnalysisRequest, ChatScoreRequest, GenerateSpeechRequest,
)


class ProxyTests(unittest.TestCase):
    def test_rejected_requests_never_generate(self):
        requests_to_check = [
            (main.chat_completions, ChatRequest(messages=[{'role': 'user', 'content': 'blocked'}])),
            (main.image_generations, ImageGenerationRequest(prompt='blocked')),
            (main.image_analysis, ImageAnalysisRequest(image_base64='AA==', question='blocked')),
        ]
        for endpoint, request in requests_to_check:
            with self.subTest(endpoint=endpoint.__name__), patch.object(
                main, 'ask_gms', return_value='{"is_appropriate": false}'
            ) as ask, patch.object(main, 'gms_post') as post:
                with self.assertRaises(HTTPException) as error:
                    endpoint(request)
                self.assertEqual(error.exception.status_code, 403)
                self.assertEqual(ask.call_count, 1)
                post.assert_not_called()

    def test_guardrail_failure_never_generates(self):
        for answer in ['not json', '{"is_appropriate": "false"}', '{}']:
            with self.subTest(answer=answer), patch.object(main, 'ask_gms', return_value=answer) as ask:
                with self.assertRaises(HTTPException) as error:
                    main.chat_completions(ChatRequest(messages=[{'content': 'request'}]))
                self.assertEqual(error.exception.status_code, 503)
                self.assertEqual(ask.call_count, 1)

    def test_guardrail_schema(self):
        with patch.object(main, 'ask_gms', return_value='{"is_appropriate": true}') as ask:
            self.assertEqual(main.chat_guardrail(ChatGuardrailRequest(prompt='book')), {'is_appropriate': True})
        response_format = ask.call_args.args[2]
        self.assertTrue(response_format['json_schema']['strict'])
        schema = response_format['json_schema']['schema']
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(schema['required'], ['is_appropriate'])

    def test_model_selection_and_call_order(self):
        for enabled, tier, expected in [
            (False, None, main.MODEL_NANO),
            (True, 'simple', main.MODEL_NANO),
            (True, 'complex', main.MODEL_MINI),
        ]:
            answers = ['{"is_appropriate": true}']
            if enabled:
                answers.append(json.dumps({'tier': tier}))
            answers.append('recommended books')
            with self.subTest(enabled=enabled, tier=tier), patch.object(main, 'ask_gms', side_effect=answers) as ask:
                result = main.chat_completions(ChatRequest(messages=[{'content': 'book'}], use_tier_routing=enabled))
                self.assertEqual(result['model_used'], expected)
                self.assertEqual(ask.call_count, 3 if enabled else 2)
                self.assertEqual(ask.call_args.args[1], expected)

    def test_route_only_allows_known_paths(self):
        for route in ['/chat/completions', '/images/generations']:
            with patch.object(main, 'ask_gms', return_value=json.dumps({'route': route})):
                self.assertEqual(main.decide_route(DecideRouteRequest(prompt='book'))['route'], route)
        with patch.object(main, 'ask_gms', return_value='{"route": "/unknown"}'):
            with self.assertRaises(HTTPException) as error:
                main.decide_route(DecideRouteRequest(prompt='book'))
            self.assertEqual(error.exception.status_code, 503)

    def test_image_generation_contract(self):
        response = Mock()
        response.json.return_value = {'data': [{'b64_json': 'image-data'}]}
        with patch.object(main, 'MODEL_IMAGE', 'gpt-image-1-mini'), patch.object(main, 'ensure_appropriate') as guard, patch.object(main, 'gms_post', return_value=response) as post:
            result = main.image_generations(ImageGenerationRequest(prompt='cover'))
        guard.assert_called_once_with('cover')
        self.assertEqual(result, {'image_base64': 'image-data'})
        self.assertEqual(post.call_args.args[0], '/images/generations')
        self.assertEqual(post.call_args.args[1]['output_format'], 'jpeg')
        self.assertEqual(post.call_args.args[1]['quality'], 'low')

    def test_gemini_image_is_returned_as_jpeg(self):
        image = io.BytesIO()
        Image.new('RGBA', (4, 4), (30, 70, 45, 255)).save(image, format='PNG')
        response = Mock()
        response.json.return_value = {'steps': [
            {'type': 'thought', 'signature': 'do-not-use'},
            {'type': 'model_output', 'content': [
                {'type': 'text', 'text': 'generated cover'},
                {'type': 'image', 'mime_type': 'image/png', 'data': base64.b64encode(image.getvalue()).decode()},
            ]},
        ]}
        with patch.object(main, 'MODEL_IMAGE', 'gemini-3.1-flash-lite-image'), patch.object(main, 'ensure_appropriate') as guard, patch.object(main, 'gms_post', return_value=response) as post:
            result = main.image_generations(ImageGenerationRequest(prompt='cover'))
        guard.assert_called_once_with('cover')
        self.assertEqual(post.call_args.args[0], '/interactions')
        self.assertEqual(post.call_args.kwargs['headers'], {'x-goog-api-key': main.GMS_KEY})
        with Image.open(io.BytesIO(base64.b64decode(result['image_base64']))) as jpeg:
            self.assertEqual(jpeg.format, 'JPEG')
            self.assertEqual(jpeg.size, (4, 4))

    def test_gemini_response_without_image_is_503(self):
        response = Mock()
        response.json.return_value = {'outputs': [{'type': 'text', 'text': 'no image'}]}
        with patch.object(main, 'MODEL_IMAGE', 'gemini-3.1-flash-lite-image'), patch.object(main, 'ensure_appropriate'), patch.object(main, 'gms_post', return_value=response):
            with self.assertRaises(HTTPException) as error:
                main.image_generations(ImageGenerationRequest(prompt='cover'))
            self.assertEqual(error.exception.status_code, 503)

    def test_image_analysis_sends_question_and_image(self):
        for encoded, mime in [('iVBORw==', 'image/png'), ('/9j/AA==', 'image/jpeg')]:
            with patch.object(main, 'ensure_appropriate') as guard, patch.object(main, 'ask_gms', return_value='analysis') as ask:
                result = main.image_analysis(ImageAnalysisRequest(image_base64=encoded, question='similar books'))
            guard.assert_called_once_with('similar books')
            content = ask.call_args.args[0][-1]['content']
            self.assertEqual(content[0]['image_url']['url'], f'data:{mime};base64,{encoded}')
            self.assertEqual(content[1]['text'], 'similar books')
            self.assertEqual(result, {'content': 'analysis'})

    def test_score_range(self):
        for score in [0, 100, -1, 101, True]:
            with self.subTest(score=score), patch.object(main, 'ask_gms', return_value=json.dumps({'score': score, 'reason': 'reason'})):
                request = ChatScoreRequest(messages=[{'content': 'book'}], answer='answer')
                if type(score) is int and 0 <= score <= 100:
                    self.assertEqual(main.chat_score(request)['score'], score)
                else:
                    with self.assertRaises(HTTPException):
                        main.chat_score(request)

    def test_speech_returns_base64_mp3(self):
        response = Mock(content=b'ID3-audio')
        with patch.object(main, 'gms_post', return_value=response) as post:
            result = main.generate_speech(GenerateSpeechRequest(text='hello'))
        self.assertEqual(base64.b64decode(result['audio_data']), b'ID3-audio')
        self.assertEqual(post.call_args.args, ('/audio/speech', {
            'model': main.MODEL_TTS, 'input': 'hello', 'voice': 'nova', 'response_format': 'mp3',
        }))

    def test_gms_errors_are_503_and_timeout_is_set(self):
        for code in [400, 401, 403, 429, 500]:
            with self.subTest(code=code), patch.object(main.requests, 'post', return_value=Mock(status_code=code, text='upstream error')) as post:
                with self.assertRaises(HTTPException) as error:
                    main.gms_post('/chat/completions', {})
                self.assertEqual(error.exception.status_code, 503)
                self.assertEqual(error.exception.detail, 'model server error')
                self.assertEqual(post.call_args.kwargs['timeout'], 120)
        for error_type in [requests.Timeout, requests.ConnectionError]:
            with patch.object(main.requests, 'post', side_effect=error_type()):
                with self.assertRaises(HTTPException) as error:
                    main.gms_post('/chat/completions', {})
                self.assertEqual(error.exception.status_code, 503)


if __name__ == '__main__':
    unittest.main()
