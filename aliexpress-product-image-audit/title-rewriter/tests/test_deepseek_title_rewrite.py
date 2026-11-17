import copy
import io
import json
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

import rewrite_titles_deepseek as titles


TITLE = 'Hot Sale Transformation NewAge NA-H74 NAH74 Megatank Action Figures Collection Gifts'


def reply(title=TITLE, **extra):
    return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(
        {'titleEn': title, 'modelCode': 'NA-H74', 'warnings': []})}}], **extra}


class DeepSeekTitleTests(unittest.TestCase):
    def product(self, **extra):
        return {'id': 1, 'title': 'NewAge NA-H74 威震天 变形玩具', 'shopId': 7, **extra}

    def test_prompt_uses_current_sop_without_description_or_write_instructions(self):
        messages = titles.make_messages(self.product(descriptionJson='SECRET_DESCRIPTION'), 7)
        text = json.dumps(messages, ensure_ascii=False)
        self.assertIn('Megatank', text)
        self.assertIn('NA-H74 NAH74', text)
        self.assertIn('Hot Sale', text)
        self.assertIn('Upgrade Kit', text)
        self.assertNotIn('SECRET_DESCRIPTION', text)
        self.assertNotIn('autoSave', text)

    def test_first_success_stops_without_quality_or_usage_gate(self):
        request = Mock(return_value=reply())
        row = titles.rewrite_one(self.product(), 7, request=request, retries=3, retry_delay=0)
        self.assertEqual(row['status'], 'SUCCEEDED')
        self.assertEqual(row['titleEn'], TITLE)
        self.assertIsNone(row['usage'])
        self.assertEqual(row['attempts'], 1)
        self.assertEqual(request.call_count, 1)

    def test_failed_request_or_invalid_output_retries_then_stops(self):
        request = Mock(side_effect=[TimeoutError(), reply('invalid'), reply(), reply()])
        row = titles.rewrite_one(self.product(), 7, request=request, retries=3, retry_delay=0)
        self.assertEqual(row['status'], 'SUCCEEDED')
        self.assertEqual(row['attempts'], 3)
        self.assertEqual(request.call_count, 3)
        self.assertEqual(len(row['calls']), 3)
        self.assertNotIn('error', row)

    def test_permanent_auth_error_is_not_retried(self):
        request = Mock(side_effect=urllib.error.HTTPError('http://localhost', 401, 'Unauthorized', {}, None))
        row = titles.rewrite_one(self.product(), 7, request=request, retries=3, retry_delay=0)
        self.assertEqual(row['status'], 'FAILED')
        self.assertEqual(request.call_count, 1)

    def test_exhausted_retries_does_not_report_success(self):
        request = Mock(side_effect=TimeoutError())
        row = titles.rewrite_one(self.product(), 7, request=request, retries=2, retry_delay=0)
        self.assertEqual(row['status'], 'FAILED')
        self.assertEqual(row['attempts'], 3)
        self.assertNotIn('titleEn', row)

    def test_truncated_response_is_retried_and_warnings_are_preserved(self):
        truncated = reply()
        truncated['choices'][0]['finish_reason'] = 'length'
        good = reply(usage={'total_tokens': 123})
        good['choices'][0]['message']['content'] = json.dumps(
            {'titleEn': TITLE, 'modelCode': 'NA-H74', 'warnings': ['角色需确认']})
        row = titles.rewrite_one(self.product(), 7, request=Mock(side_effect=[truncated, good]), retry_delay=0)
        self.assertEqual(row['warnings'], ['角色需确认'])
        self.assertEqual(row['usage'], {'total_tokens': 123})

    def test_malformed_response_shape_is_retried(self):
        request = Mock(side_effect=[{'choices': ['bad choice']}, reply()])
        row = titles.rewrite_one(self.product(), 7, request=request, retries=1, retry_delay=0)
        self.assertEqual(row['status'], 'SUCCEEDED')
        self.assertEqual(row['attempts'], 2)

    def test_parallel_batch_preserves_order_and_reuses_success_on_resume(self):
        barrier = threading.Barrier(2)
        def request(messages):
            barrier.wait(timeout=5)
            return reply()
        products = [self.product(id=1), self.product(id=2, title='NA-H74 威震天 再版')]
        original = copy.deepcopy(products)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'results.json'
            result = titles.run_batch(products, output, request=request, workers=2, retry_delay=0)
            self.assertEqual([r['id'] for r in result['results']], [1, 2])
            self.assertTrue(all(r['status'] == 'SUCCEEDED' for r in result['results']))
            never_call = Mock(side_effect=AssertionError('Successful item regenerated'))
            resumed = titles.run_batch(products, output, request=never_call, workers=2)
            self.assertEqual(never_call.call_count, 0)
            self.assertEqual(result['results'], resumed['results'])
            self.assertEqual(json.loads(output.read_text(encoding='utf-8'))['results'], resumed['results'])
        self.assertEqual(products, original)

    def test_duplicate_input_calls_once_and_changed_source_is_not_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'results.json'
            request = Mock(return_value=reply())
            titles.run_batch([self.product(), self.product()], output, request=request)
            self.assertEqual(request.call_count, 1)
            titles.run_batch([self.product(title='NA-H74 威震天 原创')], output, request=request)
            self.assertEqual(request.call_count, 2)

    def test_bad_local_input_does_not_call_api_or_block_other_items(self):
        with tempfile.TemporaryDirectory() as directory:
            request = Mock(return_value=reply())
            result = titles.run_batch([self.product(title=''), self.product()], Path(directory)/'out.json', request=request)
            self.assertEqual(result['results'][0]['status'], 'FAILED')
            self.assertEqual(result['results'][0]['attempts'], 0)
            self.assertEqual(result['results'][1]['status'], 'SUCCEEDED')
            self.assertEqual(request.call_count, 1)

    def test_transport_uses_existing_deepseek_http_entry(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps(reply()).encode()
        with patch.object(titles, '_open_model_request', return_value=response) as opened:
            result = titles.send_request(titles.make_messages(self.product(), 7),
                                        base_url='http://127.0.0.1:8788/v1/',
                                        model='deepseek-v4.1-flash', api_key='TEST_ONLY',
                                        timeout=45, max_tokens=2048)
        req = opened.call_args.args[0]
        body = json.loads(req.data)
        self.assertEqual(req.full_url, 'http://127.0.0.1:8788/v1/chat/completions')
        self.assertEqual(body['model'], 'deepseek-v4.1-flash')
        self.assertEqual(body['response_format'], {'type': 'json_object'})
        self.assertEqual(opened.call_args.kwargs['timeout'], 45)
        self.assertEqual(result, reply())

    def test_cli_file_transport_checkpoint_and_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.json'
            output = Path(directory) / 'nested/results.json'
            source.write_text(json.dumps([self.product()]), encoding='utf-8')
            args = ['--input', str(source), '--output', str(output), '--workers', '2',
                    '--retries', '1', '--retry-delay', '0']
            opened_requests = []
            def opener(request, timeout):
                opened_requests.append(json.loads(request.data))
                if len(opened_requests) == 1:
                    raise urllib.error.HTTPError(request.full_url, 429, 'Rate limited', {}, None)
                return io.BytesIO(json.dumps(reply()).encode())
            with patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'TEST_ONLY'}, clear=True), \
                    patch.object(titles, '_open_model_request', side_effect=opener), \
                    patch('sys.stdout', new_callable=io.StringIO):
                self.assertEqual(titles.main(args), 0)
                self.assertEqual(titles.main(args), 0)
            self.assertEqual(len(opened_requests), 2)
            saved = json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(saved['results'][0]['attempts'], 2)
            self.assertEqual(saved['results'][0]['titleEn'], TITLE)
            self.assertNotIn('TEST_ONLY', output.read_text(encoding='utf-8'))
            self.assertEqual(json.loads(source.read_text(encoding='utf-8')), [self.product()])

    def test_failed_items_retry_on_rerun_but_changed_settings_invalidate_success(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'out.json'
            titles.run_batch([self.product()], output, request=Mock(side_effect=TimeoutError()), retries=0)
            request = Mock(return_value=reply())
            titles.run_batch([self.product()], output, request=request)
            self.assertEqual(request.call_count, 1)
            titles.run_batch([self.product()], output, request=request, request_settings={'model': titles.DEFAULT_MODEL})
            self.assertEqual(request.call_count, 2)

    def test_shop_four_prefix_and_jsonl_input(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.jsonl'
            source.write_text(json.dumps(self.product(shopId=4)) + '\n\n', encoding='utf-8-sig')
            products = titles.load_products(source)
            request = Mock(return_value=reply(TITLE.replace('Hot Sale', 'In Stock')))
            result = titles.run_batch(products, Path(directory)/'out.json', request=request)
            self.assertEqual(result['results'][0]['status'], 'SUCCEEDED')
            self.assertTrue(result['results'][0]['titleEn'].startswith('In Stock '))


if __name__ == '__main__':
    unittest.main()
