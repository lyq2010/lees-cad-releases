"""Prove bucket checks stay on authenticated metadata endpoints without body GET."""
import sys
sys.dont_write_bytecode = True
import io
import json
import unittest
import urllib.error
from unittest.mock import Mock, patch
import storage

HASH = 'a' * 32
KEY = 'lees-cad/stable/latest.json'
PATH = 'accounts/' + 'b' * 32 + '/r2/buckets/cad/objects'


class ServiceError(Exception):
    def __init__(self, code):
        self.code = code

    def get_status_code(self):
        return self.code


class StorageTests(unittest.TestCase):
    def test_cos_only_heads_origin_with_base_prefix(self):
        sdk = Mock(); sdk.CosServiceError = ServiceError
        client = Mock(); client.head_object.return_value = {'ETag': '"' + HASH + '"', 'Content-Length': '12'}
        with patch.dict(sys.modules, {'qcloud_cos': sdk}), patch.object(storage, 'cos_client', return_value=client), \
             patch.object(storage, 'env', return_value='bucket'), patch.object(storage.urllib.request, 'build_opener') as network:
            self.assertEqual(storage.metadata('cos', KEY, 'https://unused.invalid/download/'), (HASH, 12))
            client.head_object.assert_called_once_with(Bucket='bucket', Key='download/' + KEY)
            client.get_object.assert_not_called()
            network.assert_not_called()

    def test_only_cos_404_means_absent(self):
        sdk = Mock(); sdk.CosServiceError = ServiceError
        for code in (404, 403, 500):
            with patch.dict(sys.modules, {'qcloud_cos': sdk}), patch.object(storage, 'cos_client') as client, \
                 patch.object(storage, 'env', return_value='bucket'):
                client.return_value.head_object.side_effect = ServiceError(code)
                if code == 404:
                    self.assertIsNone(storage.metadata('cos', KEY, 'https://unused.invalid/'))
                else:
                    with self.assertRaises(ServiceError): storage.metadata('cos', KEY, 'https://unused.invalid/')

    def test_unknown_weak_multipart_etag_and_missing_size_fail_closed(self):
        for etag, size in [(None, 1), ('W/"' + HASH + '"', 1), (HASH + '-2', 1), ('f' * 64, 1),
                           (HASH, None), (HASH, -1), (HASH, True), (HASH, '1.0')]:
            with self.assertRaises(RuntimeError): storage.identity(etag, size)

    def test_r2_only_lists_exact_key_metadata_with_pagination(self):
        pages = [{'result': [], 'result_info': {'is_truncated': True, 'cursor': 'next'}},
                 {'result': [{'key': KEY + '.unrelated', 'etag': 'c' * 32, 'size': 100},
                             {'key': KEY, 'etag': HASH, 'size': 12}]}]
        with patch.object(storage, 'r2_path', return_value=PATH), patch.object(storage, 'r2_request', side_effect=pages) as api:
            self.assertEqual(storage.metadata('r2', KEY, 'https://unused.invalid/'), (HASH, 12))
            for call in api.call_args_list:
                self.assertTrue(call.args[0].startswith(PATH + '?'))
                self.assertIn('prefix=lees-cad%2Fstable%2Flatest.json', call.args[0])
            self.assertIn('cursor=next', api.call_args.args[0])

    def test_r2_missing_object_and_invalid_pagination(self):
        with patch.object(storage, 'r2_path', return_value=PATH), \
             patch.object(storage, 'r2_request', return_value={'result': []}):
            self.assertIsNone(storage.metadata('r2', KEY, 'https://unused.invalid/'))
        for result in [{'result': [], 'result_info': {'is_truncated': True, 'cursor': 'same'}},
                       {'result': [{'key': 'other-product', 'etag': HASH, 'size': 12}]},
                       {'result': [{'key': KEY, 'etag': HASH, 'size': 12}] * 2}]:
            with patch.object(storage, 'r2_path', return_value=PATH), patch.object(storage, 'r2_request', return_value=result):
                with self.assertRaises(RuntimeError): storage.metadata('r2', KEY, 'https://unused.invalid/')

    def test_r2_api_refuses_every_object_get_and_redirect(self):
        with patch.object(storage.urllib.request, 'build_opener') as network:
            for path in (PATH + '/' + KEY, PATH, 'https://bucket.invalid/' + KEY, 'accounts/other'):
                with self.assertRaises(RuntimeError): storage.r2_request(path)
            network.assert_not_called()
        with self.assertRaises(RuntimeError):
            storage.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://bucket.invalid/')

    def test_r2_api_reads_only_management_json_and_propagates_errors(self):
        response = Mock(); response.__enter__ = Mock(return_value=response); response.__exit__ = Mock()
        response.read.return_value = json.dumps({'success': True, 'result': []}).encode()
        with patch.object(storage, 'env', return_value='token'), patch.object(storage.urllib.request, 'build_opener') as opener:
            opener.return_value.open.return_value = response
            self.assertEqual(storage.r2_request(PATH + '?prefix=lees-cad%2F'), {'success': True, 'result': []})
            req = opener.return_value.open.call_args.args[0]
            self.assertEqual(req.get_method(), 'GET')
            self.assertTrue(req.full_url.startswith('https://api.cloudflare.com/client/v4/' + PATH + '?'))
            error = urllib.error.HTTPError(req.full_url, 403, '', {}, io.BytesIO())
            self.addCleanup(error.close)
            opener.return_value.open.side_effect = error
            with self.assertRaises(urllib.error.HTTPError): storage.r2_request(PATH + '?prefix=lees-cad%2F')

    def test_local_md5_is_only_a_metadata_fingerprint(self):
        file = Mock(); file.open.return_value = io.BytesIO(b'abc'); file.stat.return_value.st_size = 3
        self.assertEqual(storage.fingerprint(file), ('900150983cd24fb0d6963f7d28e17f72', 3))


if __name__ == '__main__':
    unittest.main()
