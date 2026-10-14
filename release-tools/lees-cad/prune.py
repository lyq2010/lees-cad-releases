"""Keep the signed current CAD release; prune only validated older CAD artifact keys."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from mirror import NoRedirect, digest, env, public

PREFIX = "lees-cad/releases/"
VERSION = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)")


def names(version):
    binaries = [f"lees-cad-{version}-windows-x64.msi",
                f"lees-cad-{version}-macos-aarch64.dmg", f"lees-cad-{version}-macos-aarch64.app.tar.gz",
                f"lees-cad-cli-{version}-macos-aarch64.zip"]
    # Published 0.1.0 included a portable ZIP; later releases must still be able to prune it.
    if version == "0.1.0":
        binaries.append(f"lees-cad-{version}-windows-x64-portable.zip")
    return set(binaries + [name + ".minisig" for name in binaries] +
               ["windows-x86_64.json", "darwin-aarch64.json", "release-manifest.json", "SHA256SUMS", "verification.json"])


def plan(keys, current, prefix=PREFIX):
    if not VERSION.fullmatch(current):
        raise RuntimeError("Invalid current release version")
    result = []
    for key in sorted(set(keys)):
        if not key.startswith(prefix):
            raise RuntimeError("Object listing escaped the CAD release prefix")
        parts = key[len(prefix):].split("/")
        if len(parts) != 2 or not VERSION.fullmatch(parts[0]) or (parts[1] and parts[1] not in names(parts[0])):
            raise RuntimeError("Unexpected object requires explicit review")
        version = parts[0]
        if tuple(map(int, version.split("."))) > tuple(map(int, current.split("."))):
            raise RuntimeError("A newer staged release must not be deleted")
        if version != current:
            result.append(key)
    return result


def cos_keys(client, bucket, prefix):
    marker, seen, keys = "", set(), []
    while True:
        page = client.list_objects(Bucket=bucket, Prefix=prefix, Marker=marker, MaxKeys=1000)
        rows = page.get("Contents", [])
        keys.extend(row["Key"] for row in rows)
        if len(keys) > 10000:
            raise RuntimeError("CAD object inventory exceeds limit")
        if page.get("IsTruncated", "false") == "false":
            return keys
        cursor = page.get("NextMarker") or (rows[-1]["Key"] if rows else None)
        if not cursor or cursor in seen:
            raise RuntimeError("Invalid COS pagination")
        marker = cursor
        seen.add(cursor)


def r2_keys(request, path, prefix):
    cursor, seen, keys = "", set(), []
    while True:
        query = {"prefix": prefix, "per_page": 1000}
        if cursor:
            query["cursor"] = cursor
        page = request(path + "?" + urllib.parse.urlencode(query))
        if not page.get("success") or not isinstance(page.get("result"), list):
            raise RuntimeError("R2 object listing failed")
        keys.extend(row["key"] for row in page["result"])
        if len(keys) > 10000:
            raise RuntimeError("CAD object inventory exceeds limit")
        info = page.get("result_info", {})
        if not info.get("is_truncated", False):
            return keys
        cursor = info.get("cursor")
        if not cursor or cursor in seen:
            raise RuntimeError("Invalid R2 pagination")
        seen.add(cursor)


def same_latest(config, expected):
    for field in ("cosBaseUrl", "r2BaseUrl"):
        url = urllib.parse.urljoin(config[field], "lees-cad/stable/latest.json")
        if public(url, limit=65536) != expected:
            raise RuntimeError("Both live latest pointers must match the verified release")


def main():
    source, folder = sys.argv[1:]
    if source not in ("cos", "r2"):
        raise RuntimeError("Invalid cleanup mirror")
    root = Path(folder)
    script = Path(__file__).parent
    verified = json.loads(subprocess.check_output(["node", str(script / "verify.mjs"), str(root)], text=True))
    current = verified["payload"]["version"]
    config = json.loads((script / "public-config.json").read_text())
    expected = digest(root / "release-manifest.json")
    same_latest(config, expected)
    if source == "cos":
        from qcloud_cos import CosConfig, CosS3Client
        client = CosS3Client(CosConfig(Region=env("TENCENT_COS_REGION"), SecretId=env("TENCENT_COS_SECRET_ID"),
                                      SecretKey=env("TENCENT_COS_SECRET_KEY"), Scheme="https"))
        bucket = env("TENCENT_COS_BUCKET")
        base_prefix = urllib.parse.urlsplit(config["cosBaseUrl"]).path.strip("/")
        prefix = (base_prefix + "/" if base_prefix else "") + PREFIX
        listing = lambda: cos_keys(client, bucket, prefix)
        remove = lambda key: client.delete_object(Bucket=bucket, Key=key)
    else:
        token = env("CF_API_TOKEN")

        def request(path, method="GET"):
            headers = {"Authorization": "Bearer " + token}
            if method == "DELETE":
                headers["cf-r2-data-catalog-check"] = "true"
            req = urllib.request.Request("https://api.cloudflare.com/client/v4/" + path, headers=headers, method=method)
            with urllib.request.build_opener(NoRedirect).open(req, timeout=30) as response:
                data = response.read(4 * 1024 * 1024 + 1)
            if len(data) > 4 * 1024 * 1024:
                raise RuntimeError("R2 API response exceeds limit")
            result = json.loads(data) if data else {"success": True}
            if not result.get("success"):
                raise RuntimeError("R2 API operation failed")
            return result

        account = os.environ.get("CF_ACCOUNT_ID", "").strip()
        if not account:
            accounts = request("accounts")["result"]
            if len(accounts) != 1:
                raise RuntimeError("A unique R2 account is required")
            account = accounts[0]["id"]
        path = "accounts/" + account + "/r2/buckets/" + urllib.parse.quote(env("R2_BUCKET"), safe="") + "/objects"
        prefix = PREFIX
        listing = lambda: r2_keys(request, path, prefix)
        remove = lambda key: request(path + "/" + urllib.parse.quote(key, safe="/"), method="DELETE")
    keys = listing()
    required = {prefix + current + "/" + name for name in verified["assets"]}
    if not required.issubset(keys):
        raise RuntimeError("Current release assets are missing from the mirror inventory")
    candidates = plan(keys, current, prefix)
    # Recheck the signed publication immediately before destructive operations.
    same_latest(config, expected)
    for key in candidates:
        remove(key)
    remaining = listing()
    if plan(remaining, current, prefix) or not required.issubset(remaining):
        raise RuntimeError("Old CAD artifacts remain after cleanup")
    same_latest(config, expected)
    report = {"source": source, "version": current, "policy": "latest_only", "prefix": prefix,
              "deleted": candidates, "current_release_preserved": True, "result": "passed"}
    (root / f"cleanup-{source}.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
