"""News-bot-specific config knobs that aren't worth promoting to the shared layer."""

from __future__ import annotations

from shared.config import BotType

BOT_TYPE = BotType.NEWS

# How long we wait after seeing the first message of an album for the rest to
# arrive before we treat the album as "complete" and process it.
ALBUM_FLUSH_DELAY_SECONDS = 2.5

# Outbound publish loop pause when there's nothing to do.
PUBLISH_IDLE_SLEEP_SECONDS = 5.0

# Max concurrent ingest tasks (downloads + summarization).
INGEST_WORKER_CONCURRENCY = 4
