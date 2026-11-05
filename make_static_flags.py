"""
Write static/flags/: a copy of every round flag in flags/, padded to the Distributions table's row size
(app.padded_flag_svg), served by Streamlit as static files (server.enableStaticServing) at
app/static/flags/<iso2>.svg for the table's ImageColumn (app.flag_url).

    python make_static_flags.py

Run it again, and commit the result, whenever the padding changes (app.FLAG_ROW_SHARE, or Streamlit's row
height or cell padding) or flags/ does; tests/test_static_flags.py fails until then.
"""
from __future__ import annotations

import shutil
import sys

from app import FLAGS_DIR, STATIC_FLAGS_DIR, padded_flag_svg


def expected_files() -> dict[str, str]:
    """{file name: padded SVG} for every flag in flags/."""
    return {f.name: padded_flag_svg(f.read_text(encoding="utf-8")) for f in sorted(FLAGS_DIR.glob("*.svg"))}


def main() -> int:
    files = expected_files()
    shutil.rmtree(STATIC_FLAGS_DIR, ignore_errors=True)
    STATIC_FLAGS_DIR.mkdir(parents=True)
    for name, svg in files.items():
        (STATIC_FLAGS_DIR / name).write_text(svg, encoding="utf-8", newline="")
    shutil.copy(FLAGS_DIR / "LICENSE.md", STATIC_FLAGS_DIR / "LICENSE.md")
    print(f"Wrote {len(files)} flags to {STATIC_FLAGS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
