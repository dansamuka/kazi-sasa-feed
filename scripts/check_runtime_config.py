#!/usr/bin/env python3
"""Report whether optional authenticated collectors are configured.

Only presence is reported; secret values are never printed.
"""
from __future__ import annotations

import os


def main() -> None:
    groups = {
        "ReliefWeb": ["RELIEFWEB_APPNAME"],
        "Adzuna": ["ADZUNA_APP_ID", "ADZUNA_APP_KEY"],
        "UN Talent": ["UNTALENT_FEED_URL"],
    }
    for source, names in groups.items():
        missing = [name for name in names if not os.environ.get(name)]
        if missing:
            print(f"WARN {source}: not configured ({', '.join(missing)} missing); collector will be skipped")
        else:
            print(f"OK   {source}: configured")


if __name__ == "__main__":
    main()
