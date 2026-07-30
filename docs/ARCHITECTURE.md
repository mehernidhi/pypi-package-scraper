# Architecture

A function-by-function walkthrough of `pypi_package_scraper.py`.

---

## Imports & Constants

| Import | Role |
|---|---|
| `argparse` | Reads the package name from the command line |
| `ast` | Parses `setup.py` into a syntax tree to find `install_requires` |
| `re` | Regex fallback for `setup.py`, and filename matching for `requirements.txt` |
| `sys` | Used by `die()` to exit with a non-zero status |
| `tarfile`, `zipfile` | Read `.tar.gz` sdists and `.whl` archives without extracting to disk |
| `pathlib.Path` | Filesystem paths |
| `requests` | The only external dependency; all HTTP calls to PyPI |

`PYPI_API` is the endpoint template — `{}` is replaced with the package name at runtime.

---

## Helper Functions

### `die(msg)`
Centralised error exit. Prints a prefixed message and terminates immediately. Having one exit path keeps the four step functions free of scattered `sys.exit` calls.

### `requires_dist(text) -> list[str]`
Takes the raw text of any `METADATA` or `PKG-INFO` file and returns the value of every `Requires-Dist:` line. Case-insensitive on the key, and strips whitespace from the value. Works identically for wheels and sdists because both use the same Core Metadata format.

### `parse_install_requires(source) -> list[str]`
Two-tier extraction from `setup.py`:

1. **AST pass (preferred).** Walks the syntax tree looking for a call to `setup()`, then reads the `install_requires` keyword argument. Only string literals (`ast.Constant`) are collected — computed values are skipped rather than guessed at.
2. **Regex fallback.** If the file raises a `SyntaxError` (Python 2 syntax, encoding issues, deliberate malformation), a regex scrapes anything that looks like a quoted string inside `install_requires = [...]`.

The AST pass is correct but brittle; the regex pass is loose but resilient. Together they cover more real-world `setup.py` files than either alone.

---

## Core Step Functions

### `fetch_version(package) -> (version, release_urls)`
Hits the PyPI JSON API. Handles three failure modes explicitly — connection error, timeout, and non-200 status, with 404 given its own message since "package doesn't exist" is a different problem from "PyPI is down". Returns the latest version string and the list of distribution files for that version.

### `download(package, version, urls) -> list[Path]`
Filters the release URLs down to `.whl` and `.tar.gz` files, then streams each one to the current working directory in 8 KB chunks. Files that already exist are skipped rather than re-fetched — reruns are cheap and work offline against a previous download.

### `extract_deps(files) -> dict[str, list[str]]`
The core of the tool. For each downloaded file:

- **`.whl`** → open as a zip, locate the `*/METADATA` member, parse `Requires-Dist`.
- **`.tar.gz`** → open as a gzipped tar, then run three passes: `PKG-INFO`/`METADATA`, `setup.py`, and `requirements*.txt`.

Results are keyed by a human-readable source label (`"METADATA (requests-2.33.1-py3-none-any.whl)"`) so provenance survives into the report. A nested `read_tar_member` helper takes a predicate and returns the first matching member's decoded contents, which keeps the three tar passes to one line each.

Archive-level failures (`BadZipFile`, `TarError`) are caught per file — a corrupt sdist doesn't prevent the wheel from being analysed.

### `report(package, version, files, sources)`
Deduplicates across all sources with a set, prints the sorted master list, then prints each source's contribution separately. The second half is what makes the tool useful for analysis rather than just inventory.

---

## Entry Point

`main()` sequences the four steps and prints a `[n/4]` progress marker before each, so a long download doesn't look like a hang. The `if __name__ == "__main__"` guard ensures `main()` runs only on direct invocation, leaving the module importable for testing.

---

## Design Notes

**Why label sources instead of merging?** A dependency found only in `requirements.txt` is a development dependency. One found only in `setup.py` but absent from `METADATA` suggests a build that didn't regenerate metadata. One present in the sdist but missing from the wheel is worth a second look. Merging silently destroys all three signals.

**Why not extract archives to disk?** Reading members in memory avoids writing attacker-controlled paths to the filesystem — relevant given the tool's intended use on untrusted packages.
