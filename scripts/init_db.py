"""Run all pending Alembic migrations.

Equivalent to `alembic upgrade head`, but importable from code (handy if you
want to call it at container start before launching the bot).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from loguru import logger

from shared.logging import configure_logging


def _alembic_cfg() -> Config:
    ini_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    cfg = Config(str(ini_path))
    # env.py will pull DATABASE_URL from Settings, but Alembic still wants the value.
    cfg.set_main_option("script_location", str(ini_path.parent / "migrations"))
    return cfg


def upgrade_head() -> None:
    cfg = _alembic_cfg()
    command.upgrade(cfg, "head")


async def main() -> None:
    configure_logging()
    logger.info("Running migrations… (DATABASE_URL={})", os.environ.get("DATABASE_URL", "(default)"))
    # Alembic's CLI is sync; run in a worker thread so this script can be used
    # as part of an async startup sequence.
    await asyncio.to_thread(upgrade_head)
    logger.info("Migrations up to date.")


if __name__ == "__main__":
    asyncio.run(main())
