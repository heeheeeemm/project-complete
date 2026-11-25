import os
import json
import unittest
from unittest.mock import patch

import requests

from app.llm import AgentConfigurationError, analyze_request


class LLMErrorTests(unittest.TestCase):
    def test_429_distinguishes_rate_limit_from_provider_quota_without_leaking_body(self):
        for code in ('rate_limit_exceeded', 'insufficient_quota', 'secret-unrecognized-code'):
            with self.subTest(code=code), patch.dict(os.environ, {'OPENAI_API_KEY': 'fixture', 'OPENAI_MODEL': 'fixture'}):
                response = requests.Response()
                response.status_code = 429
                response.headers['Retry-After'] = '30'
                response._content = json.dumps({'error': {'code': code, 'message': 'secret upstream text'}}).encode()
                with patch('app.llm.requests.post', return_value=response), self.assertRaises(AgentConfigurationError) as raised:
                    analyze_request('hello', {})
                self.assertEqual(getattr(raised.exception, 'provider_code', None), code if code != 'secret-unrecognized-code' else 'UNKNOWN')
                self.assertEqual(getattr(raised.exception, 'retry_after', None), 30)
                self.assertNotIn('secret', str(raised.exception))

    def test_analysis_request_caps_output_and_omits_unused_tool_output_schemas(self):
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({'choices': [{'message': {'content': json.dumps({'intent': 'help', 'reason': 'greeting'})}}]}).encode()
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'fixture', 'OPENAI_MODEL': 'fixture'}), patch('app.llm.requests.post', return_value=response) as post:
            self.assertEqual(analyze_request('hello', {})['intent'], 'help')
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload.get('max_completion_tokens'), 1024)
        self.assertNotIn('output_schema', payload['messages'][0]['content'])

    def test_http_errors_have_safe_distinct_codes(self):
        for status in (400, 401, 403, 404, 429, 500):
            with self.subTest(status=status), patch.dict(os.environ, {'OPENAI_API_KEY': 'fixture-secret', 'OPENAI_MODEL': 'fixture'}):
                response = requests.Response()
                response.status_code = status
                response._content = b'{"error":{"message":"sensitive-provider-response"}}'
                with patch('app.llm.requests.post', return_value=response), self.assertRaises(AgentConfigurationError) as raised:
                    analyze_request('hello', {})
                self.assertEqual(getattr(raised.exception, 'code', None), f'HTTP_{status}')
                self.assertNotIn('fixture-secret', str(raised.exception))
                self.assertNotIn('sensitive-provider-response', str(raised.exception))

    def test_connection_and_invalid_response_are_distinct(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'fixture', 'OPENAI_MODEL': 'fixture'}):
            with patch('app.llm.requests.post', side_effect=requests.ConnectionError('private details')), self.assertRaises(AgentConfigurationError) as raised:
                analyze_request('hello', {})
            self.assertEqual(getattr(raised.exception, 'code', None), 'CONNECTION_ERROR')
            response = requests.Response()
            response.status_code = 200
            response._content = b'not JSON'
            with patch('app.llm.requests.post', return_value=response), self.assertRaises(AgentConfigurationError) as raised:
                analyze_request('hello', {})
            self.assertEqual(getattr(raised.exception, 'code', None), 'INVALID_RESPONSE')
