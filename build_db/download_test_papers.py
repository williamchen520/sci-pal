"""
Batch download test papers: OpenAlex → Crossref → Unpaywall.

V19.6 — use ISSN for Crossref (not journal name):
  1. OpenAlex: get journal name + ISSN_l, save to data/journal_list.json
  2. Crossref: /journals/{issn}/works → get OA DOIs
  3. Unpaywall: DOI → PDF URL → download

Usage:
  cd /home/kokomi/sciPal && source venv_sciPal/bin/activate
  python -m build_db.download_test_papers
"""
import json
import re
import sys
import time
import requests
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# ------------------------------------------------------------------
DOWNLOAD_DIR = project_root / "documents"
DATA_DIR = project_root / "data"
JOURNAL_LIST_FILE = DATA_DIR / "journal_list.json"

PROXY = "http://127.0.0.1:7890"
PROXIES = {"http": PROXY, "https": PROXY}
OPENALEX = "https://api.openalex.org"
CROSSREF = "https://api.crossref.org/journals"
UNPAYWALL = "https://api.unpaywall.org/v2"
MAILTO = "chenwei-ucas@outlook.com"

BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
API_UA = "SciPal-Downloader/0.1 (mailto:chenwei-ucas@outlook.com)"

NUM_JOURNALS = 100
PAPERS_PER_JOURNAL = 1
REQUEST_DELAY = 0.5


def get_journals_from_openalex(n: int = 100) -> list[dict]:
    """Get OA biology journals with ISSN from OpenAlex."""
    try:
        params = {
            "search": "biology",
            "filter": "is_oa:true",
            "per-page": n,
            "mailto": MAILTO,
        }
        r = requests.get(f"{OPENALEX}/sources", params=params,
                         proxies=PROXIES,
                         headers={"User-Agent": API_UA}, timeout=20)
        data = r.json()
        results = data.get("results", [])
        journals = []
        for s in results:
            issn = s.get("issn_l")
            name = s.get("display_name", "")
            if issn and name:
                journals.append({"name": name, "issn": issn})
        if journals:
            JOURNAL_LIST_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(JOURNAL_LIST_FILE, "w") as f:
                json.dump(journals, f, ensure_ascii=False, indent=2)
            print(f"   Saved {len(journals)} journals to {JOURNAL_LIST_FILE}")
        return journals
    except Exception as e:
        print(f"   (OpenAlex error: {e})")
        return []


def load_journal_list() -> list[dict]:
    """Load journal list: OpenAlex first, then JSON cache."""
    journals = get_journals_from_openalex(NUM_JOURNALS)
    if journals:
        return journals

    if JOURNAL_LIST_FILE.exists():
        with open(JOURNAL_LIST_FILE) as f:
            journals = json.load(f)
        print(f"   Loaded {len(journals)} journals from {JOURNAL_LIST_FILE}")
        return journals

    print("   ⚠️  Using built-in fallback list")
    return [
        {"name": "PLOS Biology", "issn": "1545-7885"},
        {"name": "PLOS ONE", "issn": "1932-6203"},
        {"name": "Nature Communications", "issn": "2041-1723"},
        {"name": "eLife", "issn": "2050-084X"},
        {"name": "BMC Biology", "issn": "1741-7007"},
    ]


def search_crossref(issn: str, n: int = 1) -> list[dict]:
    """Search Crossref for recent OA papers by ISSN."""
    try:
        url = f"{CROSSREF}/{issn}/works"
        params = {
            "filter": "has-full-text:true,type:journal-article,from-pub-date:2024-01-01",
            "rows": n * 3,
            "sort": "published",
            "order": "desc",
            "mailto": MAILTO,
            "select": "DOI,title",
        }
        r = requests.get(url, params=params,
                         proxies=PROXIES,
                         headers={"User-Agent": API_UA}, timeout=20)
        if r.status_code != 200:
            return []
        items = r.json().get("message", {}).get("items", [])
        results = []
        for item in items:
            doi = item.get("DOI", "")
            title = (item.get("title") or [""])[0][:80]
            if doi:
                results.append({"doi": doi, "title": title})
            if len(results) >= n:
                break
        return results
    except Exception:
        return []


def find_pdf_url(doi: str) -> str | None:
    """Unpaywall: DOI → direct PDF URL (free)."""
    try:
        r = requests.get(f"{UNPAYWALL}/{doi}", params={"email": MAILTO},
                         proxies=PROXIES, headers={"User-Agent": API_UA}, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        best = data.get("best_oa_location") or {}
        if best.get("url_for_pdf"):
            return best["url_for_pdf"]
        for loc in data.get("oa_locations", []):
            if loc.get("url_for_pdf"):
                return loc["url_for_pdf"]
        return None
    except Exception:
        return None


def safe_filename(title: str, doi: str) -> str:
    t = re.sub(r'[^\w\s-]', '', title)[:50].strip()
    t = re.sub(r'\s+', '_', t)
    doi_safe = re.sub(r'[^A-Za-z0-9.-]', '_', doi)
    return f"{t}_{doi_safe}.pdf"


def download_pdf(url: str, filepath: Path) -> bool:
    if filepath.exists():
        return True
    headers = {"User-Agent": BROWSER_UA,
               "Accept": "application/pdf,*/*",
               "Accept-Language": "en-US,en;q=0.9"}
    try:
        r = requests.get(url, proxies=PROXIES, headers=headers,
                         timeout=60, allow_redirects=True, stream=True)
        if r.status_code != 200:
            print(f"  ❌ HTTP {r.status_code}")
            return False
        first = next(r.iter_content(chunk_size=10), b"")
        if not first.startswith(b"%PDF"):
            print(f"  ❌ not PDF")
            return False
        with open(filepath, "wb") as f:
            f.write(first)
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"  ✅ {filepath.name} ({filepath.stat().st_size/1024:.0f} KB)")
        return True
    except Exception as e:
        print(f"  ❌ {str(e)[:50]}")
        return False


def main():
    print("=" * 70)
    print("📥 OpenAlex → Crossref (ISSN) → Unpaywall")
    print("=" * 70)

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n🔍 Step 1: Getting journal list with ISSN...")
    journals = load_journal_list()
    print(f"   {len(journals)} journals to process")

    total_done = 0
    total_fail = 0

    for i, j in enumerate(journals, 1):
        name = j["name"]
        issn = j["issn"]
        print(f"\n[{i}/{len(journals)}] {name} (ISSN: {issn})")

        # Step 2: Crossref by ISSN
        time.sleep(REQUEST_DELAY)
        papers = search_crossref(issn, n=PAPERS_PER_JOURNAL)
        if not papers:
            print(f"  ⚠️  no papers found")
            total_fail += 1
            continue

        # Step 3: Unpaywall → PDF URL → download
        jdir = DOWNLOAD_DIR / re.sub(r'[^\w]', '_', name)[:40]
        jdir.mkdir(parents=True, exist_ok=True)

        for p in papers:
            doi = p["doi"]
            title = p["title"]
            time.sleep(REQUEST_DELAY)
            pdf_url = find_pdf_url(doi)
            if not pdf_url:
                print(f"  ⚠️  no PDF for {title[:40]}")
                continue
            time.sleep(REQUEST_DELAY)
            fpath = jdir / safe_filename(title, doi)
            if download_pdf(pdf_url, fpath):
                total_done += 1
            else:
                total_fail += 1

    print("\n" + "=" * 70)
    print(f"✅ Done: {total_done} downloaded, {total_fail} failed")
    print("=" * 70)


if __name__ == "__main__":
    main()
