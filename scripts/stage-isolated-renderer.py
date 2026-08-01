#!/usr/bin/env python3
"""Stage a reproducible, episode-local copy of the story renderer.

The source renderer is treated as read-only.  Renderer code is copied into a
temporary sibling directory, only the storyboard-referenced public assets and
public/fonts are added, and the finished tree is atomically renamed into place.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


PROVENANCE_FILENAME = "STAGING_PROVENANCE.json"
PROVENANCE_SCHEMA = "isolated-renderer-stage/v1"
SOURCE_EXCLUDED_DIRECTORIES = {".git", "build", "node_modules", "out", "public"}


class StageError(RuntimeError):
    """Raised when an isolated renderer cannot be staged safely."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def manifest_digest(entries: Iterable[dict[str, Any]]) -> str:
    normalized = [
        {
            "path": entry["path"],
            "sha256": entry["sha256"],
            "bytes": entry["bytes"],
        }
        for entry in sorted(entries, key=lambda item: item["path"])
    ]
    return sha256_bytes(canonical_json_bytes(normalized))


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def ensure_plain_file(path: Path, *, label: str) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as exc:
        raise StageError(f"{label} does not exist: {path}") from exc
    if stat.S_ISLNK(mode):
        raise StageError(f"{label} must not be a symlink: {path}")
    if not stat.S_ISREG(mode):
        raise StageError(f"{label} must be a regular file: {path}")


def ensure_no_symlink_components(root: Path, relative: Path, *, label: str) -> None:
    current = root
    for component in relative.parts:
        current /= component
        if current.is_symlink():
            raise StageError(f"{label} traverses a symlink: {current}")


