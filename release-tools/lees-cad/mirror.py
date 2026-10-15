"""CAD-only immutable uploads; derived from Mail behavior, independently implemented."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
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


def public(url, limit=512 * 1024 * 1024):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 LeesCADRelease/1", "Cache-Control": "no-cache"})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            digest, size = hashlib.sha256(), 0
            while block := response.read(1024 * 1024):
                size += len(block)
                if size > limit:
                    raise RuntimeError("Mirror object oversized")
                digest.update(block)
            return digest.hexdigest(), size
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def digest(file):
    with file.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest(), file.stat().st_size


def upload(source, key, file, base, mutable=False):
    expected, url = digest(file), urllib.parse.urljoin(base, key)
    existing = public(url)
    if existing == expected:
        return
    if existing is not None and not mutable:
        raise RuntimeError("Immutable CAD asset differs")
    cache = "no-cache" if mutable else "public, max-age=31536000, immutable"
    if source == "cos":
        from qcloud_cos import CosConfig, CosS3Client
        client = CosS3Client(CosConfig(Region=env("TENCENT_COS_REGION"), SecretId=env("TENCENT_COS_SECRET_ID"), SecretKey=env("TENCENT_COS_SECRET_KEY"), Scheme="https"))
        prefix = urllib.parse.urlsplit(base).path.strip("/")
        object_key = prefix + "/" + key if prefix else key
        client.upload_file(Bucket=env("TENCENT_COS_BUCKET"), Key=object_key, LocalFilePath=str(file), EnableMD5=True, CacheControl=cache)
    else:
        process_env = os.environ.copy()
        process_env["CLOUDFLARE_API_TOKEN"] = env("CF_API_TOKEN")
        account = os.environ.get("CF_ACCOUNT_ID", "").strip()
        if not account:
            request = urllib.request.Request("https://api.cloudflare.com/client/v4/accounts", headers={"Authorization": "Bearer " + env("CF_API_TOKEN")})
            with urllib.request.urlopen(request, timeout=15) as response:
                result = json.load(response)
            if not result.get("success") or len(result.get("result", [])) != 1:
                raise RuntimeError("Set an explicit CF_ACCOUNT_ID for the R2 release account")
            account = result["result"][0]["id"]
        process_env["CLOUDFLARE_ACCOUNT_ID"] = account
        subprocess.run(["npm", "exec", "--yes", "--package", "wrangler@4.90.0", "--", "wrangler", "r2", "object", "put", f'{env("R2_BUCKET")}/{key}', "--file", str(file), "--remote", "--cache-control", cache], env=process_env, check=True)
    for attempt in range(5):
        if public(url) == expected:
            return
        if attempt < 4:
            time.sleep(2 ** attempt)
    raise RuntimeError("Full public GET readback differs")


def check_latest(s, root, verified, config, script):
    url = urllib.parse.urljoin(config["cosBaseUrl" if s == "cos" else "r2BaseUrl"], "lees-cad/stable/latest.json")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 LeesCADRelease/1", "Cache-Control": "no-cache"})
        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            previous = response.read(65537)
        if len(previous) > 65536:
            raise RuntimeError("Previous latest oversized")
        old = root / f"previous-{s}.json"
        old.write_bytes(previous)
        prior = json.loads(subprocess.check_output(["node", str(script / "verify.mjs"), "--manifest", str(old)], text=True))
        version = lambda value: tuple(map(int, value.split(".")))
        if version(prior["payload"]["version"]) > version(verified["payload"]["version"]) or (prior["payload"]["version"] == verified["payload"]["version"] and prior["payloadSha256"] != verified["payloadSha256"]):
            raise RuntimeError("Refusing downgrade or equal-version conflict")
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise


def promote(root, verified, files, config, script):
    p = verified["payload"]
    readiness = [json.loads((root / f"readiness-{s}.json").read_text()) for s in ("cos", "r2")]
    for s, row in zip(("cos", "r2"), readiness):
        if row != {"source": s, "verified": True, "version": p["version"], "payloadSha256": verified["payloadSha256"], "runId": env("GITHUB_RUN_ID")}:
            raise RuntimeError("Both independent mirror jobs must agree")
    # Full readback of both immutable sources once, before either latest changes.
    for s in ("cos", "r2"):
        origin = config["cosBaseUrl" if s == "cos" else "r2BaseUrl"]
        for key, file in files.items():
            if public(urllib.parse.urljoin(origin, key)) != digest(file):
                raise RuntimeError("Mirror readiness no longer holds")
        check_latest(s, root, verified, config, script)
    for s in ("cos", "r2"):
        # Latest is small and mutable: recheck immediately before each write.
        check_latest(s, root, verified, config, script)
        base = config["cosBaseUrl" if s == "cos" else "r2BaseUrl"]
        upload(s, "lees-cad/stable/latest.json", root / "release-manifest.json", base, mutable=True)


def main():
    mode, source, folder = sys.argv[1:]
    if (mode == "stage" and source not in ("cos", "r2")) or (mode == "promote" and source != "both") or mode not in ("stage", "promote"):
        raise RuntimeError("Invalid mirror operation")
    root = Path(folder)
    script = Path(__file__).parent
    verified = json.loads(subprocess.check_output(["node", str(script / "verify.mjs"), str(root)], text=True))
    p = verified["payload"]
    prefix = f'lees-cad/releases/{p["version"]}/'
    # The verifier emits a strict public allowlist, never a checkout glob.
    files = {prefix + name: root / name for name in verified["assets"]}
    config = json.loads((script / "public-config.json").read_text())
    base = config["cosBaseUrl" if source == "cos" else "r2BaseUrl"]
    if mode == "stage":
        for key, file in files.items():
            upload(source, key, file, base)
        (root / f"readiness-{source}.json").write_text(json.dumps({"source": source, "verified": True, "version": p["version"], "payloadSha256": verified["payloadSha256"], "runId": env("GITHUB_RUN_ID")}) + "\n")
        return
    promote(root, verified, files, config, script)


if __name__ == "__main__":
    main()
