"""A new process with the committed snapshot (data_snapshot/) and no disk cache, as after a redeploy or a host
waking a sleeping app (2026-11-05): nobody waits for the download. load_data() returns at once with the
snapshot's sources while every source is fetched in the background; the sources with no copy
(ND-GAIN, WHR, SWIID: not redistributed) are "loading", named in a note at the top of the page, until the
fetch is done. Then the generation changes and the next load has everything. Also: a source with no copy
that fails in the background is an error from the next run on; the country list comes from the snapshot
too; and the page still waits when there is nothing at all to show."""
import _pathfix  # noqa: F401
import json
import shutil
import threading
import time
from unittest.mock import patch

import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

import data_utils as du
import sources as ds
from test_app2 import fake_get

NOT_IN_SNAPSHOT = set(ds.SOURCES) - set(du.SNAPSHOT_SOURCES)
assert NOT_IN_SNAPSHOT == {"NDGAIN", "WHR", "SWIID"}, NOT_IN_SNAPSHOT
SNAPSHOT_SAVED = "2026-01-15T10:00:00"


def write_snapshot():
    """A snapshot of the fake data, written the way make_snapshot.py writes the real one."""
    shutil.rmtree(du._SNAPSHOT_DIR, ignore_errors=True)  # else this load would go to the background
    du.wait_for_background_refresh()
    du.clear_disk_cache()
    st.cache_data.clear()
    with patch.object(du._SESSION, "get", side_effect=fake_get):
        du.load_data()
        du.load_countries()
    shutil.rmtree(du._SNAPSHOT_DIR, ignore_errors=True)
    du._SNAPSHOT_DIR.mkdir(parents=True)
    on_disk = json.loads(du._UPDATES_CACHE_FILE.read_text(encoding="utf-8"))
    for key in du.SNAPSHOT_SOURCES:
        name = du._source_cache_file(key).name
        shutil.copy(du._CACHE_DIR / name, du._SNAPSHOT_DIR / name)
    shutil.copy(du._COUNTRIES_CACHE_FILE, du._SNAPSHOT_DIR / du._COUNTRIES_CACHE_FILE.name)
    du._SNAPSHOT_MANIFEST.write_text(json.dumps({
        "saved": {key: SNAPSHOT_SAVED for key in [*du.SNAPSHOT_SOURCES, du.COUNTRIES_SOURCE]},
        "updates": {key: on_disk[key] for key in du.SNAPSHOT_SOURCES},
    }), encoding="utf-8")
    # The new process: no disk cache, nothing in memory
    du.clear_disk_cache()
    st.cache_data.clear()


write_snapshot()
gate = threading.Event()
calls = []


def gated_get(url, *args, **kwargs):
    """The network, held until the gate opens: whatever returns before that didn't wait for it."""
    assert gate.wait(60), "the network was held too long"
    calls.append(url)
    return fake_get(url, *args, **kwargs)


# --- 1. Nobody waits: the snapshot at once, the rest loading ---
with patch.object(du._SESSION, "get", side_effect=gated_get):
    start = time.time()
    generation = du.data_generation()
    data, errors = du.load_data()
    countries, country_errors = du.load_countries()
    assert time.time() - start < 20 and not calls, "load_data / load_countries waited for the network"
    assert errors == {} and country_errors == {}, (errors, country_errors)
    loaded = {ds.source_of(code) for code in data["series_code"].unique()}
    assert loaded == set(du.SNAPSHOT_SOURCES), loaded
    assert du.loading_sources() == NOT_IN_SNAPSHOT, du.loading_sources()
    assert du.has_country_groups(countries), "the snapshot's country list, with regions"
    assert du.source_updates()["WDI"] is not None, "the snapshot's release dates"
    assert du.stale_sources() == {}, "a copy shown while it is refetched is not 'stale'"
    print("OK: a new process shows the snapshot at once; ND-GAIN, WHR and SWIID are loading")

    at = AppTest.from_file(_pathfix.APP_PATH, default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    notes = [i.value for i in at.info if i.value.startswith("Still downloading")]
    assert len(notes) == 1 and all(du.SOURCE_LABELS[s] in notes[0] for s in NOT_IN_SNAPSHOT), notes
    assert not any("Couldn't load data from" in w.value for w in at.warning), [w.value for w in at.warning]
    print("OK: the page names the sources still downloading, with no failure warning")

    # --- 2. The fetch arrives: a new generation, with everything ---
    gate.set()
    du.wait_for_background_refresh()
    assert du.loading_sources() == set() and du.data_generation() > generation
    data, errors = du.load_data()
    assert errors == {} and {ds.source_of(c) for c in data["series_code"].unique()} == set(ds.SOURCES)
    assert all(du._source_cache_file(s).exists() for s in ds.SOURCES), "every source written to disk"
    at.run()
    assert not at.exception, at.exception
    assert not [i.value for i in at.info if i.value.startswith("Still downloading")]
    print("OK: once the background fetch is done, the next run has every source and no note")


# --- 3. A source with no copy that fails in the background is an error from the next run on ---
write_snapshot()


def ndgain_down_get(url, *args, **kwargs):
    if url == ds.NDGAIN_URL:
        raise requests.exceptions.ConnectionError("simulated: ND-GAIN unreachable")
    return fake_get(url, *args, **kwargs)


with patch.object(du._SESSION, "get", side_effect=ndgain_down_get):
    data, errors = du.load_data()
    assert errors == {}, errors  # still loading
    du.wait_for_background_refresh()
    data, errors = du.load_data()
    assert set(errors) == {"NDGAIN"} and "ND-GAIN unreachable" in errors["NDGAIN"], errors
    assert du.loading_sources() == set()
    assert {ds.source_of(c) for c in data["series_code"].unique()} == set(ds.SOURCES) - {"NDGAIN"}
print("OK: a source with no copy that fails in the background is an error on the next run")

# --- 4. A snapshot older than the disk cache loses to it ---
write_snapshot()
with patch.object(du._SESSION, "get", side_effect=fake_get):
    du.load_data()
    du.wait_for_background_refresh()
copy = du._read_saved_copy("WDI")
assert copy is not None and copy[1] > du.dt.datetime.fromisoformat(SNAPSHOT_SAVED), copy and copy[1]
print("OK: the newer of the disk cache and the snapshot is shown")

# --- 5. Nothing at all to show (no snapshot, no disk cache): the page waits, as before ---
shutil.rmtree(du._SNAPSHOT_DIR, ignore_errors=True)
du.clear_disk_cache()
st.cache_data.clear()
with patch.object(du._SESSION, "get", side_effect=fake_get):
    data, errors = du.load_data()
    assert errors == {} and du.loading_sources() == set()
    assert {ds.source_of(c) for c in data["series_code"].unique()} == set(ds.SOURCES)
print("OK: with nothing to show, load_data waits for every source")

du.clear_disk_cache()
st.cache_data.clear()
print("\nALL BACKGROUND REFRESH TESTS PASSED")
