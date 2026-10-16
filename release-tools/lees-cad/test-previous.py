"""Previous release references may come from GitHub only and must be signed."""
import sys
sys.dont_write_bytecode = True
import io
import json
import unittest
import urllib.error
from unittest.mock import Mock, patch
import previous


class MemoryPath:
    texts = {}

    def __init__(self, name):
        self.name = name

    def __truediv__(self, name):
        return MemoryPath(name)

    def __str__(self):
        return self.name

    def write_text(self, value):
        self.texts[self.name] = json.loads(value)


class PreviousTests(unittest.TestCase):
    def setUp(self):
        MemoryPath.texts = {}
        self.root = MemoryPath('root')
        self.tag = 'lees-cad-v0.1.2'
        self.release = {'tag_name': self.tag, 'draft': False, 'prerelease': False,
                        'assets': [{'name': 'release-manifest.json', 'size': 100}]}

    def test_signed_reference_download_is_github_only(self):
        reply = Mock(); reply.__enter__ = Mock(return_value=reply); reply.__exit__ = Mock()
        reply.read.return_value = json.dumps(self.release).encode()
        prior = {'payload': {'releaseId': self.tag}}
        with patch.object(previous, 'env', return_value='token'), \
             patch.object(previous.urllib.request, 'build_opener') as opener, \
             patch.object(previous.subprocess, 'run') as download, \
             patch.object(previous.subprocess, 'check_output', return_value=json.dumps(prior)):
            opener.return_value.open.return_value = reply
            previous.prepare(self.root, self.root)
            self.assertEqual(opener.return_value.open.call_args.args[0].full_url,
                             'https://api.github.com/repos/lyq2010/lees-cad-releases/releases/latest')
            self.assertEqual(download.call_args.args[0], ['gh', 'release', 'download', self.tag, '--repo',
                'lyq2010/lees-cad-releases', '--pattern', 'release-manifest.json', '--output', 'previous-release-manifest.json'])
            self.assertEqual(MemoryPath.texts['previous-release.json'], {'releaseId': self.tag})

    def test_only_github_404_is_first_release(self):
        for code in (404, 403, 500):
            self.setUp()
            with patch.object(previous, 'env', return_value='token'), \
                 patch.object(previous.urllib.request, 'build_opener') as opener, \
                 patch.object(previous.subprocess, 'run') as download:
                error = urllib.error.HTTPError('https://api.github.com/', code, '', {}, io.BytesIO())
                self.addCleanup(error.close)
                opener.return_value.open.side_effect = error
                if code == 404:
                    previous.prepare(self.root, self.root)
                    self.assertEqual(MemoryPath.texts['previous-release.json'], {'missing': True})
                else:
                    with self.assertRaises(urllib.error.HTTPError): previous.prepare(self.root, self.root)
                    self.assertEqual(MemoryPath.texts, {})
                download.assert_not_called()

    def test_invalid_signature_or_release_identity_prevents_reference(self):
        for result, error in [({'payload': {'releaseId': 'different'}}, None), ({}, RuntimeError('signature'))]:
            reply = Mock(); reply.__enter__ = Mock(return_value=reply); reply.__exit__ = Mock()
            reply.read.return_value = json.dumps(self.release).encode()
            with patch.object(previous, 'env', return_value='token'), \
                 patch.object(previous.urllib.request, 'build_opener') as opener, \
                 patch.object(previous.subprocess, 'run'), \
                 patch.object(previous.subprocess, 'check_output', return_value=json.dumps(result), side_effect=error):
                opener.return_value.open.return_value = reply
                with self.assertRaises(RuntimeError): previous.prepare(self.root, self.root)
                self.assertEqual(MemoryPath.texts, {})

    def test_invalid_assets_prevent_download(self):
        for assets in ([], [{'name': 'release-manifest.json', 'size': 65537}], self.release['assets'] * 2):
            self.release['assets'] = assets
            reply = Mock(); reply.__enter__ = Mock(return_value=reply); reply.__exit__ = Mock()
            reply.read.return_value = json.dumps(self.release).encode()
            with patch.object(previous, 'env', return_value='token'), \
                 patch.object(previous.urllib.request, 'build_opener') as opener, patch.object(previous.subprocess, 'run') as download:
                opener.return_value.open.return_value = reply
                with self.assertRaises(RuntimeError): previous.prepare(self.root, self.root)
                download.assert_not_called()


if __name__ == '__main__':
    unittest.main()
