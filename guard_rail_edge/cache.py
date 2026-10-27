"""Disk-backed judge response cache to avoid redundant LLM invocations."""

import hashlib
import json
from pathlib import Path
from typing import Any


class JudgeCache:
    """Caches raw judge LLM responses on disk keyed by sha256 of call parameters."""

    def __init__(self, cache_dir: Path | str | None = None, enabled: bool = True) -> None:
        self.enabled = enabled and (cache_dir is not None)
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.hits: int = 0
        self.misses: int = 0
        if self.enabled and self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def compute_key(
        self,
        backend_type: str,
        model_name: str,
        model_digest: str | None,
        prompt: str,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Compute SHA-256 hash key across backend, model, digest, prompt, and options."""
        opts_str = json.dumps(options, sort_keys=True) if options else ""
        digest_str = model_digest or ""
        payload = f"{backend_type}|{model_name}|{digest_str}|{opts_str}|{prompt}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, key: str) -> str | None:
        """Retrieve cached raw reply by key if available."""
        if not self.enabled or self.cache_dir is None:
            return None
        cache_file = self.cache_dir / f"{key}.txt"
        if cache_file.exists():
            try:
                content = cache_file.read_text(encoding="utf-8")
                self.hits += 1
                return content
            except Exception:
                return None
        self.misses += 1
        return None

    def set(self, key: str, raw_reply: str) -> None:
        """Store raw judge reply in cache. Never cache empty strings or errors."""
        if not self.enabled or self.cache_dir is None or not raw_reply:
            return
        cache_file = self.cache_dir / f"{key}.txt"
        try:
            cache_file.write_text(raw_reply, encoding="utf-8")
        except Exception:
            pass
