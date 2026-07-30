<h1 align="center">PyPI Package Scraper</h1>

<p align="center">
  <em>See every dependency a PyPI package declares — from every place it declares them.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/dependencies-requests-orange" alt="Dependencies: requests">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License: MIT">
  <img src="https://img.shields.io/badge/domain-supply%20chain%20security-red" alt="Supply chain security">
</p>

---

Most dependency tools read one metadata file and call it a day. Real packages aren't that tidy — a wheel's `METADATA`, an sdist's `PKG-INFO`, a legacy `setup.py`, and a bundled `requirements.txt` routinely disagree with each other.

**Those disagreements are the interesting part.** This tool pulls all four, labels each dependency with where it came from, and shows you the delta.

Built as Part 1 of a software supply chain security assessment.

---

## Demo

```console
$ python pypi_package_scraper.py requests

[1/4] Fetching latest version of 'requests' from PyPI ...
      Version: 2.33.1

[2/4] Downloading to /home/analyst/scans ...
  [download] requests-2.33.1-py3-none-any.whl ... done.
  [download] requests-2.33.1.tar.gz ... done.

[3/4] Extracting dependencies ...

[4/4] Report

=======================================================
  Package : requests  (v2.33.1)
  Files   : requests-2.33.1-py3-none-any.whl, requests-2.33.1.tar.gz
=======================================================

  Direct Dependencies (12 unique)
  ----------------------------------------
    PySocks!=1.5.7,>=1.5.6; extra == "socks"
    certifi>=2023.5.7
    chardet<8,>=3.0.2; extra == "use-chardet-on-py3"
    charset_normalizer<4,>=2
    httpbin~=0.10.0
    idna<4,>=2.5
    pytest-cov
    pytest-httpbin==2.1.0
    pytest>=2.8.0,<9
    trustme
    urllib3<3,>=1.26
    wheel

  By Source
  ----------------------------------------

  [METADATA (requests-2.33.1-py3-none-any.whl)]
    charset_normalizer<4,>=2
    idna<4,>=2.5
    urllib3<3,>=1.26
    certifi>=2023.5.7
    PySocks!=1.5.7,>=1.5.6; extra == "socks"
    chardet<8,>=3.0.2; extra == "use-chardet-on-py3"

  [PKG-INFO (requests-2.33.1.tar.gz)]
    charset_normalizer<4,>=2
    idna<4,>=2.5
    urllib3<3,>=1.26
    certifi>=2023.5.7
    PySocks!=1.5.7,>=1.5.6; extra == "socks"
    chardet<8,>=3.0.2; extra == "use-chardet-on-py3"

  [requirements.txt (requests-2.33.1.tar.gz)]
    pytest>=2.8.0,<9
    pytest-cov
    pytest-httpbin==2.1.0
    httpbin~=0.10.0
    trustme
    wheel

=======================================================
```

Note what the per-source breakdown surfaces: six of the twelve "dependencies" are test-only packages that appear **exclusively** in the bundled `requirements.txt`. A scanner reading only `METADATA` would miss them entirely — and a scanner reading only `requirements.txt` would report `pytest` as a runtime dependency of `requests`. Provenance is the point.

---

## Quick Start

```bash
git clone https://github.com/<mehernidhi>/pypi-package-scraper.git
cd pypi-package-scraper
pip install -r requirements.txt

python pypi_package_scraper.py requests
```

Requires Python 3.10+ (the code uses `list[str]` built-in generics and the walrus operator).

---

## How It Works

| Step | Stage | What happens |
|:---:|---|---|
| 1 | **Fetch** | Queries the PyPI JSON API for the latest stable version and its release URLs |
| 2 | **Download** | Streams every `.whl` and `.tar.gz` to disk in 8 KB chunks; skips files already present |
| 3 | **Extract** | Runs four parsing passes across the downloaded archives |
| 4 | **Report** | Prints a deduplicated master list, then a per-source breakdown |

### The four metadata sources

| Source | Lives in | Why it's parsed |
|---|---|---|
| `METADATA` | `.whl` | Most reliable. Standard for every modern package. |
| `PKG-INFO` / `METADATA` | `.tar.gz` | Source-distribution equivalent; can drift from the wheel. |
| `setup.py` → `install_requires` | `.tar.gz` | Legacy packages declare deps only here. Parsed via AST, with a regex fallback. |
| `requirements.txt` | `.tar.gz` | Often dev/test deps — informative, but *not* the same as runtime deps. |

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Package not on PyPI (404) | Exits with a clear message |
| Network unreachable / timeout | Exits with a clear message |
| Non-200 from PyPI | Exits, reporting the status code |
| File already downloaded | Skips the download, still re-extracts |
| Missing `setup.py` / `requirements.txt` | Silently skips that source |
| Corrupted or unreadable archive | Warns and continues with the remaining files |

---

## Security Relevance

The tool maps the **declared** dependency surface of a package before you install it:

- Reveals unpinned or loosely pinned dependencies — the ground condition for dependency-confusion attacks
- Exposes drift between wheel and sdist metadata, which is itself a signal worth investigating
- Produces raw, diffable metadata for comparing a suspect package against its legitimate namesake
- Surfaces the author, homepage, and version-history fields from the JSON response for threat-intel enrichment

---

## Roadmap — Detecting What a Package *Does*

The current tool reads what a package **says about itself**. Every sophisticated supply chain attack lives in the gap between that declaration and actual runtime behaviour.

[**→ docs/SCALABILITY.md**](docs/SCALABILITY.md) works through three extensions that close specific evasion gaps:

| Idea | Gap it closes |
|---|---|
| **`setup.py` body scanner** | Payloads hide in the install script's body, not the dependency list |
| **Base64 blob detector** | Size-thresholded flagging of `b64decode()` calls — the most common obfuscation in PyPI malware |
| **Typosquatting detection** | Levenshtein distance against a top-package list catches `reqeusts`, `flask-dev`, `numpy-core` |

Each is documented with rationale and reference pseudocode.

Also planned:

- [ ] `--output-dir` flag instead of writing to the current working directory
- [ ] `--json` output for piping into other tooling
- [ ] Recursive resolution for transitive dependencies
- [ ] Batch mode for scanning a package list

---

## Limitations

Stated plainly, because a security tool that overstates its coverage is worse than no tool:

- **Direct dependencies only.** Transitive dependencies require recursive resolution, which is not implemented.
- **Static analysis only.** If `install_requires` is assembled at runtime from a variable or function call, AST parsing cannot see it.
- **One package per invocation.** Batch scanning requires an external loop.
- **`requirements.txt` deps are reported alongside runtime deps** in the master list. The per-source breakdown is what disambiguates them — read it, not just the summary.

---

## Repository Layout

```
pypi-package-scraper/
├── .github/workflows/ci.yml    # Lint + smoke test on push
├── docs/
│   ├── ARCHITECTURE.md         # Function-by-function walkthrough
│   └── SCALABILITY.md          # Security-driven extension proposals
├── pypi_package_scraper.py     # The tool
├── requirements.txt
├── .gitignore
├── LICENSE
└── README.md
```

---

## License

MIT — see [LICENSE](LICENSE).
