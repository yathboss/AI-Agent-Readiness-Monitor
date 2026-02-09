from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from elasticsearch import Elasticsearch


@dataclass
class ESConfig:
    url: str
    user: str = ""
    password: str = ""
    enabled: bool = True


class ESClient:
    def __init__(self, cfg: ESConfig):
        self.cfg = cfg
        self.client: Optional[Elasticsearch] = None
        if not cfg.enabled:
            return

        kwargs: Dict[str, Any] = {"hosts": [cfg.url]}
        if cfg.user and cfg.password:
            kwargs["basic_auth"] = (cfg.user, cfg.password)

        self.client = Elasticsearch(**kwargs)

    @staticmethod
    def from_env() -> "ESClient":
        enabled = os.getenv("ES_ENABLED", "1").strip() not in ("0", "false", "False")
        cfg = ESConfig(
            url=os.getenv("ES_URL", "http://localhost:9200").strip(),
            user=os.getenv("ES_USER", "").strip(),
            password=os.getenv("ES_PASS", "").strip(),
            enabled=enabled,
        )
        return ESClient(cfg)

    def index(self, index: str, doc: Dict[str, Any]) -> None:
        if not self.client:
            return
        self.client.index(index=index, document=doc)
