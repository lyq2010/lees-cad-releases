"""Exercise production promotion with in-memory files and network adapters."""
import sys
sys.dont_write_bytecode = True
import json
import unittest
from unittest.mock import Mock, patch
import mirror


class MemoryPath:
    texts = {}

    def __init__(self, name):
        self.name = name

    def __truediv__(self, name):
        return MemoryPath(name)

    def __str__(self):
        return self.name

    def read_text(self):
        return self.texts[self.name]

    def write_bytes(self, value):
        self.texts[self.name] = value


class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.root = MemoryPath('root')
        self.config = {'cosBaseUrl': 'https://cos.invalid/', 'r2BaseUrl': 'https://r2.invalid/'}
        self.verified = {'payload': {'version': '0.1.3'}, 'payloadSha256': 'signed-hash'}
        self.files = {f'lees-cad/releases/0.1.3/asset-{i}': MemoryPath(f'asset-{i}') for i in range(12)}
        MemoryPath.texts = {f'readiness-{s}.json': json.dumps({'source': s, 'verified': True,
            'version': '0.1.3', 'payloadSha256': 'signed-hash', 'runId': 'current-run'}) for s in ('cos', 'r2')}

    def promote(self):
        mirror.promote(self.root, self.verified, self.files, self.config, MemoryPath('script'))

    def test_one_full_dual_source_readback_then_two_updates(self):
        with patch.object(mirror, 'env', return_value='current-run'), \
             patch.object(mirror, 'digest', return_value=('hash', 1)), \
             patch.object(mirror, 'public', return_value=('hash', 1)) as get, \
             patch.object(mirror, 'check_latest') as latest, patch.object(mirror, 'upload') as put:
            self.promote()
        self.assertEqual(get.call_count, 24)
        self.assertEqual([c.args[0] for c in put.call_args_list], ['cos', 'r2'])
        self.assertTrue(all(c.kwargs == {'mutable': True} for c in put.call_args_list))
        self.assertEqual([c.args[0] for c in latest.call_args_list], ['cos', 'r2', 'cos', 'r2'])

    def test_untrusted_readiness_never_reads_or_updates(self):
        for field, value in [('runId', 'other-run'), ('payloadSha256', 'wrong'), ('verified', False)]:
            self.setUp()
            row = json.loads(MemoryPath.texts['readiness-r2.json']); row[field] = value
            MemoryPath.texts['readiness-r2.json'] = json.dumps(row)
            with patch.object(mirror, 'env', return_value='current-run'), \
                 patch.object(mirror, 'public') as get, patch.object(mirror, 'upload') as put:
                with self.assertRaises(RuntimeError): self.promote()
                get.assert_not_called(); put.assert_not_called()

    def test_second_source_corruption_prevents_both_updates(self):
        with patch.object(mirror, 'env', return_value='current-run'), \
             patch.object(mirror, 'digest', return_value=('hash', 1)), \
             patch.object(mirror, 'public', side_effect=[('hash', 1)] * 12 + [('bad', 1)]), \
             patch.object(mirror, 'check_latest'), \
             patch.object(mirror, 'upload') as put:
            with self.assertRaises(RuntimeError): self.promote()
            put.assert_not_called()

    def test_newer_latest_prevents_updates(self):
        with patch.object(mirror, 'env', return_value='current-run'), \
             patch.object(mirror, 'digest', return_value=('hash', 1)), \
             patch.object(mirror, 'public', return_value=('hash', 1)), \
             patch.object(mirror, 'check_latest', side_effect=[None, RuntimeError('newer')]), \
             patch.object(mirror, 'upload') as put:
            with self.assertRaises(RuntimeError): self.promote()
            put.assert_not_called()

    def test_latest_is_rechecked_immediately_before_each_write(self):
        with patch.object(mirror, 'env', return_value='current-run'), \
             patch.object(mirror, 'digest', return_value=('hash', 1)), \
             patch.object(mirror, 'public', return_value=('hash', 1)), \
             patch.object(mirror, 'check_latest', side_effect=[None, None, None, RuntimeError('advanced')]), \
             patch.object(mirror, 'upload') as put:
            with self.assertRaises(RuntimeError): self.promote()
            self.assertEqual([c.args[0] for c in put.call_args_list], ['cos'])

    def test_latest_signature_version_and_size_guards(self):
        for version, digest, blocked in [('0.1.2', 'old', False), ('0.1.3', 'signed-hash', False),
                                          ('0.1.4', 'new', True), ('0.1.3', 'conflict', True)]:
            reply = Mock(); reply.__enter__ = Mock(return_value=reply); reply.__exit__ = Mock()
            reply.read.return_value = b'previous manifest'
            verified = {'payload': {'version': version}, 'payloadSha256': digest}
            with patch.object(mirror.urllib.request, 'build_opener') as opener, \
                 patch.object(mirror.subprocess, 'check_output', return_value=json.dumps(verified)):
                opener.return_value.open.return_value = reply
                if blocked:
                    with self.assertRaises(RuntimeError):
                        mirror.check_latest('cos', self.root, self.verified, self.config, self.root)
                else:
                    mirror.check_latest('cos', self.root, self.verified, self.config, self.root)

    def test_oversized_or_invalid_signed_latest_is_not_ignored(self):
        for body, error in [(b'x' * 65537, None), (b'bad-signature', RuntimeError('signature'))]:
            reply = Mock(); reply.__enter__ = Mock(return_value=reply); reply.__exit__ = Mock()
            reply.read.return_value = body
            with patch.object(mirror.urllib.request, 'build_opener') as opener, \
                 patch.object(mirror.subprocess, 'check_output', side_effect=error):
                opener.return_value.open.return_value = reply
                with self.assertRaises(RuntimeError):
                    mirror.check_latest('cos', self.root, self.verified, self.config, self.root)


if __name__ == '__main__':
    unittest.main()
