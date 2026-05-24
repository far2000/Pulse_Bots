"""Entrypoint: `python -m bots.news`."""

from __future__ import annotations

import asyncio

from bots.news.main import main

if __name__ == "__main__":
    asyncio.run(main())
