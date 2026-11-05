"""
Write data_snapshot/: a copy of the openly licensed sources (data_utils.SNAPSHOT_SOURCES) and the country list,
committed with the app. A new process with no disk cache (a redeploy, Streamlit Community Cloud waking a
sleeping app) shows it at once while the sources are fetched in the background (data_utils, "Background
refresh"), so no visitor waits for the download. The other sources (ND-GAIN, World Happiness Report, SWIID)
name no licence and are not redistributed (DATA_SOURCES.md): they load in the background after a restart.

    python make_snapshot.py

Fetches every snapshot source from its publisher and writes the files only if all of them succeed (else
it changes nothing and exits with 1). Run it now and then and commit the result: the app works with an old
snapshot too (it is replaced by fresh data within seconds of a restart), but the newer the snapshot, the
closer the first page after a restart is to the current data.
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import json
import sys

import data_utils as du
import sources as ds


def main() -> int:
    keys = list(du.SNAPSHOT_SOURCES)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(keys) + 1) as executor:
        futures = {key: executor.submit(ds.SOURCES[key]["fetch"], du._SESSION) for key in keys}
        countries_future = executor.submit(du.fetch_countries)
        results, failed = {}, []
        for key, future in futures.items():
            try:
                results[key] = future.result()
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{key}: {type(exc).__name__}: {exc}")
        try:
            countries = countries_future.result()
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{du.COUNTRIES_SOURCE}: {type(exc).__name__}: {exc}")
    if failed:
        print("Not written, these failed:\n  " + "\n  ".join(failed), file=sys.stderr)
        return 1

    out = du._SNAPSHOT_DIR
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.parquet"):  # a source dropped from SNAPSHOT_SOURCES goes too
        old.unlink()
    now = dt.datetime.now().replace(microsecond=0).isoformat()
    saved, updates = {}, {}
    for key, (table, updated) in results.items():
        table.to_parquet(out / du._source_cache_file(key).name, index=False, compression="zstd")
        saved[key], updates[key] = now, updated.isoformat() if updated else None
        print(f"{key}: {len(table):,} rows, released {updates[key]}")
    countries.to_parquet(out / du._COUNTRIES_CACHE_FILE.name, index=False, compression="zstd")
    saved[du.COUNTRIES_SOURCE] = now
    print(f"{du.COUNTRIES_SOURCE}: {len(countries)} rows")
    du._SNAPSHOT_MANIFEST.write_text(json.dumps({"saved": saved, "updates": updates}, indent=1) + "\n",
                                     encoding="utf-8")
    size = sum(f.stat().st_size for f in out.iterdir()) / 1e6
    print(f"Wrote {out} ({size:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
