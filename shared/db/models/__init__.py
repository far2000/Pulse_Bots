"""Importing this package registers every model on `Base.metadata`."""

from shared.db.models.source import SourceChannel
from shared.db.models.article import (
    Article,
    ArticleMedia,
    ArticleRole,
    ArticleStatus,
)
from shared.db.models.media import MediaFile, MediaType
from shared.db.models.user import User, UserBotSession
from shared.db.models.channel import DestinationChannel, PublishLog, PublishStatus

__all__ = [
    "SourceChannel",
    "Article",
    "ArticleMedia",
    "ArticleRole",
    "ArticleStatus",
    "MediaFile",
    "MediaType",
    "User",
    "UserBotSession",
    "DestinationChannel",
    "PublishLog",
    "PublishStatus",
]
