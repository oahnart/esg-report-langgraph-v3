from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import logging
from threading import Lock
from time import perf_counter
from typing import Any, Callable, Literal, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import re


logger = logging.getLogger(__name__)

ProgressLevel = Literal["quiet", "steps", "full"]
ProgressVerbosity = Literal["steps", "full"]
ProgressSink = Callable[["ProgressEvent"], None]
LegacyProgressObserver = Callable[[str, str], None]

_LEVEL_RANK: dict[str, int] = {"quiet": 0, "steps": 1, "full": 2}
_STATUS_LABELS = {
    "started": "START",
    "completed": "DONE",
    "failed": "FAILED",
    "retry": "RETRY",
    "cache": "CACHE",
    "skipped": "SKIP",
    "fallback": "FALLBACK",
    "timeout": "TIMEOUT",
    "info": "INFO",
}
_SENSITIVE_KEY_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization|signature)"
)
_SENSITIVE_TEXT_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password|authorization|signature)"
    r"([\"']?\s*[:=]\s*[\"']?)([^\s,;}\]\"']+)"
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+\-/=]+")


@dataclass(frozen=True)
class ProgressEvent:
    category: str
    name: str
    status: str
    timestamp: datetime
    total_elapsed_seconds: float
    duration_seconds: float | None = None
    current: int | None = None
    total: int | None = None
    completed: int | None = None
    details: Mapping[str, Any] = field(default_factory=dict)
    verbosity: ProgressVerbosity = "full"


@dataclass(frozen=True)
class ProgressToken:
    category: str
    name: str
    started_at: float
    current: int | None = None
    total: int | None = None
    details: Mapping[str, Any] = field(default_factory=dict)
    verbosity: ProgressVerbosity = "full"


