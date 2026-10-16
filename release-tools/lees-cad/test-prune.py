"""Regression checks for mirror cleanup scope, latest guard and complete pagination."""
import sys
sys.dont_write_bytecode = True
import unittest
from unittest.mock import Mock, patch
import prune


class PruneTests(unittest.TestCase):
    def test_keep_current_delete_old(self):
        old = "lees-cad/releases/0.1.0/lees-cad-0.1.0-windows-x64.msi"
        current = "lees-cad/releases/0.1.1/release-manifest.json"
        self.assertEqual(prune.plan([old, current], "0.1.1"), [old])

    def test_legacy_portable_and_signature_are_pruned(self):
        old = "lees-cad/releases/0.1.0/lees-cad-0.1.0-windows-x64-portable.zip"
        self.assertEqual(prune.plan([old, old + ".minisig"], "0.1.1"), [old, old + ".minisig"])
        self.assertEqual(prune.plan([old, old + ".minisig"], "0.1.0"), [])

    def test_new_portable_is_not_a_recognized_release_object(self):
        new = "lees-cad/releases/0.1.1/lees-cad-0.1.1-windows-x64-portable.zip"
        with self.assertRaises(RuntimeError): prune.plan([new], "0.1.1")

    def test_other_products_and_stable_never_deleted(self):
        for key in ("lees-mail/releases/0.1.0/file.msi", "lees-cad/stable/latest.json", "lees-cad/releases-other/0.1.0/file.msi"):
            with self.assertRaises(RuntimeError): prune.plan([key], "0.1.1")

    def test_unknown_paths_and_newer_staging_rejected(self):
        for key in ("lees-cad/releases/../release-manifest.json", "lees-cad/releases/0.1.0/private.dxf", "lees-cad/releases/0.1.2/release-manifest.json"):
            with self.assertRaises(RuntimeError): prune.plan([key], "0.1.1")

    def test_cos_base_path_and_pagination(self):
        client = Mock()
        client.list_objects.side_effect = [
            {"Contents": [{"Key": "download/lees-cad/releases/0.1.0/SHA256SUMS"}], "IsTruncated": "true", "NextMarker": "next"},
            {"Contents": [{"Key": "download/lees-cad/releases/0.1.1/SHA256SUMS"}], "IsTruncated": "false"}]
        keys = prune.cos_keys(client, "bucket", "download/lees-cad/releases/")
        self.assertEqual(len(keys), 2)
        self.assertEqual(prune.plan(keys, "0.1.1", "download/lees-cad/releases/"), [keys[0]])
        self.assertEqual(client.list_objects.call_args.kwargs["Marker"], "next")

    def test_r2_cursor_pagination(self):
        request = Mock(side_effect=[
            {"success": True, "result": [{"key": "lees-cad/releases/0.1.0/SHA256SUMS"}], "result_info": {"is_truncated": True, "cursor": "next"}},
            {"success": True, "result": [{"key": "lees-cad/releases/0.1.1/SHA256SUMS"}], "result_info": {"is_truncated": False}}])
        self.assertEqual(len(prune.r2_keys(request, "objects", prune.PREFIX)), 2)
        self.assertIn("cursor=next", request.call_args.args[0])

    def test_pagination_error_is_not_success(self):
        request = Mock(return_value={"success": True, "result": [], "result_info": {"is_truncated": True, "cursor": "same"}})
        with self.assertRaises(RuntimeError): prune.r2_keys(request, "objects", prune.PREFIX)

    def test_both_live_latest_are_required(self):
        config = {"cosBaseUrl": "https://cos.invalid/", "r2BaseUrl": "https://r2.invalid/"}
        with patch.object(prune, "metadata", side_effect=[("a", 1), ("b", 1)]):
            with self.assertRaises(RuntimeError): prune.same_latest(config, ("a", 1))


if __name__ == "__main__":
    unittest.main()
