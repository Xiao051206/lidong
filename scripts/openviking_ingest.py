#!/usr/bin/env python3
"""Batch-ingest knowledge sources into OpenViking.

The source manifest is a YAML file with the shape:

sources:
  - url: https://github.com/owner/repo
    reason: Seed repository docs
  - url: https://en.wikipedia.org/wiki/Model_Context_Protocol
    reason: Background reference
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

try:
    import yaml
except ImportError:  # pragma: no cover - fallback for incomplete local envs
    yaml = None


def _default_hermes_home() -> Path:
    configured = os.environ.get("HERMES_HOME", "").strip()
    return Path(configured) if configured else Path.home() / ".hermes"


def _load_sources(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"source manifest not found: {path}")

    raw = path.read_text(encoding="utf-8")
    if yaml is not None:
        loaded = yaml.safe_load(raw) or {}
    else:
        loaded = json.loads(raw or "{}")
    if not isinstance(loaded, dict):
        raise ValueError("source manifest must be a YAML mapping")

    raw_sources = loaded.get("sources")
    if not isinstance(raw_sources, list):
        raise ValueError("source manifest must contain a top-level 'sources' list")

    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw_sources:
        normalized = _normalize_source(item)
        url = normalized["url"]
        if url in seen:
            continue
        seen.add(url)
        sources.append(normalized)
    return sources


def _normalize_source(item: Any) -> dict[str, str]:
    if isinstance(item, str):
        url = item.strip()
        reason = ""
    elif isinstance(item, dict):
        url = str(item.get("url") or item.get("path") or "").strip()
        reason = str(item.get("reason") or "").strip()
    else:
        raise ValueError(f"unsupported source entry: {item!r}")

    if not url:
        raise ValueError(f"source entry is missing url/path: {item!r}")

    return {"url": url, "reason": reason}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch-ingest GitHub/Wikipedia resources into OpenViking.",
    )
    parser.add_argument(
        "--sources-file",
        default=str(_default_hermes_home() / "knowledge_base_sources.yaml"),
        help="YAML manifest of sources to ingest (default: ~/.hermes/knowledge_base_sources.yaml).",
    )
    parser.add_argument(
        "--endpoint",
        default=os.getenv("OPENVIKING_ENDPOINT", "http://127.0.0.1:1933"),
        help="OpenViking endpoint (default: OPENVIKING_ENDPOINT or http://127.0.0.1:1933).",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("OPENVIKING_API_KEY", ""),
        help="OpenViking API key (default: OPENVIKING_API_KEY).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="HTTP timeout in seconds (default: 15).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print requests without sending them.",
    )
    return parser.parse_args()


def _headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def _request_json(
    method: str,
    base_url: str,
    path: str,
    headers: dict[str, str],
    timeout: float,
    payload: dict[str, str] | None = None,
) -> dict[str, Any]:
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    request = urllib_request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urllib_request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed with HTTP {exc.code}: {detail}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"{method} {path} failed: {exc.reason}") from exc

    if not raw.strip():
        return {}
    return json.loads(raw)


def main() -> int:
    args = parse_args()
    sources_path = Path(args.sources_file).expanduser()
    sources = _load_sources(sources_path)

    if not sources:
        print(f"No sources found in {sources_path}")
        return 0

    print(f"Loaded {len(sources)} source(s) from {sources_path}")
    if args.dry_run:
        for item in sources:
            print(f"DRY RUN  {item['url']}")
            if item["reason"]:
                print(f"         reason: {item['reason']}")
        return 0

    base_url = args.endpoint.rstrip("/")
    headers = _headers(args.api_key)
    _request_json("GET", base_url, "/health", headers, args.timeout)
    for item in sources:
        payload = {"path": item["url"]}
        if item["reason"]:
            payload["reason"] = item["reason"]
        body = _request_json("POST", base_url, "/api/v1/resources", headers, args.timeout, payload)
        result = body.get("result", {}) if isinstance(body, dict) else {}
        root_uri = result.get("root_uri", "")
        suffix = f" -> {root_uri}" if root_uri else ""
        print(f"INGESTED  {item['url']}{suffix}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