class ProgressReporter:
    """Thread-safe structured progress events for CLI and workflow adapters."""

    def __init__(
        self,
        sink: ProgressSink | None = None,
        *,
        level: ProgressLevel = "full",
    ) -> None:
        normalized_level = str(level or "full").strip().casefold()
        if normalized_level not in _LEVEL_RANK:
            raise ValueError("progress level must be one of: full, steps, quiet")
        self.sink = sink
        self.level: ProgressLevel = normalized_level  # type: ignore[assignment]
        self.started_at = perf_counter()
        self._lock = Lock()
        self._metrics: dict[tuple[str, str], int] = {}

    @classmethod
    def from_legacy(
        cls,
        observer: LegacyProgressObserver | None,
        *,
        level: ProgressLevel = "steps",
    ) -> "ProgressReporter":
        if observer is None:
            return cls(level=level)

        def sink(event: ProgressEvent) -> None:
            observer(event.name, event.status)

        return cls(sink, level=level)

    def enabled_for(self, verbosity: ProgressVerbosity) -> bool:
        return bool(self.sink) and _LEVEL_RANK[self.level] >= _LEVEL_RANK[verbosity]

    def count(self, category: str, status: str | None = None) -> int:
        normalized_category = str(category).upper()
        with self._lock:
            if status is not None:
                return self._metrics.get((normalized_category, str(status)), 0)
            return sum(
                count
                for (event_category, _), count in self._metrics.items()
                if event_category == normalized_category
            )

    def start(
        self,
        category: str,
        name: str,
        *,
        current: int | None = None,
        total: int | None = None,
        details: Mapping[str, Any] | None = None,
        verbosity: ProgressVerbosity = "full",
    ) -> ProgressToken:
        token = ProgressToken(
            category=category,
            name=name,
            started_at=perf_counter(),
            current=current,
            total=total,
            details=dict(details or {}),
            verbosity=verbosity,
        )
        self._emit(
            category,
            name,
            "started",
            current=current,
            total=total,
            details=token.details,
            verbosity=verbosity,
        )
        return token

    def finish(
        self,
        token: ProgressToken,
        *,
        status: str = "completed",
        completed: int | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        merged = dict(token.details)
        merged.update(details or {})
        self._emit(
            token.category,
            token.name,
            status,
            duration_seconds=max(0.0, perf_counter() - token.started_at),
            current=token.current,
            total=token.total,
            completed=completed,
            details=merged,
            verbosity=token.verbosity,
        )

    def event(
        self,
        category: str,
        name: str,
        status: str = "info",
        *,
        duration_seconds: float | None = None,
        current: int | None = None,
        total: int | None = None,
        completed: int | None = None,
        details: Mapping[str, Any] | None = None,
        verbosity: ProgressVerbosity = "full",
    ) -> None:
        self._emit(
            category,
            name,
            status,
            duration_seconds=duration_seconds,
            current=current,
            total=total,
            completed=completed,
            details=details,
            verbosity=verbosity,
        )

    def _emit(
        self,
        category: str,
        name: str,
        status: str,
        *,
        duration_seconds: float | None = None,
        current: int | None = None,
        total: int | None = None,
        completed: int | None = None,
        details: Mapping[str, Any] | None = None,
        verbosity: ProgressVerbosity,
    ) -> None:
        should_deliver = self.enabled_for(verbosity)
        metric_key = (str(category).upper(), str(status))
        if not should_deliver:
            with self._lock:
                self._metrics[metric_key] = self._metrics.get(metric_key, 0) + 1
            return
        event = ProgressEvent(
            category=str(category),
            name=str(name),
            status=str(status),
            timestamp=datetime.now().astimezone(),
            total_elapsed_seconds=max(0.0, perf_counter() - self.started_at),
            duration_seconds=duration_seconds,
            current=current,
            total=total,
            completed=completed,
            details=dict(details or {}),
            verbosity=verbosity,
        )
        try:
            with self._lock:
                self._metrics[metric_key] = self._metrics.get(metric_key, 0) + 1
                if self.sink:
                    self.sink(event)
        except Exception:
            logger.exception("Progress sink failed; report generation will continue")


def format_progress_event(event: ProgressEvent) -> str:
    timestamp = event.timestamp.isoformat(timespec="milliseconds")
    elapsed = _clock_duration(event.total_elapsed_seconds)
    status = _STATUS_LABELS.get(event.status, event.status.upper())
    parts = [
        f"[{timestamp}]",
        f"[+{elapsed}]",
        event.category.upper(),
        status,
        event.name,
    ]
    if event.current is not None and event.total is not None:
        position_label = (
            "attempt"
            if event.category.upper() == "RAG API"
            else "batch"
            if event.category.upper() == "RAG BATCH"
            else "question"
            if event.category.upper() in {"CURATOR", "WRITER", "SEMANTIC", "REVISION"}
            else "item"
        )
        parts.append(f"{position_label}={event.current}/{event.total}")
    if event.completed is not None:
        completion_total = event.total if event.total is not None else "?"
        parts.append(f"completed={event.completed}/{completion_total}")
    if event.duration_seconds is not None:
        parts.append(f"duration={_human_duration(event.duration_seconds)}")
    parts.extend(
        f"{key}={_safe_value(value)}"
        for key, value in event.details.items()
        if value not in (None, "", [], {}, ())
    )
    return " ".join(parts)


def safe_error_detail(exc: BaseException, limit: int = 240) -> str:
    value = " ".join(str(exc).replace("\r", " ").replace("\n", " ").split())
    value = redact_sensitive_text(value)
    if not value:
        value = type(exc).__name__
    return value if len(value) <= limit else f"{value[:limit]}..."


def _safe_value(value: Any, limit: int = 240) -> str:
    if isinstance(value, (list, tuple, set)):
        text = ",".join(str(item) for item in value)
    elif isinstance(value, bool):
        text = str(value).lower()
    else:
        text = str(value)
    text = " ".join(text.replace("\r", " ").replace("\n", " ").split())
    text = redact_sensitive_text(text)
    return text if len(text) <= limit else f"{text[:limit]}..."


def redact_url_secrets(url: str) -> str:
    try:
        parts = urlsplit(str(url))
        query = [
            (key, "[REDACTED]" if _SENSITIVE_KEY_RE.search(key) else value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
        ]
        netloc = parts.netloc
        if parts.username is not None or parts.password is not None:
            hostname = parts.hostname or ""
            if ":" in hostname and not hostname.startswith("["):
                hostname = f"[{hostname}]"
            port = f":{parts.port}" if parts.port is not None else ""
            netloc = f"[REDACTED]@{hostname}{port}"
        return urlunsplit((parts.scheme, netloc, parts.path, urlencode(query), parts.fragment))
    except (TypeError, ValueError):
        return redact_sensitive_text(str(url))


def redact_sensitive_text(value: str) -> str:
    redacted = _BEARER_RE.sub("Bearer [REDACTED]", str(value))
    return _SENSITIVE_TEXT_RE.sub(r"\1\2[REDACTED]", redacted)


def _clock_duration(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def _human_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.3f}s"
    return _clock_duration(seconds)
