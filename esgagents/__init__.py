"""ESG qualitative report agents built on a LangGraph workflow.

The public classes are loaded lazily so importing a lightweight submodule (for
example, a Temporal workflow definition) does not also import HTTP clients and
the complete LangGraph runtime.  Temporal validates workflow imports inside a
deterministic sandbox, where those unrelated networking modules are forbidden.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
_ENV_ASSIGNMENT_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def _warn_duplicate_env_keys(path_value: str) -> None:
    if not path_value:
        return
    path = Path(path_value)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    seen: set[str] = set()
    duplicates: set[str] = set()
    for line in lines:
        match = _ENV_ASSIGNMENT_RE.match(line)
        if not match:
            continue
        key = match.group(1)
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    if duplicates:
        logger.warning(
            "Duplicate environment keys in %s: %s; the last file value may not "
            "win when the process environment is already set",
            path,
            ", ".join(sorted(duplicates)),
        )


try:
    from dotenv import find_dotenv, load_dotenv

    for _env_name in (".env", ".env.local", ".env.enterprise"):
        _env_path = find_dotenv(_env_name, usecwd=True)
        _warn_duplicate_env_keys(_env_path)
        if _env_path:
            load_dotenv(_env_path, override=False)
except ImportError:
    pass

__all__ = ["CompanyInput", "ESGQualitativeGraph"]


def __getattr__(name: str) -> Any:
    if name == "CompanyInput":
        from esgagents.schemas import CompanyInput

        return CompanyInput
    if name == "ESGQualitativeGraph":
        from esgagents.graph.esg_graph import ESGQualitativeGraph

        return ESGQualitativeGraph
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
