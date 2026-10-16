"""Authenticated metadata only: never read an object body from COS or R2."""
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, url):
        raise RuntimeError("Mirror redirect refused")


def env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing {name}")
    return value


def fingerprint(file):
    # SHA-256 and signatures are verified locally by verify.mjs. This MD5 is
    # only for comparison with a single-part object ETag, not a signature.
    with file.open("rb") as stream:
        return hashlib.file_digest(stream, "md5").hexdigest(), file.stat().st_size


def identity(etag, size):
    value = str(etag).lower()
    if len(value) == 34 and value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    if not re.fullmatch(r"[a-f0-9]{32}", value) or not re.fullmatch(r"\d+", str(size)):
        raise RuntimeError("Missing or unsupported object metadata; body download is forbidden")
    return value, int(size)


def cos_client():
    from qcloud_cos import CosConfig, CosS3Client
    return CosS3Client(CosConfig(Region=env("TENCENT_COS_REGION"), SecretId=env("TENCENT_COS_SECRET_ID"),
                               SecretKey=env("TENCENT_COS_SECRET_KEY"), Scheme="https"))


def cos_key(base, key):
    prefix = urllib.parse.urlsplit(base).path.strip("/")
    return prefix + "/" + key if prefix else key


def r2_request(path, method="GET"):
    # GET is restricted to management metadata endpoints. Object GET is never allowed.
    if method not in ("GET", "DELETE") or (method == "GET" and path != "accounts" and
            not re.fullmatch(r"accounts/[^/]+/r2/buckets/[^/]+/objects\?[^#]+", path)):
        raise RuntimeError("R2 object body access is forbidden")
    headers = {"Authorization": "Bearer " + env("CF_API_TOKEN")}
    if method == "DELETE":
        headers["cf-r2-data-catalog-check"] = "true"
    request = urllib.request.Request("https://api.cloudflare.com/client/v4/" + path, headers=headers, method=method)
    with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
        data = response.read(4 * 1024 * 1024 + 1)
    if len(data) > 4 * 1024 * 1024:
        raise RuntimeError("R2 metadata response exceeds limit")
    result = json.loads(data) if data else {"success": True}
    if not result.get("success"):
        raise RuntimeError("R2 metadata operation failed")
    return result


def r2_account():
    account = os.environ.get("CF_ACCOUNT_ID", "").strip()
    if not account:
        accounts = r2_request("accounts")["result"]
        if len(accounts) != 1:
            raise RuntimeError("A unique R2 account is required")
        account = accounts[0]["id"]
    if not re.fullmatch(r"[a-fA-F0-9]{32}", account):
        raise RuntimeError("Invalid R2 account")
    return account


def r2_path():
    return "accounts/" + r2_account() + "/r2/buckets/" + urllib.parse.quote(env("R2_BUCKET"), safe="") + "/objects"


def metadata(source, key, base):
    if not key.startswith("lees-cad/"):
        raise RuntimeError("Object key escaped CAD scope")
    if source == "cos":
        from qcloud_cos import CosServiceError
        try:
            row = cos_client().head_object(Bucket=env("TENCENT_COS_BUCKET"), Key=cos_key(base, key))
        except CosServiceError as error:
            if error.get_status_code() == 404:
                return None
            raise
        return identity(row.get("ETag"), row.get("Content-Length"))
    if source != "r2":
        raise RuntimeError("Invalid mirror source")
    path, cursor, seen, count = r2_path(), "", set(), 0
    while True:
        query = {"prefix": key, "per_page": 1000}
        if cursor:
            query["cursor"] = cursor
        page = r2_request(path + "?" + urllib.parse.urlencode(query))
        rows = page.get("result")
        if not isinstance(rows, list):
            raise RuntimeError("Invalid R2 metadata listing")
        count += len(rows)
        if count > 10000 or any(not row["key"].startswith(key) for row in rows):
            raise RuntimeError("Invalid R2 metadata scope or limit")
        matches = [row for row in rows if row["key"] == key]
        if len(matches) > 1:
            raise RuntimeError("Ambiguous R2 metadata")
        if matches:
            return identity(matches[0].get("etag"), matches[0].get("size"))
        info = page.get("result_info", {})
        if not info.get("is_truncated", False):
            return None
        cursor = info.get("cursor")
        if not cursor or cursor in seen:
            raise RuntimeError("Invalid R2 metadata pagination")
        seen.add(cursor)
