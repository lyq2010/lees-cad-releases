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

    def test_metadata_only_dual_source_check_then_two_updates(self):
        with patch.object(mirror, 'env', return_value='current-run'), \
             patch.object(mirror, 'fingerprint', return_value=('hash', 1)), \
             patch.object(mirror, 'metadata', return_value=('hash', 1)) as get, \
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
                 patch.object(mirror, 'metadata') as get, patch.object(mirror, 'upload') as put:
                with self.assertRaises(RuntimeError): self.promote()
                get.assert_not_called(); put.assert_not_called()

    def test_second_source_corruption_prevents_both_updates(self):
        with patch.object(mirror, 'env', return_value='current-run'), \
             patch.object(mirror, 'fingerprint', return_value=('hash', 1)), \
             patch.object(mirror, 'metadata', side_effect=[('hash', 1)] * 12 + [('bad', 1)]), \
             patch.object(mirror, 'check_latest'), \
             patch.object(mirror, 'upload') as put:
            with self.assertRaises(RuntimeError): self.promote()
            put.assert_not_called()

    def test_newer_latest_prevents_updates(self):
        with patch.object(mirror, 'env', return_value='current-run'), \
             patch.object(mirror, 'fingerprint', return_value=('hash', 1)), \
             patch.object(mirror, 'metadata', return_value=('hash', 1)), \
             patch.object(mirror, 'check_latest', side_effect=[None, RuntimeError('newer')]), \
             patch.object(mirror, 'upload') as put:
            with self.assertRaises(RuntimeError): self.promote()
            put.assert_not_called()

    def test_latest_is_rechecked_immediately_before_each_write(self):
        with patch.object(mirror, 'env', return_value='current-run'), \
             patch.object(mirror, 'fingerprint', return_value=('hash', 1)), \
             patch.object(mirror, 'metadata', return_value=('hash', 1)), \
             patch.object(mirror, 'check_latest', side_effect=[None, None, None, RuntimeError('advanced')]), \
             patch.object(mirror, 'upload') as put:
            with self.assertRaises(RuntimeError): self.promote()
            self.assertEqual([c.args[0] for c in put.call_args_list], ['cos'])

    def test_latest_local_signature_and_version_guards(self):
        MemoryPath.texts['previous-release.json'] = json.dumps({'releaseId': 'previous'})
        for version, digest, blocked in [('0.1.2', 'old', False), ('0.1.3', 'signed-hash', False),
                                          ('0.1.4', 'new', True), ('0.1.3', 'conflict', True)]:
            prior = {'payload': {'version': version, 'releaseId': 'previous'}, 'payloadSha256': digest}
            with patch.object(mirror, 'metadata', return_value=('old', 1)), \
                 patch.object(mirror, 'fingerprint', side_effect=[('new', 2), ('old', 1)]), \
                 patch.object(mirror.subprocess, 'check_output', return_value=json.dumps(prior)):
                if blocked:
                    with self.assertRaises(RuntimeError):
                        mirror.check_latest('cos', self.root, self.verified, self.config, self.root)
                else:
                    mirror.check_latest('cos', self.root, self.verified, self.config, self.root)

    def test_missing_unknown_or_unsigned_latest_is_not_ignored(self):
        MemoryPath.texts['previous-release.json'] = json.dumps({'releaseId': 'previous'})
        prior = {'payload': {'version': '0.1.2', 'releaseId': 'previous'}, 'payloadSha256': 'old'}
        for actual, error in [(None, None), (('unknown', 2), None), (('old', 1), RuntimeError('signature'))]:
            with patch.object(mirror, 'metadata', return_value=actual), \
                 patch.object(mirror, 'fingerprint', return_value=('old', 1)), \
                 patch.object(mirror.subprocess, 'check_output', return_value=json.dumps(prior), side_effect=error):
                with self.assertRaises(RuntimeError):
                    mirror.check_latest('cos', self.root, self.verified, self.config, self.root)

    def test_first_release_requires_absence_or_exact_current_metadata(self):
        MemoryPath.texts['previous-release.json'] = json.dumps({'missing': True})
        for actual, allowed in [(None, True), (('current', 1), True), (('unknown', 1), False)]:
            with patch.object(mirror, 'metadata', return_value=actual), \
                 patch.object(mirror, 'fingerprint', return_value=('current', 1)):
                if allowed:
                    mirror.check_latest('r2', self.root, self.verified, self.config, self.root)
                else:
                    with self.assertRaises(RuntimeError):
                        mirror.check_latest('r2', self.root, self.verified, self.config, self.root)

    def test_immutable_mismatch_never_uploads(self):
        with patch.object(mirror, 'metadata', return_value=('other', 1)), \
             patch.object(mirror, 'fingerprint', return_value=('expected', 1)), \
             patch.object(mirror, 'cos_client') as client:
            with self.assertRaises(RuntimeError):
                mirror.upload('cos', 'lees-cad/asset', self.root, 'https://unused.invalid/')
            client.assert_not_called()

    def test_existing_identical_asset_is_idempotent(self):
        with patch.object(mirror, 'metadata', return_value=('expected', 1)), \
             patch.object(mirror, 'fingerprint', return_value=('expected', 1)), \
             patch.object(mirror.subprocess, 'run') as put:
            mirror.upload('r2', 'lees-cad/asset', self.root, 'https://unused.invalid/')
            put.assert_not_called()

    def test_r2_upload_and_failed_readback_never_download(self):
        with patch.object(mirror, 'metadata', side_effect=[None] + [('bad', 1)] * 5) as listing, \
             patch.object(mirror, 'fingerprint', return_value=('expected', 1)), \
             patch.object(mirror, 'env', return_value='bucket'), patch.object(mirror, 'r2_account', return_value='account'), \
             patch.object(mirror.time, 'sleep'), patch.object(mirror.subprocess, 'run') as put:
            with self.assertRaisesRegex(RuntimeError, 'body download is forbidden'):
                mirror.upload('r2', 'lees-cad/asset', self.root, 'https://unused.invalid/')
            self.assertEqual(listing.call_count, 6)
            self.assertEqual(put.call_args.args[0][7:10], ['r2', 'object', 'put'])
            self.assertEqual(put.call_count, 1)

    def test_upload_uses_single_cos_put_and_metadata_readback(self):
        file = Mock(); file.open.return_value.__enter__ = Mock(return_value='body')
        file.open.return_value.__exit__ = Mock()
        with patch.object(mirror, 'metadata', side_effect=[None, ('expected', 1)]) as head, \
             patch.object(mirror, 'fingerprint', return_value=('expected', 1)), \
             patch.object(mirror, 'env', return_value='bucket'), patch.object(mirror, 'cos_client') as client:
            mirror.upload('cos', 'lees-cad/asset', file, 'https://unused.invalid/download/')
            self.assertEqual(head.call_count, 2)
            client.return_value.put_object.assert_called_once_with(Bucket='bucket', Key='download/lees-cad/asset',
                Body='body', EnableMD5=True, CacheControl='public, max-age=31536000, immutable')
            client.return_value.get_object.assert_not_called()
            client.return_value.upload_file.assert_not_called()


if __name__ == '__main__':
    unittest.main()
