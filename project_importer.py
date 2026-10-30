"""Safe, managed imports for uploaded source project folders and ZIP archives."""
from __future__ import annotations

import json
import io
import shutil
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import uuid4

from config import (
    DATA_DIR,
    MAX_PROJECT_IMPORT_BYTES,
    MAX_PROJECT_IMPORT_FILE_BYTES,
    MAX_PROJECT_IMPORT_FILES,
    MAX_PROJECT_UPLOAD_MB,
)
from workspace_reader import EXCLUDED_DIRS, SENSITIVE_DIRS, _is_sensitive_path, _is_supported


METADATA_NAME = ".vask-project"
COMMON_PROJECT_DIRECTORIES = {"src", "tests", "test", "docs", "doc", "lib", "app", "config", "packages"}


class ProjectImportError(ValueError):
    """A safe-to-display error raised for unsafe or invalid project uploads."""


@dataclass(frozen=True)
class ImportedProject:
    project_id: str
    name: str
    root: Path
    imported_files: int
    skipped_files: int
    total_bytes: int


def _imports_root() -> Path:
    root = DATA_DIR / "imported_projects"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ProjectImportError("An uploaded file has an invalid path.")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or any(":" in part for part in path.parts)
        or any(ord(char) < 32 or ord(char) == 127 for char in normalized)
    ):
        raise ProjectImportError("Project archives cannot contain absolute or parent-directory paths.")
    return path.as_posix()


def _strip_common_root(entries: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    if not entries:
        return entries
    parts = [PurePosixPath(path).parts for path, _ in entries]
    first = parts[0][0]
    if (
        all(len(item) > 1 and item[0] == first for item in parts)
        and (len(entries) > 1 or first.casefold() not in COMMON_PROJECT_DIRECTORIES)
    ):
        return [(PurePosixPath(*item[1:]).as_posix(), content) for item, (_, content) in zip(parts, entries)]
    return entries


def _should_skip(relative_path: str) -> bool:
    parts = PurePosixPath(relative_path).parts
    if any(part.casefold() in EXCLUDED_DIRS | SENSITIVE_DIRS for part in parts[:-1]):
        return True
    return _is_sensitive_path(relative_path) or not _is_supported(relative_path)


def _project_name(name: str) -> str:
    candidate = Path(name).stem.strip() or "Imported project"
    return candidate[:80]


def _write_project(name: str, entries: list[tuple[str, bytes]]) -> ImportedProject:
    if len(entries) > MAX_PROJECT_IMPORT_FILES:
        raise ProjectImportError(f"A project can contain at most {MAX_PROJECT_IMPORT_FILES:,} files.")
    prepared: list[tuple[str, bytes]] = []
    raw_total = 0
    for relative_path, content in _strip_common_root(entries):
        safe_path = _safe_relative_path(relative_path)
        if not isinstance(content, bytes):
            raise ProjectImportError("An uploaded file could not be read.")
        raw_total += len(content)
        if raw_total > MAX_PROJECT_IMPORT_BYTES:
            raise ProjectImportError("The extracted project exceeds the configured import size limit.")
        if len(content) > MAX_PROJECT_IMPORT_FILE_BYTES:
            raise ProjectImportError("A project file exceeds the configured per-file size limit.")
        prepared.append((safe_path, content))

    imports_root = _imports_root()
    project_id = str(uuid4())
    final_root = imports_root / project_id
    skipped = imported = total_bytes = 0
    try:
        final_root.mkdir()
        for relative_path, content in prepared:
            if _should_skip(relative_path):
                skipped += 1
                continue
            target = final_root.joinpath(*PurePosixPath(relative_path).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            imported += 1
            total_bytes += len(content)
        if not imported:
            raise ProjectImportError("No supported, safe text files were found in this project.")
        metadata = {
            "id": project_id,
            "name": _project_name(name),
            "imported_files": imported,
            "skipped_files": skipped,
            "total_bytes": total_bytes,
        }
        (final_root / METADATA_NAME).write_text(json.dumps(metadata), encoding="utf-8")
        return ImportedProject(project_id, metadata["name"], final_root, imported, skipped, total_bytes)
    except Exception:
        shutil.rmtree(final_root, ignore_errors=True)
        raise


def import_project_folder(files: list[tuple[str, bytes]], *, name: str = "Uploaded project") -> ImportedProject:
    """Import browser directory-upload files while retaining their relative paths."""
    if not files:
        raise ProjectImportError("Choose a project folder with at least one file.")
    return _write_project(name, files)


def import_project_zip(name: str, archive: bytes) -> ImportedProject:
    """Safely validate and import a ZIP archive without extracting arbitrary paths."""
    if not archive:
        raise ProjectImportError("Choose a non-empty ZIP archive.")
    if len(archive) > MAX_PROJECT_UPLOAD_MB * 1024 * 1024:
        raise ProjectImportError(f"ZIP uploads are limited to {MAX_PROJECT_UPLOAD_MB} MiB.")
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            all_infos = bundle.infolist()
            for info in all_infos:
                _safe_relative_path(info.filename.rstrip("/"))
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode) or info.flag_bits & 0x1:
                    raise ProjectImportError("ZIP archives cannot contain links or encrypted files.")
            infos = [info for info in all_infos if not info.is_dir()]
            if len(infos) > MAX_PROJECT_IMPORT_FILES:
                raise ProjectImportError(f"A project can contain at most {MAX_PROJECT_IMPORT_FILES:,} files.")
            entries: list[tuple[str, bytes]] = []
            total_uncompressed = 0
            for info in infos:
                if info.file_size > MAX_PROJECT_IMPORT_FILE_BYTES:
                    raise ProjectImportError("A project file exceeds the configured per-file size limit.")
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_PROJECT_IMPORT_BYTES:
                    raise ProjectImportError("The extracted project exceeds the configured import size limit.")
                entries.append((info.filename, bundle.read(info)))
    except ProjectImportError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile):
        raise ProjectImportError("The uploaded file is not a readable ZIP archive.") from None
    return _write_project(name, entries)


def list_imported_projects() -> tuple[ImportedProject, ...]:
    projects: list[ImportedProject] = []
    for root in sorted(_imports_root().iterdir(), key=lambda item: item.name, reverse=True):
        metadata_path = root / METADATA_NAME
        if not root.is_dir() or not metadata_path.is_file():
            continue
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            projects.append(ImportedProject(
                str(metadata["id"]), str(metadata["name"]), root.resolve(),
                int(metadata["imported_files"]), int(metadata["skipped_files"]), int(metadata["total_bytes"]),
            ))
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
    return tuple(projects)


def remove_imported_project(project_id: str) -> None:
    if not project_id or Path(project_id).name != project_id:
        raise ProjectImportError("Invalid imported project.")
    target = _imports_root() / project_id
    try:
        target.resolve(strict=True).relative_to(_imports_root().resolve())
    except (OSError, RuntimeError, ValueError):
        raise ProjectImportError("The imported project is unavailable.") from None
    shutil.rmtree(target)
