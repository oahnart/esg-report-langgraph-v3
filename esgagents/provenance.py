from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


logger = logging.getLogger(__name__)

PROVENANCE_SCHEMA_VERSION = 1
PROVENANCE_INPUTS = ("esgagents", "skills", "template_v1", "pyproject.toml")
IGNORED_DIRECTORY_NAMES = {".git", ".mypy_cache", ".pytest_cache", "__pycache__"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}
VALID_MODES = {"off", "warn", "strict"}


class ProvenanceError(RuntimeError):
    """Raised when a container cannot prove that its image matches the source."""


def compute_source_digest(root: str | Path) -> str:
    source_root = Path(root).resolve()
    files: list[Path] = []
    for name in PROVENANCE_INPUTS:
        candidate = source_root / name
        if not candidate.exists():
            raise FileNotFoundError(f"provenance input is missing: {name}")
        if candidate.is_file():
            files.append(candidate)
            continue
        files.extend(
            path
            for path in candidate.rglob("*")
            if path.is_file() and not _ignored(path.relative_to(source_root))
        )

    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(source_root).as_posix()):
        relative = path.relative_to(source_root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def create_build_provenance(root: str | Path, *, git_sha: str = "unknown") -> dict[str, Any]:
    return {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "source_digest": compute_source_digest(root),
        "built_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_sha": (git_sha or "unknown").strip() or "unknown",
    }


def write_build_provenance(
    root: str | Path,
    output: str | Path,
    *,
    git_sha: str = "unknown",
) -> dict[str, Any]:
    record = create_build_provenance(root, git_sha=git_sha)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def verify_runtime_provenance(
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    values = os.environ if environ is None else environ
    mode = str(values.get("ESG_PROVENANCE_MODE", "off") or "off").strip().casefold()
    if mode not in VALID_MODES:
        raise ProvenanceError(f"invalid ESG_PROVENANCE_MODE: {mode}")

    build_file = Path(values.get("ESG_PROVENANCE_BUILD_FILE", "/app/build_provenance.json"))
    if mode == "off":
        try:
            build = _read_build_record(build_file, required=False)
        except (OSError, ValueError, ProvenanceError):
            build = {}
        return _runtime_record(mode, build, verified=False)

    try:
        build = _read_build_record(build_file, required=True)
        image_digest = str(build.get("source_digest", "") or "")
        expected_digest = str(values.get("ESG_EXPECTED_SOURCE_DIGEST", "") or "").strip()
        source_root_value = str(values.get("ESG_PROVENANCE_SOURCE_ROOT", "") or "").strip()
        runtime_digest = compute_source_digest(source_root_value) if source_root_value else ""
        if not expected_digest and not runtime_digest:
            raise ProvenanceError(
                "strict provenance requires ESG_EXPECTED_SOURCE_DIGEST or "
                "ESG_PROVENANCE_SOURCE_ROOT"
            )
        comparisons = [digest for digest in (expected_digest, runtime_digest) if digest]
        verified = bool(image_digest) and all(image_digest == digest for digest in comparisons)
        record = _runtime_record(
            mode,
            build,
            verified=verified,
            runtime_source_digest=runtime_digest,
            expected_source_digest=expected_digest,
        )
        if not verified:
            raise ProvenanceError(_mismatch_message(record))
        logger.info(
            "Container provenance verified source_digest=%s built_at_utc=%s git_sha=%s",
            image_digest[:12],
            record["built_at_utc"],
            record["git_sha"],
        )
        return record
    except (OSError, ValueError, ProvenanceError) as exc:
        if mode == "strict":
            if isinstance(exc, ProvenanceError):
                raise
            raise ProvenanceError(str(exc)) from exc
        logger.warning("Container provenance warning: %s", exc)
        if "record" in locals():
            return {**record, "verified": False}
        return _runtime_record(mode, locals().get("build", {}), verified=False)


def _read_build_record(path: Path, *, required: bool) -> dict[str, Any]:
    if not path.is_file():
        if required:
            raise ProvenanceError(f"build provenance file is missing: {path}")
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ProvenanceError("build provenance payload must be an object")
    if payload.get("schema_version") != PROVENANCE_SCHEMA_VERSION:
        raise ProvenanceError("unsupported build provenance schema_version")
    if not str(payload.get("source_digest", "")):
        raise ProvenanceError("build provenance source_digest is missing")
    return payload


def _runtime_record(
    mode: str,
    build: Mapping[str, Any],
    *,
    verified: bool,
    runtime_source_digest: str = "",
    expected_source_digest: str = "",
) -> dict[str, Any]:
    return {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "mode": mode,
        "verified": verified,
        "source_digest": str(build.get("source_digest", "") or ""),
        "runtime_source_digest": runtime_source_digest,
        "expected_source_digest": expected_source_digest,
        "built_at_utc": str(build.get("built_at_utc", "") or ""),
        "git_sha": str(build.get("git_sha", "unknown") or "unknown"),
    }


def _mismatch_message(record: Mapping[str, Any]) -> str:
    return (
        "container image source does not match the expected runtime source "
        f"(image={str(record.get('source_digest', ''))[:12]}, "
        f"runtime={str(record.get('runtime_source_digest', ''))[:12]}, "
        f"expected={str(record.get('expected_source_digest', ''))[:12]}). "
        "Rebuild with: docker compose up --build --force-recreate -d api worker"
    )


def _ignored(relative: Path) -> bool:
    return bool(
        IGNORED_DIRECTORY_NAMES.intersection(relative.parts)
        or relative.suffix.casefold() in IGNORED_SUFFIXES
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ESG source provenance metadata")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--root", required=True)
    build.add_argument("--output", required=True)
    build.add_argument("--git-sha", default="unknown")
    args = parser.parse_args()
    if args.command == "build":
        record = write_build_provenance(args.root, args.output, git_sha=args.git_sha)
        print(json.dumps(record, sort_keys=True))


if __name__ == "__main__":
    main()
