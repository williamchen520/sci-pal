"""
Resolve missing DOIs for references in the Sci-Pal database.

V18.1 - Offline-first, visible-file cache, concurrent CrossRef lookup.

Strategy (agreed design):
  1. Offline pass: re-scan citation.raw_text with extract_doi() — free, instant.
  2. Visible file cache: data/doi_cache.json (you can open it, see it, back it up).
  3. CrossRef:      cache miss → concurrent api.crossref.org lookup
                    (12 workers, ~12 req/sec via polite pool).
                    Validate top result's title similarity before accepting DOI.
  4. Write-back:    update citations.doi + append to doi_cache.json. Resumable.

Why a JSON file instead of a SQLite table:
  - Visible on disk in data/ — you'll never forget it exists.
  - Easy to inspect, back up, or delete intentionally.
  - Survives a fresh research.db rebuild (as long as you keep doi_cache.json).

Usage:
  cd /path/to/sciPal && source .venv/bin/activate
  # Proxy must be UP (127.0.0.1:7890)
  python -m build_db.resolve_ref_dois
"""
import json
import re
import sys
import time
import sqlite3
import threading
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from build_db.build_database import extract_doi

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------
DB_PATH = project_root / "data" / "research.db"
CACHE_PATH = project_root / "data" / "doi_cache.json"
CROSSREF_API = "https://api.crossref.org/works"
PROXY = "http://127.0.0.1:7890"

# Concurrency: CrossRef polite pool allows ~50 req/sec.
# 12 workers ≈ 10-15 req/sec effective (overseas latency limits us, not CrossRef).
MAX_WORKERS = 12
TITLE_MATCH_THRESHOLD = 0.75
MAX_QUERY_WORDS = 12
SAVE_EVERY = 10          # flush cache.json every N results
HTTP_RETRY_DELAY = 5     # seconds to wait on HTTP 429 / 5xx
HTTP_MAX_RETRIES = 2

USER_AGENT = "SciPal/0.1 (mailto:researcher@example.org)"

# Lock for the shared cache dict (reads are GIL-safe, but writes during
# concurrent ThreadPoolExecutor need a lock to avoid lost updates).
_cache_lock = threading.Lock()


# ------------------------------------------------------------------
# Visible JSON cache
# ------------------------------------------------------------------
def load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"  ⚠️  Could not read {CACHE_PATH.name}: {e} — starting fresh.")
    return {}


