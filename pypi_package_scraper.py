
import argparse
import ast
import re
import sys
import tarfile
import zipfile
from pathlib import Path

import requests

PYPI_API = "https://pypi.org/pypi/{}/json"

def die(msg: str):
    sys.exit(f"[ERROR] {msg}")


def requires_dist(text: str) -> list[str]:
    return [
        line.split(":", 1)[1].strip()
        for line in text.splitlines()
        if line.lower().startswith("requires-dist:")
    ]


def parse_install_requires(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fname = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
                if fname == "setup":
                    for kw in node.keywords:
                        if kw.arg == "install_requires" and isinstance(kw.value, (ast.List, ast.Tuple)):
                            return [e.value for e in kw.value.elts if isinstance(e, ast.Constant)]
    except SyntaxError:
        pass
    m = re.search(r"install_requires\s*=\s*\[([^\]]*)\]", source, re.DOTALL)
    return re.findall(r'[\'"]([^\'"]+)[\'"]', m.group(1)) if m else []


def fetch_version(package: str) -> tuple[str, dict]:
    """Step 1 — Query PyPI and return (latest_version, release_urls)."""
    try:
        r = requests.get(PYPI_API.format(package), timeout=15)
    except requests.exceptions.ConnectionError:
        die("Network error: cannot reach PyPI.")
    except requests.exceptions.Timeout:
        die("Request timed out.")
    if r.status_code == 404:
        die(f"Package '{package}' not found on PyPI.")
    if r.status_code != 200:
        die(f"PyPI returned HTTP {r.status_code}.")
    data = r.json()
    version = data["info"]["version"]
    return version, data["releases"].get(version, [])


def download(package: str, version: str, urls: list[dict]) -> list[Path]:
    targets = [u for u in urls if u["filename"].endswith((".whl", ".tar.gz"))]
    if not targets:
        die(f"No .whl or .tar.gz found for {package}=={version}.")

    files: list[Path] = []
    for dist in targets:
        dest = Path.cwd() / dist["filename"]
        if dest.exists():
            print(f"  [skip]     {dest.name}")
        else:
            print(f"  [download] {dest.name} ...", end=" ", flush=True)
            r = requests.get(dist["url"], timeout=60, stream=True)
            r.raise_for_status()
            dest.write_bytes(b"".join(r.iter_content(8192)))
            print("done.")
        files.append(dest)
    return files


def extract_deps(files: list[Path]) -> dict[str, list[str]]:
    sources: dict[str, list[str]] = {}

    def read_tar_member(tf, name_filter):
        for m in tf.getmembers():
            if name_filter(m.name):
                f = tf.extractfile(m)
                return f.read().decode("utf-8", errors="replace") if f else ""
        return ""

    for fp in files:
        try:
            if fp.suffix == ".whl":
                with zipfile.ZipFile(fp) as zf:
                    meta_names = [n for n in zf.namelist() if n.endswith("/METADATA")]
                    if meta_names:
                        text = zf.read(meta_names[0]).decode("utf-8", errors="replace")
                        if deps := requires_dist(text):
                            sources[f"METADATA ({fp.name})"] = deps

            elif fp.name.endswith(".tar.gz"):
                with tarfile.open(fp, "r:gz") as tf:
                    text = read_tar_member(tf, lambda n: n.endswith(("PKG-INFO", "METADATA")))
                    if deps := requires_dist(text):
                        sources[f"PKG-INFO ({fp.name})"] = deps

                    # setup.py
                    text = read_tar_member(tf, lambda n: n.endswith("setup.py"))
                    if deps := parse_install_requires(text):
                        sources[f"setup.py ({fp.name})"] = deps

                    # requirements.txt
                    text = read_tar_member(tf, lambda n: re.search(r"requirements.*\.txt$", n, re.I))
                    if deps := [l for l in text.splitlines() if l.strip() and not l.startswith(("#", "-"))]:
                        sources[f"requirements.txt ({fp.name})"] = deps

        except (zipfile.BadZipFile, tarfile.TarError) as e:
            print(f"  [warn] Could not read {fp.name}: {e}")

    return sources


def report(package: str, version: str, files: list[Path], sources: dict[str, list[str]]):
    sep = "=" * 55
    print(f"\n{sep}")
    print(f"  Package : {package}  (v{version})")
    print(f"  Files   : {', '.join(f.name for f in files)}")
    print(sep)

    if not sources:
        print("  No dependencies found.\n")
        return

    all_deps = sorted({d for deps in sources.values() for d in deps})
    print(f"\n  Direct Dependencies ({len(all_deps)} unique)")
    print("  " + "-" * 40)
    for dep in all_deps:
        print(f"    {dep}")

    print(f"\n  By Source")
    print("  " + "-" * 40)
    for src, deps in sources.items():
        print(f"\n  [{src}]")
        for dep in deps:
            print(f"    {dep}")
    print(f"\n{sep}\n")

def main():
    parser = argparse.ArgumentParser(description="PyPI package dependency inspector.")
    parser.add_argument("package", help="PyPI package name (e.g. requests)")
    args = parser.parse_args()
    pkg = args.package.strip().lower()

    print(f"\n[1/4] Fetching latest version of '{pkg}' from PyPI ...")
    version, urls = fetch_version(pkg)
    print(f"      Version: {version}")

    print(f"\n[2/4] Downloading to {Path.cwd()} ...")
    files = download(pkg, version, urls)

    print(f"\n[3/4] Extracting dependencies ...")
    sources = extract_deps(files)

    print(f"\n[4/4] Report")
    report(pkg, version, files, sources)


if __name__ == "__main__":
    main()
