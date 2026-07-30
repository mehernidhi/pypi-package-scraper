# Scalability — A Security & Evasion Perspective

> These are proposed extensions with reference pseudocode, not implemented features. Each one closes a specific gap that a malicious package author would exploit against a tool that reads metadata alone.

**Core insight:** most dependency scanners check what a package *says it is*. The ideas below check what a package *actually does*. The gap between declared identity and actual behaviour is where every sophisticated supply chain attack lives.

---

## 1. `setup.py` Body Scanner

**What:** Scan the full body of `setup.py` — not just `install_requires` — for dangerous imports and calls: `subprocess`, `socket`, `os.system`, `exec`, `eval`, `urllib`, `base64`.

**Why it matters:** Malicious packages hide their payload in the install script's body, not the dependency list. The dependency list looks clean; the execution logic doesn't. This is the pattern used by the `typing-unions` campaign.

```python
DANGEROUS_PATTERNS = [
    "import subprocess", "import socket", "import urllib",
    "import base64", "os.system", "exec(", "eval(",
]

def scan_setup_body(setup_source: str) -> list[str]:
    findings = []
    for i, line in enumerate(setup_source.splitlines(), start=1):
        for pattern in DANGEROUS_PATTERNS:
            if pattern in line:
                findings.append(f"  [!] Line {i}: '{pattern}' found → {line.strip()}")
    return findings


if findings := scan_setup_body(setup_source):
    print("SUSPICIOUS — dangerous patterns in setup.py:")
    for f in findings:
        print(f)
else:
    print("CLEAN — no dangerous patterns found")
```

**Known weakness:** substring matching produces false positives on legitimate build scripts (plenty of real packages shell out during install) and is trivially evaded by `getattr(__import__("os"), "system")`. Treat output as a triage signal for human review, not a verdict. An AST-based pass over `ast.Import` and `ast.Call` nodes would be the natural hardening step.

---

## 2. Base64 Blob Detector

**What:** Flag every `base64.b64decode()` call in `setup.py` and measure the length of the string being decoded. A short encoded string may be benign; a 50,000-character blob is almost certainly a payload.

**Why it matters:** Encoding is the most common obfuscation technique in PyPI malware. The heuristic is cheap to implement and size alone is a strong discriminator.

```python
import re

BLOB_SIZE_THRESHOLD = 500  # characters — above this is suspicious

def detect_base64_blobs(setup_source: str) -> list[str]:
    findings = []
    pattern = re.compile(r'b64decode\(["\']([A-Za-z0-9+/=]+)["\']\)')
    for match in pattern.finditer(setup_source):
        blob = match.group(1)
        size = len(blob)
        risk = "HIGH" if size > BLOB_SIZE_THRESHOLD else "LOW"
        findings.append(f"  [!] base64 blob detected — {size} chars — Risk: {risk}")
    return findings


if findings := detect_base64_blobs(setup_source):
    print("SUSPICIOUS — base64 payloads found:")
    for f in findings:
        print(f)
else:
    print("CLEAN — no base64 blobs detected")
```

**Known weakness:** only catches blobs passed as a string literal directly to `b64decode()`. A payload assigned to a variable first, split across concatenated strings, or read from a data file goes undetected. Scanning for long base64-shaped string literals *anywhere* in the file — independent of what consumes them — would catch considerably more.

---

## 3. Typosquatting Detection

**What:** Compare the requested package name against a list of top PyPI packages using edit distance. Flag names within one or two character edits of a well-known package.

**Why it matters:** `reqeusts`, `flask-dev`, `numpy-core` are real attack patterns. A one- or two-character difference from a legitimate, high-download package name is a high-confidence signal, and this check runs *before* anything is downloaded.

```python
# pip install python-Levenshtein
from Levenshtein import distance

TOP_PYPI_PACKAGES = [
    "requests", "numpy", "flask", "boto3", "pandas",
    "django", "scipy", "tensorflow", "pytest", "pydantic",
    "urllib3", "certifi", "setuptools", "pip", "cryptography",
    # expand as needed
]

EDIT_DISTANCE_THRESHOLD = 2

def detect_typosquat(package_name: str) -> list[str]:
    findings = []
    for legit in TOP_PYPI_PACKAGES:
        if package_name == legit:
            continue  # exact match — it's the real one
        d = distance(package_name, legit)
        if d <= EDIT_DISTANCE_THRESHOLD:
            findings.append(
                f"  [!] '{package_name}' is {d} edit(s) away from '{legit}' — possible typosquat"
            )
    return findings


if findings := detect_typosquat(package_name):
    print("WARNING — possible typosquatting:")
    for f in findings:
        print(f)
else:
    print("CLEAN — no known typosquat matches")
```

**Known weakness:** a threshold of 2 over short names is noisy — plenty of legitimate packages sit two edits from a popular one. Two refinements worth making: scale the threshold to name length (1 edit for names under six characters), and weight the finding by download count, since a near-miss name with fifty downloads is far more suspicious than one with fifty million.

---

## Where These Fit in the Pipeline

| Stage | Check |
|---|---|
| Before download | Typosquatting detection — cheapest possible check, runs on the name alone |
| After download, during extraction | `setup.py` body scan and base64 blob detection |
| In the report | A findings section alongside the dependency breakdown |

The typosquat check belongs first specifically because it needs no network fetch of the suspect package — it can warn before anything untrusted touches the disk.