def load_storyboard(path: Path) -> tuple[dict[str, Any], bytes]:
    ensure_plain_file(path, label="storyboard")
    raw = path.read_bytes()
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StageError(f"storyboard is not valid UTF-8 JSON: {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise StageError("storyboard root must be a JSON object")
    scenes = parsed.get("scenes")
    if not isinstance(scenes, list):
        raise StageError("storyboard.scenes must be a JSON array")
    return parsed, raw


def normalize_asset_path(raw: str, *, scene_label: str, asset_key: str) -> Path:
    if not raw or "\\" in raw:
        raise StageError(
            f"{scene_label}.assets.{asset_key} is not a normalized POSIX path: {raw!r}"
        )
    pure = PurePosixPath(raw)
    if (
        pure.is_absolute()
        or pure.as_posix() != raw
        or not pure.parts
        or any(part in {"", ".", ".."} for part in pure.parts)
        or pure.parts[0] != "assets"
    ):
        raise StageError(
            f"{scene_label}.assets.{asset_key} must be a normalized path below "
            f"public/assets: {raw!r}"
        )
    return Path(*pure.parts)


def collect_referenced_assets(
    storyboard: dict[str, Any],
    public_root: Path,
) -> list[dict[str, Any]]:
    references: dict[str, dict[str, Any]] = {}
    for scene_index, scene in enumerate(storyboard["scenes"], start=1):
        if not isinstance(scene, dict):
            raise StageError(f"storyboard.scenes[{scene_index - 1}] must be an object")
        scene_id = scene.get("id")
        scene_label = f"scene {scene_id!r}" if scene_id is not None else f"scene #{scene_index}"
        assets = scene.get("assets", {})
        if assets is None:
            assets = {}
        if not isinstance(assets, dict):
            raise StageError(f"{scene_label}.assets must be an object")
        for asset_key, raw_path in sorted(assets.items()):
            if raw_path is None or raw_path == "":
                continue
            if not isinstance(raw_path, str):
                raise StageError(f"{scene_label}.assets.{asset_key} must be a string or null")
            relative = normalize_asset_path(
                raw_path,
                scene_label=scene_label,
                asset_key=str(asset_key),
            )
            ensure_no_symlink_components(
                public_root,
                relative,
                label=f"{scene_label}.assets.{asset_key}",
            )
            source = public_root / relative
            ensure_plain_file(
                source,
                label=f"{scene_label}.assets.{asset_key}",
            )
            resolved = source.resolve()
            if not is_relative_to(resolved, public_root):
                raise StageError(
                    f"{scene_label}.assets.{asset_key} escapes renderer public/: {raw_path!r}"
                )
            relative_posix = relative.as_posix()
            reference = f"{scene_label}.assets.{asset_key}"
            if relative_posix not in references:
                references[relative_posix] = {
                    "path": relative_posix,
                    "source": source,
                    "referenced_by": [],
                }
            references[relative_posix]["referenced_by"].append(reference)
    return [references[key] for key in sorted(references)]


def iter_plain_files(root: Path, *, label: str) -> list[tuple[Path, Path]]:
    if root.is_symlink():
        raise StageError(f"{label} must not be a symlink: {root}")
    if not root.is_dir():
        raise StageError(f"{label} directory does not exist: {root}")
    files: list[tuple[Path, Path]] = []
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(directory)
        dirnames.sort()
        filenames.sort()
        for dirname in dirnames:
            candidate = current / dirname
            if candidate.is_symlink():
                raise StageError(f"{label} contains a symlinked directory: {candidate}")
        for filename in filenames:
            candidate = current / filename
            ensure_plain_file(candidate, label=label)
            files.append((candidate.relative_to(root), candidate))
    return files


def iter_renderer_snapshot_files(renderer_root: Path) -> list[tuple[Path, Path]]:
    files: list[tuple[Path, Path]] = []
    for directory, dirnames, filenames in os.walk(renderer_root, followlinks=False):
        current = Path(directory)
        relative_directory = current.relative_to(renderer_root)
        if relative_directory == Path("."):
            dirnames[:] = sorted(
                name for name in dirnames if name not in SOURCE_EXCLUDED_DIRECTORIES
            )
        else:
            dirnames.sort()
        for dirname in dirnames:
            candidate = current / dirname
            if candidate.is_symlink():
                raise StageError(f"renderer snapshot contains a symlinked directory: {candidate}")
        for filename in sorted(filenames):
            # The story render receives the supplied episode storyboard below.
            # Keep the uploaded-pages fixture because uploadedStoryboard.ts
            # imports it at type-check/build time even for PictureSilent.
            if filename in {"storyboard.json", "storyboard.generated.json"}:
                continue
            candidate = current / filename
            ensure_plain_file(candidate, label="renderer snapshot")
            files.append((candidate.relative_to(renderer_root), candidate))
    return files


def protected_renderer_state(renderer_root: Path) -> dict[str, Any]:
    storyboard_entries: list[dict[str, Any]] = []
    for path in sorted(renderer_root.glob("storyboard*.json")):
        ensure_plain_file(path, label="protected renderer storyboard")
        storyboard_entries.append(
            {
                "path": path.name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )

    out_root = renderer_root / "out"
    out_entries: list[dict[str, Any]] = []
    if out_root.exists() or out_root.is_symlink():
        if out_root.is_symlink() or not out_root.is_dir():
            raise StageError(f"renderer out must be a plain directory: {out_root}")
        for directory, dirnames, filenames in os.walk(out_root, followlinks=False):
            current = Path(directory)
            relative_directory = current.relative_to(out_root)
            dirnames.sort()
            filenames.sort()
            for dirname in dirnames:
                candidate = current / dirname
                if candidate.is_symlink():
                    out_entries.append(
                        {
                            "path": (relative_directory / dirname).as_posix(),
                            "type": "symlink",
                            "target": os.readlink(candidate),
                        }
                    )
                else:
                    out_entries.append(
                        {
                            "path": (relative_directory / dirname).as_posix(),
                            "type": "directory",
                        }
                    )
            for filename in filenames:
                candidate = current / filename
                relative = (relative_directory / filename).as_posix()
                if candidate.is_symlink():
                    out_entries.append(
                        {
                            "path": relative,
                            "type": "symlink",
                            "target": os.readlink(candidate),
                        }
                    )
                else:
                    ensure_plain_file(candidate, label="renderer out")
                    out_entries.append(
                        {
                            "path": relative,
                            "type": "file",
                            "sha256": sha256_file(candidate),
                            "bytes": candidate.stat().st_size,
                        }
                    )
    state = {
        "storyboards": storyboard_entries,
        "out": {
            "exists": out_root.exists(),
            "entries": sorted(out_entries, key=lambda item: (item["path"], item["type"])),
        },
    }
    return {
        "sha256": sha256_bytes(canonical_json_bytes(state)),
        "state": state,
    }


def copy_hashed_file(source: Path, destination: Path, *, relative: str) -> dict[str, Any]:
    source_hash = sha256_file(source)
    source_size = source.stat().st_size
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination, follow_symlinks=False)
    destination_hash = sha256_file(destination)
    if source_hash != destination_hash or source_size != destination.stat().st_size:
        raise StageError(f"copied file failed integrity verification: {relative}")
    return {
        "path": relative,
        "sha256": destination_hash,
        "bytes": source_size,
    }


def staged_file_manifest(staging_root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for directory, dirnames, filenames in os.walk(staging_root, followlinks=False):
        current = Path(directory)
        dirnames[:] = sorted(name for name in dirnames if name != "node_modules")
        for filename in sorted(filenames):
            if filename == PROVENANCE_FILENAME:
                continue
            path = current / filename
            if path.is_symlink():
                raise StageError(f"unexpected symlink in staged renderer: {path}")
            ensure_plain_file(path, label="staged renderer")
            entries.append(
                {
                    "path": path.relative_to(staging_root).as_posix(),
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                }
            )
    return sorted(entries, key=lambda item: item["path"])


def stage_renderer(renderer_root: Path, storyboard_path: Path, destination: Path) -> dict[str, Any]:
    renderer_root = renderer_root.expanduser().resolve()
    storyboard_path = storyboard_path.expanduser().resolve()
    destination = destination.expanduser().resolve(strict=False)

    if not renderer_root.is_dir():
        raise StageError(f"renderer root does not exist: {renderer_root}")
    if renderer_root.is_symlink():
        raise StageError(f"renderer root must not be a symlink: {renderer_root}")
    if is_relative_to(destination, renderer_root):
        raise StageError("destination must be outside the source renderer")
    if os.path.lexists(destination):
        raise StageError(f"destination already exists: {destination}")
    if not destination.parent.is_dir():
        raise StageError(f"destination parent does not exist: {destination.parent}")

    node_modules = renderer_root / "node_modules"
    if not node_modules.is_dir():
        raise StageError(f"renderer node_modules directory does not exist: {node_modules}")
    if node_modules.is_symlink():
        node_modules_target = node_modules.resolve()
    else:
        node_modules_target = node_modules

    public_root = renderer_root / "public"
    if public_root.is_symlink() or not public_root.is_dir():
        raise StageError(f"renderer public must be a plain directory: {public_root}")
    storyboard, storyboard_bytes = load_storyboard(storyboard_path)
    referenced_assets = collect_referenced_assets(storyboard, public_root)
    font_files = iter_plain_files(public_root / "fonts", label="renderer public/fonts")
    renderer_files = iter_renderer_snapshot_files(renderer_root)
    protected_before = protected_renderer_state(renderer_root)

    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.stage-",
            dir=destination.parent,
        )
    )
    completed = False
    try:
        renderer_manifest: list[dict[str, Any]] = []
        for relative, source in renderer_files:
            renderer_manifest.append(
                copy_hashed_file(
                    source,
                    temporary / relative,
                    relative=relative.as_posix(),
                )
            )

        asset_manifest: list[dict[str, Any]] = []
        for asset in referenced_assets:
            relative = Path(*PurePosixPath(asset["path"]).parts)
            entry = copy_hashed_file(
                asset["source"],
                temporary / "public" / relative,
                relative=f"public/{asset['path']}",
            )
            entry["storyboard_path"] = asset["path"]
            entry["referenced_by"] = sorted(asset["referenced_by"])
            asset_manifest.append(entry)

        font_manifest: list[dict[str, Any]] = []
        for relative, source in font_files:
            font_manifest.append(
                copy_hashed_file(
                    source,
                    temporary / "public" / "fonts" / relative,
                    relative=f"public/fonts/{relative.as_posix()}",
                )
            )

        for filename in ("storyboard.json", "storyboard.generated.json"):
            target = temporary / filename
            target.write_bytes(storyboard_bytes)
            if sha256_file(target) != sha256_bytes(storyboard_bytes):
                raise StageError(f"installed storyboard failed integrity verification: {filename}")

        os.symlink(str(node_modules_target), temporary / "node_modules", target_is_directory=True)

        staged_manifest = staged_file_manifest(temporary)
        protected_after = protected_renderer_state(renderer_root)
        if protected_after["sha256"] != protected_before["sha256"]:
            raise StageError(
                "source renderer storyboard*.json or out/ changed while staging; "
                "discarding isolated renderer"
            )

        provenance = {
            "schema": PROVENANCE_SCHEMA,
            "source": {
                "renderer_root": str(renderer_root),
                "storyboard": str(storyboard_path),
                "storyboard_sha256": sha256_bytes(storyboard_bytes),
                "renderer_snapshot_sha256": manifest_digest(renderer_manifest),
                "protected_state_sha256": protected_before["sha256"],
                "node_modules_target": str(node_modules_target),
            },
            "destination": str(destination),
            "staged": {
                "tree_sha256": manifest_digest(staged_manifest),
                "renderer_files": sorted(renderer_manifest, key=lambda item: item["path"]),
                "referenced_assets": sorted(asset_manifest, key=lambda item: item["path"]),
                "fonts": sorted(font_manifest, key=lambda item: item["path"]),
                "files": staged_manifest,
                "storyboards": {
                    "storyboard.json": sha256_bytes(storyboard_bytes),
                    "storyboard.generated.json": sha256_bytes(storyboard_bytes),
                },
            },
            "invariants": {
                "destination_preexisted": False,
                "referenced_assets_validated": True,
                "source_protected_state_unchanged": True,
                "source_public_assets_copied_selectively": True,
            },
        }
        (temporary / PROVENANCE_FILENAME).write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        if os.path.lexists(destination):
            raise StageError(f"destination appeared while staging: {destination}")
        temporary.rename(destination)
        completed = True
        return provenance
    finally:
        if not completed and temporary.exists():
            shutil.rmtree(temporary)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage an immutable, episode-local copy of the story renderer."
    )
    parser.add_argument("--renderer-root", type=Path, required=True)
    parser.add_argument("--storyboard", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        provenance = stage_renderer(
            args.renderer_root,
            args.storyboard,
            args.destination,
        )
    except StageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "destination": provenance["destination"],
                "tree_sha256": provenance["staged"]["tree_sha256"],
                "provenance": str(Path(provenance["destination"]) / PROVENANCE_FILENAME),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
