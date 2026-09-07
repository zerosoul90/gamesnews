"""Dependency dùng chung cho router FastAPI."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.db import Clients


def get_clients(request: Request) -> Clients:
    """Client được gắn vào app.state trong lifespan (xem app/main.py)."""
    clients: Clients = request.app.state.clients
    return clients


SettingsDep = Annotated[Settings, Depends(get_settings)]
ClientsDep = Annotated[Clients, Depends(get_clients)]