def save_cache(cache: dict):
    # Snapshot under the lock so worker threads don't mutate while json.dump iterates
    with _cache_lock:
        snapshot = dict(cache)
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    tmp.replace(CACHE_PATH)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def normalize_title(title: str) -> str:
    if not title:
        return ""
    t = title.lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def title_similarity(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def crossref_lookup(title: str) -> dict | None:
    """Query CrossRef with retry on 429 / 5xx."""
    try:
        import requests
    except ImportError:
        print("  ❌ requests not installed. pip install requests")
        return None

    short = " ".join(title.split()[:MAX_QUERY_WORDS])
    params = {"query.bibliographic": short, "rows": 1, "select": "DOI,title"}
    proxies = {"http": PROXY, "https": PROXY}
    headers = {"User-Agent": USER_AGENT}

    for attempt in range(HTTP_MAX_RETRIES + 1):
        try:
            r = requests.get(
                CROSSREF_API, params=params, headers=headers,
                proxies=proxies, timeout=20,
            )
            if r.status_code == 200:
                items = r.json().get("message", {}).get("items", [])
                if not items:
                    return None
                item = items[0]
                cr_doi = item.get("DOI")
                cr_title = (item.get("title") or [""])[0]
                return {"doi": cr_doi, "title": cr_title} if cr_doi else None
            elif r.status_code == 429 or 500 <= r.status_code < 600:
                if attempt < HTTP_MAX_RETRIES:
                    time.sleep(HTTP_RETRY_DELAY * (attempt + 1))
                    continue
                return None
            else:
                return None
        except Exception:
            if attempt < HTTP_MAX_RETRIES:
                time.sleep(HTTP_RETRY_DELAY * (attempt + 1))
                continue
            return None
    return None


# ------------------------------------------------------------------
# Worker: resolve one citation (runs in a thread)
# ------------------------------------------------------------------
def resolve_one(cid: str, title: str, cache: dict) -> tuple:
    """Returns (citation_id, doi_or_None, status_str).
    Thread-safe: only touches the shared cache under a lock for writes."""
    t_norm = normalize_title(title)
    if not t_norm:
        return (cid, None, "empty_title")

    # 1. Check cache (read under lock)
    with _cache_lock:
        entry = cache.get(t_norm)
    if entry is not None:
        return (cid, entry.get("doi"), f"cache:{entry.get('source', '?')}")

    # 2. Cache miss → CrossRef
    result = crossref_lookup(title)

    if result is None:
        with _cache_lock:
            cache[t_norm] = {
                "doi": None, "title_raw": title[:200],
                "source": "crossref_miss",
                "resolved_at": datetime.now().isoformat(),
            }
        return (cid, None, "miss")

    # 3. Validate title similarity
    sim = title_similarity(title, result["title"])
    if sim >= TITLE_MATCH_THRESHOLD:
        with _cache_lock:
            cache[t_norm] = {
                "doi": result["doi"], "title_raw": result["title"][:200],
                "source": "crossref",
                "resolved_at": datetime.now().isoformat(),
            }
        return (cid, result["doi"], f"hit:{sim:.2f}")
    else:
        with _cache_lock:
            cache[t_norm] = {
                "doi": None, "title_raw": result["title"][:200],
                "source": "crossref_rejected",
                "resolved_at": datetime.now().isoformat(),
            }
        return (cid, None, f"rejected:{sim:.2f}")


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def main():
    print("=" * 70)
    print("🔗 Resolve Reference DOIs — V18.1 (concurrent)")
    print("=" * 70)

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    cache = load_cache()
    print(f"📁 Cache file: {CACHE_PATH}")
    print(f"   Entries already cached: {len(cache)}")
    print(f"   Workers: {MAX_WORKERS} concurrent")

    # --- Step 0: offline DOI re-scan ---
    print("\n📶 Step 0: Offline re-scan of raw_text for DOIs...")
    cur.execute("SELECT citation_id, raw_text FROM citations WHERE doi IS NULL OR doi = ''")
    missing = cur.fetchall()
    print(f"  Citations missing DOI: {len(missing)}")

    offline_fixed = 0
    for cid, raw in missing:
        if not raw:
            continue
        found = extract_doi(raw)
        if found:
            cur.execute("UPDATE citations SET doi = ? WHERE citation_id = ?", (found, cid))
            offline_fixed += 1
    conn.commit()
    print(f"  ✅ Offline re-scan fixed: {offline_fixed}")

    # --- Step 1: collect unresolved citations with titles ---
    cur.execute("""
        SELECT citation_id, title FROM citations
        WHERE (doi IS NULL OR doi = '')
          AND title IS NOT NULL AND title != ''
    """)
    todo = cur.fetchall()
    print(f"\n🌐 Step 1: Need online lookup: {len(todo)}")

    cur.execute("""
        SELECT COUNT(*) FROM citations
        WHERE (doi IS NULL OR doi = '') AND (title IS NULL OR title = '')
    """)
    untitled = cur.fetchone()[0]
    if untitled:
        print(f"  ⚠️  {untitled} citations have no DOI and no title — cannot resolve online.")

    # --- Step 2: concurrent resolve ---
    eta_sec = len(todo) / MAX_WORKERS * 1.5  # rough: 1.5s per request per worker
    print(f"\n⚡ Step 2: Resolving with {MAX_WORKERS} workers "
          f"(~{len(todo)/MAX_WORKERS:.0f}s/worker, ETA ~{eta_sec/60:.1f} min)")
    print("-" * 70)

    cache_hits = 0
    online_hits = 0
    online_misses = 0
    rejected = 0
    processed = 0
    since_save = 0

    try:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(resolve_one, cid, title, cache): (cid, title)
                for cid, title in todo
            }
            for future in as_completed(futures):
                cid, title = futures[future]
                try:
                    result_cid, doi, status = future.result()
                except Exception as e:
                    print(f"  (thread error on {title[:40]}: {e})")
                    continue

                processed += 1
                since_save += 1

                # Update DB (single-threaded in main loop)
                if doi:
                    cur.execute("UPDATE citations SET doi = ? WHERE citation_id = ?",
                                (doi, result_cid))

                # Categorize
                if status.startswith("cache:"):
                    cache_hits += 1
                elif status.startswith("hit:"):
                    online_hits += 1
                elif status.startswith("rejected:"):
                    rejected += 1
                else:
                    online_misses += 1

                # Progress
                if processed % 25 == 0 or processed == len(todo):
                    print(f"  [{processed}/{len(todo)}] {title[:45]}  {status}")

                # Flush cache + DB periodically
                if since_save >= SAVE_EVERY:
                    save_cache(cache)
                    conn.commit()
                    since_save = 0

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted. Saving progress...")
        save_cache(cache)
        conn.commit()
        print(f"  ✅ Cache saved: {len(cache)} entries. DB committed.")
        print(f"  ✅ Processed {processed}/{len(todo)}. Re-run to resume.")
        conn.close()
        return

    # Final
    save_cache(cache)
    conn.commit()

    # --- Summary ---
    cur.execute("SELECT COUNT(*) FROM citations WHERE doi IS NOT NULL AND doi != ''")
    total_with_doi = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM citations")
    total_cites = cur.fetchone()[0]

    print("\n" + "=" * 70)
    print("📊 Resolution Summary")
    print("=" * 70)
    print(f"  Offline raw-text fixes:    {offline_fixed}")
    print(f"  Cache hits (reused):       {cache_hits}")
    print(f"  Online hits (CrossRef):    {online_hits}")
    print(f"  Online misses (not found): {online_misses}")
    print(f"  Rejected (title mismatch): {rejected}")
    print(f"  Cache file:                {CACHE_PATH} ({len(cache)} entries)")
    print(f"  ─────────────────────────────────────")
    print(f"  Citations WITH DOI:        {total_with_doi} / {total_cites} "
          f"({100*total_with_doi/total_cites:.1f}%)")
    print("=" * 70)
    print(f"\n💡 Cache is a visible file: {CACHE_PATH}")
    print("   - Open it anytime to inspect.")
    print("   - Keep it when you rebuild research.db.")
    print("   - Delete it intentionally only if you want to re-query everything.")

    conn.close()


if __name__ == "__main__":
    main()
