"""Look up the FBIL reference rate for a date and show how stale the feed is.

    python scripts/fx_check.py                # today
    python scripts/fx_check.py 2026-08-15     # a holiday: the feed rolls back to the 14th

Rates are cached in data/fx_cache.db, so the demo works offline after one run.
"""
from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sakshi.fx import FbilClient, confidence_for  # noqa: E402


def main() -> None:
    on = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    client = FbilClient("data/fx_cache.db")
    try:
        ref = client.reference("USD", "INR", on)
    except RuntimeError as exc:
        print("no reference available:", exc)
        print("checkers would FLAG with confidence 0.0, and Stage 3 would mark the FX line as unverifiable")
        return
    print(f"requested {ref.requested}  published {ref.published}  provider {ref.provider}")
    print(f"USD/INR = {ref.rate}   stale {ref.stale_days} day(s)   checker confidence {confidence_for(ref)}")


if __name__ == "__main__":
    main()
