"""ESG qualitative report agents built on a LangGraph workflow.

The public classes are loaded lazily so importing a lightweight submodule (for
example, a Temporal workflow definition) does not also import HTTP clients and
the complete LangGraph runtime.  Temporal validates workflow imports inside a
deterministic sandbox, where those unrelated networking modules are forbidden.
"""

from __future__ import annotations

from typing import Any

try:
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv(usecwd=True), override=False)
    load_dotenv(find_dotenv(".env.local", usecwd=True), override=False)
    load_dotenv(find_dotenv(".env.enterprise", usecwd=True), override=False)
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
