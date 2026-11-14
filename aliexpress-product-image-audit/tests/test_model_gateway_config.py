import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from model_config import fingerprint, load_config, validate_config


def profile():
    return {'schema': 'model-gateway/v1', 'base_url': 'http://127.0.0.1:3425/v1',
            'models': ['workbuddy/deepseek-v4.1-flash', 'workbuddy/kimi-k3-1'],
            'max_output_tokens': 4096, 'retries': 0, 'timeout': 90}


class ModelGatewayConfigTests(unittest.TestCase):
    def reject(self, config, field):
        with self.assertRaises(ValueError) as caught:
            validate_config(config)
        self.assertEqual(str(caught.exception), 'INVALID_MODEL_CONFIG:' + field)

    def test_profile_is_copied_and_trailing_slash_normalized(self):
        original = profile()
        original['base_url'] += '///'
        before = copy.deepcopy(original)
        result = validate_config(original)
        self.assertEqual(result, profile())
        self.assertEqual(original, before)
        result['models'].append('other')
        self.assertEqual(original, before)

    def test_required_and_extra_fields(self):
        for field in profile():
            with self.subTest(missing=field):
                config = profile(); del config[field]
                self.reject(config, field)
        for field in ('api_key', 'secret', 'unknown'):
            with self.subTest(extra=field):
                config = profile(); config[field] = 'SECRET_DO_NOT_ECHO'
                self.reject(config, 'fields')
        for value in (None, [], 'SECRET_DO_NOT_ECHO'):
            self.reject(value, 'config')

    def test_schema_is_exact(self):
        for value in ('model-gateway/v2', None, True):
            config = profile(); config['schema'] = value
            self.reject(config, 'schema')

    def test_urls_accept_https_and_exact_loopback_http(self):
        for value in ('https://gateway.example/v1/', 'http://localhost:3425/v1',
                      'http://[::1]:3425/v1', 'http://127.0.0.1/v1'):
            config = profile(); config['base_url'] = value
            self.assertEqual(validate_config(config)['base_url'], value.rstrip('/'))

    def test_urls_reject_credentials_and_non_loopback_http(self):
        for value in ('http://remote.example/v1', 'http://127.0.0.2/v1',
                      'http://localhost.evil/v1', 'https://user:SECRET@gateway/v1',
                      'https://user@gateway/v1', 'https://gateway/v1?secret=SECRET',
                      'https://gateway/v1#SECRET', 'https://gateway/v1?',
                      'https://gateway/v1#', 'file:///v1', 'https:///v1',
                      'https://gateway:bad/v1', ' https://gateway/v1',
                      'https://gateway/\nv1', None):
            with self.subTest(url=value):
                config = profile(); config['base_url'] = value
                self.reject(config, 'base_url')

    def test_models_require_two_distinct_safe_identifiers(self):
        for value in ([], ['a'], ['a', 'b', 'c'], ['a', 'A'], ['a', ''],
                      ['a', 'has space'], ['a', 'bad?key'], ['a', None],
                      ['a', '模型'], ('a', 'b'), 'a,b'):
            with self.subTest(models=value):
                config = profile(); config['models'] = value
                self.reject(config, 'models')
        config = profile(); config['models'] = ['Vendor/A_1.2:fast', 'vendor/b-2']
        self.assertEqual(validate_config(config)['models'], config['models'])

    def test_integer_limits_exclude_boolean(self):
        for field, low, high in (('max_output_tokens', 1, 16384), ('retries', 0, 2), ('timeout', 1, 150)):
            for value in (low, high):
                config = profile(); config[field] = value
                self.assertEqual(validate_config(config)[field], value)
            for value in (low-1, high+1, True, False, 1.0, '1', None):
                config = profile(); config[field] = value
                self.reject(config, field)

    def test_load_utf8_bom_and_sanitize_load_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'profile.json'
            path.write_text(json.dumps(profile()), encoding='utf-8-sig')
            self.assertEqual(load_config(path), profile())
            for data in (b'{SECRET', b'\xff'):
                path.write_bytes(data)
                with self.assertRaisesRegex(ValueError, '^INVALID_MODEL_CONFIG:file$'):
                    load_config(path)
            with self.assertRaisesRegex(ValueError, '^INVALID_MODEL_CONFIG:file$'):
                load_config(Path(directory) / 'missing')

    def test_fingerprint_is_canonical_validated_sha256(self):
        expected = hashlib.sha256(json.dumps(profile(), sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
        config = dict(reversed(list(profile().items())))
        config['base_url'] += '/'
        self.assertEqual(fingerprint(config), expected)
        config['timeout'] += 1
        self.assertNotEqual(fingerprint(config), expected)
        config['api_key'] = 'SECRET'
        with self.assertRaisesRegex(ValueError, '^INVALID_MODEL_CONFIG:fields$'):
            fingerprint(config)


if __name__ == '__main__':
    unittest.main()
