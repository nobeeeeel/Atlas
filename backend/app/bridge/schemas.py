from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class Command(BaseModel):
    enabled: bool = True
    enable_buy_orders: bool = True
    enable_sell_orders: bool = True
    command_version: int = 1
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class Status(BaseModel):
    connected: bool = True
    strategy: str = "nyao"
    symbol: str = "XAUUSD"

    balance: float = 0.0
    equity: float = 0.0
    floating_profit: float = 0.0
    open_positions: int = 0

    buy_score: float = 0.0
    sell_score: float = 0.0

    atlas_enabled: bool = True
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class Runtime(BaseModel):
    atlas_version: str = "0.1.0"
    environment: str = "demo"
    strategy: str = "nyao"
    last_updated: Optional[datetime] = None