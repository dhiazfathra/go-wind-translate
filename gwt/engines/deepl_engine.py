"""DeepL translate. Free tier covers 500k chars/month."""
from __future__ import annotations

import os
import time

import requests

from gwt.mask import IGNORE_TAG, protect, unprotect

FREE_HOST = "https://api-free.deepl.com"
PRO_HOST = "https://api.deepl.com"


class DeepLEngine:
    name = "deepl"

    def __init__(self, api_key: str | None = None, batch: int = 50,
                 timeout: int = 60, retries: int = 4) -> None:
        key = api_key if api_key is not None else os.environ.get("DEEPL_API_KEY")
        if not key:
            raise RuntimeError("DEEPL_API_KEY is not set")
        self.key = key
        self.batch = batch
        self.timeout = timeout
        self.retries = retries
        self.host = FREE_HOST if key.endswith(":fx") else PRO_HOST

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"DeepL-Auth-Key {self.key}"}

    def _post(self, path: str, payload: dict):
        last = None
        for attempt in range(self.retries):
            try:
                r = requests.post(f"{self.host}{path}", headers=self._headers,
                                  json=payload, timeout=self.timeout)
                if r.status_code == 429 or r.status_code >= 500:
                    raise RuntimeError(f"retryable HTTP {r.status_code}")
                r.raise_for_status()
                return r.json()
            except Exception as exc:      # noqa: BLE001 - retry any transport error
                last = exc
                time.sleep(2 ** attempt)
        raise RuntimeError(f"DeepL request failed after {self.retries} attempts: {last}")

    def translate(self, texts: list[str]) -> list[str]:
        out: list[str] = []
        for i in range(0, len(texts), self.batch):
            chunk = [protect(t) for t in texts[i:i + self.batch]]
            data = self._post("/v2/translate", {
                "text": chunk,
                "source_lang": "ZH",
                "target_lang": "EN-US",
                "tag_handling": "xml",
                "ignore_tags": [IGNORE_TAG],
                "preserve_formatting": True,
            })
            out.extend(unprotect(t["text"]) for t in data["translations"])
        return out

    def usage(self) -> tuple[int, int]:
        r = requests.get(f"{self.host}/v2/usage", headers=self._headers,
                         timeout=self.timeout)
        r.raise_for_status()
        d = r.json()
        return d["character_count"], d["character_limit"]
