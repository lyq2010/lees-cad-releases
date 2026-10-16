"""Withdraw only the original 0.1.0 authorized by the maintainer on 2026-10-14."""
import json
import os
from pathlib import Path
import subprocess
import sys
from mirror import digest
from storage import cos_client, cos_key, env, fingerprint, metadata, r2_account

root = Path(sys.argv[1])
script = Path(__file__).parent
verified = json.loads(subprocess.check_output(["node", str(script / "verify.mjs"), str(root)], text=True))
payload = verified["payload"]
if payload["version"] != "0.1.0" or payload["sourceRevision"] != "3b47debec72a7aeeefcdb59de740e25236f0c8ad":
    raise RuntimeError("Only the original 0.1.0 may be withdrawn")
manifest_digest = digest(root / "release-manifest.json")
expected = fingerprint(root / "release-manifest.json")
if manifest_digest[0] != "b1e32ab2c1ef3cab109b59be1e1f41e194885ace747d02b79052445f94df6b1d":
    raise RuntimeError("Original manifest differs")
config = json.loads((script / "public-config.json").read_text())
bases = {"cos": config["cosBaseUrl"], "r2": config["r2BaseUrl"]}
files = {"lees-cad/releases/0.1.0/" + name: root / name for name in verified["assets"]}
latest = "lees-cad/stable/latest.json"
# Complete both-source preflight before the first external deletion.
for source, base in bases.items():
    if metadata(source, latest, base) not in (None, expected):
        raise RuntimeError("A different latest must not be removed")
    for key, file in files.items():
        if metadata(source, key, base) not in (None, fingerprint(file)):
            raise RuntimeError("A different immutable asset must not be removed")

cos = cos_client()
r2_env = os.environ.copy()
r2_env["CLOUDFLARE_API_TOKEN"] = env("CF_API_TOKEN")
r2_env["CLOUDFLARE_ACCOUNT_ID"] = r2_account()

def remove(source, key):
    base = bases[source]
    if metadata(source, key, base) is None:
        return
    if source == "cos":
        cos.delete_object(Bucket=env("TENCENT_COS_BUCKET"), Key=cos_key(base, key))
    else:
        subprocess.run(["npm", "exec", "--yes", "--package", "wrangler@4.90.0", "--", "wrangler", "r2", "object", "delete",
                        env("R2_BUCKET") + "/" + key, "--remote", "--force"], env=r2_env, check=True, timeout=90)
    if metadata(source, key, base) is not None:
        raise RuntimeError("Withdrawn object still exists in mirror metadata")

# Remove both update pointers before withdrawing any package.
for source in bases:
    remove(source, latest)
for source in bases:
    for key in files:
        remove(source, key)
print("Original CAD 0.1.0 withdrawn: both latest pointers and 14 allowlisted objects per mirror")
