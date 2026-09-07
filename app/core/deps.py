"""Dependency dùng chung cho router FastAPI."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.db import Clients
from app.search.meili import MeiliIndex


def get_clients(request: Request) -> Clients:
    """Client được gắn vào app.state trong lifespan (xem app/main.py)."""
    clients: Clients = request.app.state.clients
    return clients


SettingsDep = Annotated[Settings, Depends(get_settings)]
ClientsDep = Annotated[Clients, Depends(get_clients)]


def get_meili(clients: ClientsDep, settings: SettingsDep) -> MeiliIndex:
    """Master key chỉ ở phía server. Client không bao giờ nói thẳng với
    Meilisearch — mọi truy vấn đi qua `/search` của ta."""
    return MeiliIndex(
        clients.http,
        settings.meili_url,
        settings.meili_master_key.get_secret_value(),
    )


MeiliDep = Annotated[MeiliIndex, Depends(get_meili)]
