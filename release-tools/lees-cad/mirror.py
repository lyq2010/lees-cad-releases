"""CAD-only immutable uploads; derived from Mail behavior, independently implemented."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from storage import cos_client, cos_key, env, fingerprint, metadata, r2_account


def digest(file):
    with file.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest(), file.stat().st_size


def upload(source, key, file, base, mutable=False):
    expected = fingerprint(file)
    existing = metadata(source, key, base)
    if existing == expected:
        return
    if existing is not None and not mutable:
        raise RuntimeError("Immutable CAD asset differs")
    cache = "no-cache" if mutable else "public, max-age=31536000, immutable"
    if source == "cos":
        # One PUT keeps the ETag comparable to local MD5; never multipart.
        with file.open("rb") as body:
            cos_client().put_object(Bucket=env("TENCENT_COS_BUCKET"), Key=cos_key(base, key),
                                    Body=body, EnableMD5=True, CacheControl=cache)
    else:
        process_env = os.environ.copy()
        process_env["CLOUDFLARE_API_TOKEN"] = env("CF_API_TOKEN")
        process_env["CLOUDFLARE_ACCOUNT_ID"] = r2_account()
        subprocess.run(["npm", "exec", "--yes", "--package", "wrangler@4.90.0", "--", "wrangler", "r2", "object", "put", f'{env("R2_BUCKET")}/{key}', "--file", str(file), "--remote", "--cache-control", cache], env=process_env, check=True)
    for attempt in range(5):
        if metadata(source, key, base) == expected:
            return
        if attempt < 4:
            time.sleep(2 ** attempt)
    raise RuntimeError("Mirror metadata differs; body download is forbidden")


def check_latest(s, root, verified, config, script):
    # The previous signed manifest comes only from GitHub, never the mirrors.
    reference = json.loads((root / "previous-release.json").read_text())
    candidates = {fingerprint(root / "release-manifest.json")}
    if reference != {"missing": True}:
        old = root / "previous-release-manifest.json"
        prior = json.loads(subprocess.check_output(["node", str(script / "verify.mjs"), "--manifest", str(old)], text=True))
        if reference != {"releaseId": prior["payload"]["releaseId"]}:
            raise RuntimeError("Previous GitHub release identity differs")
        version = lambda value: tuple(map(int, value.split(".")))
        if version(prior["payload"]["version"]) > version(verified["payload"]["version"]) or (prior["payload"]["version"] == verified["payload"]["version"] and prior["payloadSha256"] != verified["payloadSha256"]):
            raise RuntimeError("Refusing downgrade or equal-version conflict")
        candidates.add(fingerprint(old))
    base = config["cosBaseUrl" if s == "cos" else "r2BaseUrl"]
    actual = metadata(s, "lees-cad/stable/latest.json", base)
    if actual not in candidates and not (actual is None and reference == {"missing": True}):
        raise RuntimeError("Latest metadata does not match a locally verified manifest")


def promote(root, verified, files, config, script):
    p = verified["payload"]
    readiness = [json.loads((root / f"readiness-{s}.json").read_text()) for s in ("cos", "r2")]
    for s, row in zip(("cos", "r2"), readiness):
        if row != {"source": s, "verified": True, "version": p["version"], "payloadSha256": verified["payloadSha256"], "runId": env("GITHUB_RUN_ID")}:
            raise RuntimeError("Both independent mirror jobs must agree")
    # Recheck both immutable inventories without transferring any object bodies.
    for s in ("cos", "r2"):
        origin = config["cosBaseUrl" if s == "cos" else "r2BaseUrl"]
        for key, file in files.items():
            if metadata(s, key, origin) != fingerprint(file):
                raise RuntimeError("Mirror readiness no longer holds")
        check_latest(s, root, verified, config, script)
    for s in ("cos", "r2"):
        # Recheck pointer metadata immediately before each write.
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
