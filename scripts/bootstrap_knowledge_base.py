#!/usr/bin/env python3
"""Bootstrap a Hermes knowledge-base layout in the active Hermes home.

Default architecture:
  - OpenViking as the persistent knowledge base
  - GitHub MCP for live repository access
  - GitHub/Wikipedia URLs seeded into a source manifest for ingestion

The script is intentionally conservative:
  - Existing config/env values are preserved unless a target key is missing.
  - Existing source manifests are preserved unless --replace-sources is set.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Iterable

try:
    import yaml
except ImportError:  # pragma: no cover - fallback for incomplete local envs
    yaml = None


DEFAULT_GITHUB_SOURCES = [
    {
        "url": "https://github.com/NousResearch/hermes-agent",
        "reason": "Seed the current Hermes repository into the persistent knowledge base.",
    },
    {
        "url": "https://github.com/NousResearch/hermes-agent/wiki",
        "reason": "Pull repository wiki pages into the persistent knowledge base if available.",
    },
]

DEFAULT_WIKIPEDIA_SOURCES = [
    {
        "url": "https://en.wikipedia.org/wiki/Large_language_model",
        "reason": "Background reference for LLM concepts used by Hermes.",
    },
    {
        "url": "https://en.wikipedia.org/wiki/Model_Context_Protocol",
        "reason": "Background reference for MCP concepts used by Hermes.",
    },
]

GENERATED_ENV_VALUES = {
    "OPENVIKING_ENDPOINT": "http://127.0.0.1:1933",
    "OPENVIKING_API_KEY": "",
    "OPENVIKING_ACCOUNT": "default",
    "OPENVIKING_USER": "default",
    "OPENVIKING_AGENT": "hermes",
    "GITHUB_TOKEN": "",
}


def _default_hermes_home() -> Path:
    configured = os.environ.get("HERMES_HOME", "").strip()
    return Path(configured) if configured else Path.home() / ".hermes"


def _ensure_mapping(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _load_yaml_mapping(path: Path) -> dict:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    if yaml is not None:
        loaded = yaml.safe_load(raw) or {}
    else:
        loaded = json.loads(raw or "{}")
    return loaded if isinstance(loaded, dict) else {}


def _dump_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if yaml is not None:
        rendered = yaml.safe_dump(
            data,
            sort_keys=False,
            allow_unicode=False,
            default_flow_style=False,
        )
    else:
        rendered = json.dumps(data, indent=2)
    path.write_text(rendered, encoding="utf-8")


def _merge_config(config: dict) -> dict:
    merged = dict(config)

    memory = _ensure_mapping(merged.get("memory"))
    memory.setdefault("provider", "openviking")
    merged["memory"] = memory

    mcp_servers = _ensure_mapping(merged.get("mcp_servers"))
    github_server = _ensure_mapping(mcp_servers.get("github"))
    github_server.setdefault("command", "npx")
    github_server.setdefault("args", ["-y", "@modelcontextprotocol/server-github"])
    github_env = _ensure_mapping(github_server.get("env"))
    github_env.setdefault("GITHUB_PERSONAL_ACCESS_TOKEN", "${GITHUB_TOKEN}")
    github_server["env"] = github_env
    mcp_servers["github"] = github_server
    merged["mcp_servers"] = mcp_servers

    return merged


def _parse_existing_env(path: Path) -> tuple[list[str], set[str]]:
    if not path.exists():
        return [], set()

    lines = path.read_text(encoding="utf-8").splitlines()
    present: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key:
            present.add(key)
    return lines, present


def _write_env_file(path: Path) -> None:
    lines, present = _parse_existing_env(path)

    if not lines:
        lines.extend(
            [
                "# Hermes knowledge-base bootstrap",
                "# Fill secrets, then restart Hermes.",
                "",
            ]
        )

    changed = False
    for key, value in GENERATED_ENV_VALUES.items():
        if key in present:
            continue
        lines.append(f"{key}={value}")
        changed = True

    if changed or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _normalize_sources(values: Iterable[str], default_reason: str) -> list[dict]:
    normalized: list[dict] = []
    for raw in values:
        text = str(raw or "").strip()
        if not text:
            continue
        normalized.append({"url": text, "reason": default_reason})
    return normalized


def _build_sources(github_sources: list[str], wikipedia_sources: list[str]) -> dict:
    resolved_github = _normalize_sources(
        github_sources,
        "GitHub source provided at bootstrap time.",
    )
    resolved_wikipedia = _normalize_sources(
        wikipedia_sources,
        "Wikipedia source provided at bootstrap time.",
    )

    if not resolved_github:
        resolved_github = list(DEFAULT_GITHUB_SOURCES)
    if not resolved_wikipedia:
        resolved_wikipedia = list(DEFAULT_WIKIPEDIA_SOURCES)

    return {
        "sources": [*resolved_github, *resolved_wikipedia],
    }


def _write_sources_file(path: Path, payload: dict, replace_sources: bool) -> None:
    if path.exists() and not replace_sources:
        return
    _dump_yaml(path, payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap Hermes knowledge-base config in ~/.hermes.",
    )
    parser.add_argument(
        "--home",
        default=str(_default_hermes_home()),
        help="Hermes home directory to bootstrap (default: ~/.hermes).",
    )
    parser.add_argument(
        "--github-source",
        action="append",
        default=[],
        help="GitHub repo or wiki URL to seed into the source manifest. Repeatable.",
    )
    parser.add_argument(
        "--wikipedia-source",
        action="append",
        default=[],
        help="Wikipedia URL to seed into the source manifest. Repeatable.",
    )
    parser.add_argument(
        "--replace-sources",
        action="store_true",
        help="Overwrite an existing knowledge_base_sources.yaml.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    hermes_home = Path(args.home).expanduser()
    config_path = hermes_home / "config.yaml"
    env_path = hermes_home / ".env"
    env_example_path = hermes_home / ".env.example"
    sources_path = hermes_home / "knowledge_base_sources.yaml"

    config = _load_yaml_mapping(config_path)
    merged = _merge_config(config)
    _dump_yaml(config_path, merged)

    _write_env_file(env_path)
    _write_env_file(env_example_path)

    sources_payload = _build_sources(args.github_source, args.wikipedia_source)
    _write_sources_file(sources_path, sources_payload, args.replace_sources)

    print(f"Bootstrapped Hermes home: {hermes_home}")
    print(f"  config:   {config_path}")
    print(f"  env:      {env_path}")
    print(f"  env.example: {env_example_path}")
    print(f"  sources:  {sources_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
