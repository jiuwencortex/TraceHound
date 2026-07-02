# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Alert — fired alert data container."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .severity import Severity


@dataclass
class Alert:
    """Represents one alert that has fired."""

    rule_id: str
    severity: Severity
    title: str
    description: str
    payload: dict = field(default_factory=dict)
    fired_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    db_id: int | None = None
