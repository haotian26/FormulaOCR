"""Collect versioned dependency notices into a built app, before code signing.

Missing wheel/crate notices are read from the matching source archive or commit.
Downloads happen at build time only. No credentials or user files are inspected.
"""
import argparse
import hashlib
import importlib.metadata as metadata
import io
import json
import re
import subprocess
import sys
import tarfile
import tomllib
import urllib.request
from pathlib import Path
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
PREFIXES = ("license", "licence", "copying", "copyright", "notice", "thirdpartynotice")


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent":"FormulaOCR-license-build"}), timeout=45) as response:
        data = response.read(30_000_001)
    if len(data) > 30_000_000:
        raise ValueError("License source archive exceeds the build-time size limit")
    return data


def notice(path):
    return Path(path).name.lower().startswith(PREFIXES)


def collect(destination):
    destination.mkdir(parents=True, exist_ok=True)
    inventory = []
    def save(kind, name, version, source, files):
        if not files:
            raise ValueError(f"No license text found for {name} {version}")
        folder = destination / kind / re.sub(r"[^A-Za-z0-9._-]", "_", name + "-" + version)
        folder.mkdir(parents=True, exist_ok=True)
        entries = []
        for index, (filename, data) in enumerate(files):
            target = folder / (str(index) + "-" + Path(filename).name)
            target.write_bytes(data)
            entries.append({"path":str(target.relative_to(destination)), "sha256":hashlib.sha256(data).hexdigest()})
        inventory.append({"kind":kind, "name":name, "version":version, "source":source, "notices":entries})

    # Frontend production dependency tree (a superset of tree-shaken JS).
    paths = subprocess.check_output(["npm", "ls", "--omit=dev", "--all", "--parseable"], cwd=ROOT, text=True).splitlines()
    for directory in sorted(set(paths) - {str(ROOT)}):
        path = Path(directory)
        package = json.loads((path / "package.json").read_text())
        files = [(p.name, p.read_bytes()) for p in sorted(path.iterdir()) if p.is_file() and notice(p)]
        if not files:
            details = json.loads(fetch(f'https://registry.npmjs.org/{package["name"]}/{package["version"]}'))
            repository = details["repository"]
            repository = repository["url"] if isinstance(repository, dict) else repository
            repository = repository.removeprefix("git+").rstrip("/").removesuffix(".git")
            if not repository.startswith("https://github.com/"):
                raise ValueError("Missing local license for " + package["name"])
            repo = repository.removeprefix("https://github.com/")
            commit = details["gitHead"]
            # This npm version references an unpublished gitHead. Pin the
            # repository's license revision instead of following a moving branch.
            if (package["name"], package["version"]) == ("react-remove-scroll-bar", "2.3.8"):
                commit = "7301c160fda44cb8cf2b9fdfde61efad35736196"
            listing = json.loads(fetch(f"https://api.github.com/repos/{repo}/contents?ref={commit}"))
            files = [(item["name"], fetch(item["download_url"])) for item in listing if item["type"] == "file" and notice(item["name"])]
        save("javascript", package["name"], package["version"], "https://www.npmjs.com/package/" + package["name"], files)

    # Python's installed production closure, excluding optional development extras.
    requirements = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]
    queue, visited = list(requirements), set()
    queue.append("pyinstaller")  # distributed bootloader and its exception
    while queue:
        requirement = Requirement(queue.pop())
        if requirement.marker and not requirement.marker.evaluate({"extra":""}):
            continue
        distribution = metadata.distribution(requirement.name)
        name, version = distribution.metadata["Name"], distribution.version
        key = re.sub(r"[-_.]+", "-", name.lower())
        if key in visited:
            continue
        visited.add(key)
        if key != "pyinstaller":
            queue.extend(distribution.requires or [])
        files = [(str(f), distribution.locate_file(f).read_bytes()) for f in distribution.files or [] if notice(f) and distribution.locate_file(f).is_file()]
        source = f"https://pypi.org/project/{name}/{version}/"
        if not files and key.startswith("pyobjc-framework-"):
            core = metadata.distribution("pyobjc-core")
            if core.version != version:
                raise ValueError("PyObjC framework/core versions differ")
            files = [(str(f), core.locate_file(f).read_bytes()) for f in core.files or [] if notice(f) and core.locate_file(f).is_file()]
        if not files and key == "flatbuffers":
            files = [("LICENSE", fetch(f"https://raw.githubusercontent.com/google/flatbuffers/v{version}/LICENSE"))]
        if not files:
            details = json.loads(fetch(f"https://pypi.org/pypi/{name}/{version}/json"))
            archive = next(item for item in details["urls"] if item["packagetype"] == "sdist")
            data = fetch(archive["url"])
            if hashlib.sha256(data).hexdigest() != archive["digests"]["sha256"]:
                raise ValueError(f"Source digest mismatch for {name}")
            with tarfile.open(fileobj=io.BytesIO(data)) as contents:
                files = [(member.name, contents.extractfile(member).read()) for member in contents.getmembers() if member.isfile() and notice(member.name)]
        if not files and key == "latex2mathml":
            files = [("LICENSE", fetch(f"https://raw.githubusercontent.com/roniemartinez/latex2mathml/{version}/LICENSE"))]
        save("python", name, version, source, files)
    base = Path(sys.base_prefix)
    python_license = next(path / "LICENSE" for path in [base, *list(base.parents)[:4]] if (path / "LICENSE").is_file())
    save("python", "CPython", sys.version.split()[0], "https://www.python.org/", [("LICENSE", python_license.read_bytes())])

    # Cargo's platform-filtered resolved graph, including build-time notices.
    cargo = "/opt/homebrew/opt/rustup/bin/cargo"
    graph = json.loads(subprocess.check_output([cargo,"metadata","--locked","--offline","--format-version","1","--filter-platform","aarch64-apple-darwin","--manifest-path",str(ROOT / "src-tauri/Cargo.toml")], cwd=ROOT))
    active = {node["id"] for node in graph["resolve"]["nodes"]}
    upstream = {}
    for package in graph["packages"]:
        if package["id"] not in active or package["name"] == "formulaocr":
            continue
        path = Path(package["manifest_path"]).parent
        files = [(str(p.relative_to(path)), p.read_bytes()) for p in sorted(path.rglob("*")) if p.is_file() and notice(p)]
        if not files:
            vcs = json.loads((path / ".cargo_vcs_info.json").read_text())["git"]["sha1"]
            repository = package["repository"].rstrip("/").removesuffix(".git")
            if not repository.startswith("https://github.com/"):
                raise ValueError("Missing local license for " + package["name"])
            key = (repository, vcs)
            if key not in upstream:
                repo = repository.removeprefix("https://github.com/")
                listing = json.loads(fetch(f"https://api.github.com/repos/{repo}/contents?ref={vcs}"))
                upstream[key] = [(item["name"], fetch(item["download_url"])) for item in listing if item["type"] == "file" and notice(item["name"])]
            files = upstream[key]
        if not files and package["license"] == "MPL-2.0":
            # Some Mozilla crates reference MPL-2.0 in their source headers
            # without shipping a standalone copy. Retain the full common text.
            mpl = next(p for p in (destination / "rust").rglob("*") if p.is_file() and p.read_bytes().startswith(b"Mozilla Public License Version 2.0"))
            files = [("LICENSE-MPL-2.0", mpl.read_bytes())]
        source = f'https://crates.io/crates/{package["name"]}/{package["version"]}'
        save("rust", package["name"], package["version"], source, files)
    # The model is Apache-2.0; retain the full license from a bundled Apache crate.
    apache = next(p for p in (destination / "rust").rglob("*") if p.is_file() and "apache" in p.name.lower())
    save("model", "PP-FormulaNet_plus-L", "RapidDoc-v1.0.0", "https://www.modelscope.cn/models/RapidAI/RapidDoc/resolve/v1.0.0/formula/PP-FormulaNet_plus-L/pp_formulanet_plus_l.onnx", [("LICENSE-APACHE-2.0", apache.read_bytes())])
    (destination / "SOURCES.json").write_text(json.dumps(inventory, indent=2) + "\n")
    print(f"Collected notices for {len(inventory)} components")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app", type=Path)
    args = parser.parse_args()
    resources = args.app / "Contents/Resources"
    collect(resources / "licenses")
    for name in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"):
        (resources / name).write_bytes((ROOT / name).read_bytes())
