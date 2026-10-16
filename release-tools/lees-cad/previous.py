"""Obtain the previous signed reference from GitHub, never from a storage bucket."""
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request
from storage import NoRedirect, env

REPOSITORY = "lyq2010/lees-cad-releases"


def prepare(root, script):
    request = urllib.request.Request("https://api.github.com/repos/" + REPOSITORY + "/releases/latest",
        headers={"Authorization": "Bearer " + env("GH_TOKEN"), "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            body = response.read(1024 * 1024 + 1)
        if len(body) > 1024 * 1024:
            raise RuntimeError("GitHub release metadata oversized")
        release = json.loads(body)
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        error.close()
        (root / "previous-release.json").write_text(json.dumps({"missing": True}) + "\n")
        return
    assets = [a for a in release["assets"] if a["name"] == "release-manifest.json"]
    if not re.fullmatch(r"lees-cad-v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", release["tag_name"]) or release["draft"] or release["prerelease"] or len(assets) != 1 or not 0 < assets[0]["size"] <= 65536:
        raise RuntimeError("Invalid previous GitHub release")
    previous = root / "previous-release-manifest.json"
    subprocess.run(["gh", "release", "download", release["tag_name"], "--repo", REPOSITORY,
                    "--pattern", "release-manifest.json", "--output", str(previous)], check=True)
    prior = json.loads(subprocess.check_output(["node", str(script / "verify.mjs"), "--manifest", str(previous)], text=True))
    if prior["payload"]["releaseId"] != release["tag_name"]:
        raise RuntimeError("Previous signed manifest differs from GitHub release")
    (root / "previous-release.json").write_text(json.dumps({"releaseId": release["tag_name"]}) + "\n")


if __name__ == "__main__":
    prepare(Path(sys.argv[1]), Path(__file__).parent)
