"""
The Distributions table's flags are static files (static/flags/, served at app/static/flags/): check that
they are up to date with flags/ and the padding (make_static_flags.py writes them), that static serving is
on, and that the table points at them while the header keeps its one data: URI.
"""
import _pathfix  # noqa: F401
import tomllib
from pathlib import Path

import app
from make_static_flags import expected_files

ROOT = Path(_pathfix.APP_PATH).parent

expected = expected_files()
on_disk = {f.name: f.read_text(encoding="utf-8") for f in app.STATIC_FLAGS_DIR.glob("*.svg")}
assert set(on_disk) == set(expected), "static/flags/ is out of date: run python make_static_flags.py"
stale = [name for name, svg in expected.items() if on_disk[name] != svg]
assert not stale, f"padding changed: run python make_static_flags.py ({len(stale)} flags differ, e.g. {stale[:3]})"
assert (app.STATIC_FLAGS_DIR / "LICENSE.md").is_file()
print(f"OK: static/flags/ matches flags/ and the padding ({len(expected)} flags)")

config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
assert config["server"]["enableStaticServing"] is True
assert app.flag_url("DE") == "app/static/flags/de.svg"
assert app.flag_url("JG") is None and app.flag_url(None) is None and app.flag_url("XX1") is None
assert app.flag_image("DE").startswith("data:image/svg+xml;base64,")  # the header's flag, unpadded
print("OK: the table uses static flag URLs; the header keeps its data: URI")
