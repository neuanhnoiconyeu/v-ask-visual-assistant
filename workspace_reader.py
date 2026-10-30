"""Safe, bounded, read-only indexing and retrieval for a selected project workspace."""
from __future__ import annotations

import os
import re
import stat
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from config import MAX_WORKSPACE_CONTEXT_CHARS


MAX_FILE_BYTES = 512 * 1024
MAX_INDEX_BYTES = 20 * 1024 * 1024
MAX_INDEX_FILES = 2_000
MAX_SCAN_ENTRIES = 25_000

SUPPORTED_SUFFIXES = {
    ".py", ".pyi", ".java", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx",
    ".c", ".h", ".cc", ".hh", ".cpp", ".hpp", ".hxx", ".cxx", ".cs",
    ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".kts", ".scala",
    ".sql", ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd", ".html",
    ".css", ".scss", ".sass", ".vue", ".svelte", ".md", ".rst", ".txt",
    ".toml", ".ini", ".cfg", ".conf", ".yaml", ".yml", ".json", ".xml",
    ".gradle", ".properties", ".tf", ".hcl", ".dockerfile",
}
SUPPORTED_FILENAMES = {
    "dockerfile", "makefile", "cmakelists.txt", "justfile", "procfile",
    "go.mod", "go.sum", "cargo.toml", "cargo.lock", "package.json",
    "tsconfig", "pyproject.toml", "requirements.txt",
}
EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules", "vendor",
    "build", "dist", "target", "out", "coverage", "htmlcov", ".next", ".nuxt",
    ".cache", "cache", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".tox", ".nox", "site-packages", ".idea", ".vscode",
}
SENSITIVE_DIRS = {
    ".aws", ".ssh", ".azure", ".gcloud", ".kube", ".gnupg", "secrets",
    "credentials", ".credentials",
}
SENSITIVE_FILENAMES = {
    ".npmrc", ".pypirc", ".netrc", ".git-credentials", "credentials",
    "credentials.json", "secrets", "secrets.json", "secrets.toml", "id_rsa",
    "id_ed25519", "id_ecdsa", "known_hosts", "authorized_keys",
    "service-account.json", "dockerconfig.json",
}
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".der", ".keystore"}

_SECRET_ASSIGNMENT_RE = re.compile(
    r"""(?im)^\s*(?:export\s+)?[\"']?[A-Z0-9_]*(?:API[_-]?KEY|ACCESS[_-]?KEY|SECRET|PASSWORD|PASSWD|TOKEN|CLIENT[_-]?SECRET)[A-Z0-9_]*[\"']?\s*[:=]\s*(?:"[^"\r\n]{4,}"|'[^'\r\n]{4,}')"""
)
_UNQUOTED_SECRET_RE = re.compile(
    r"""(?im)^\s*(?:export\s+)?[\"']?[A-Z0-9_]*(?:API[_-]?KEY|ACCESS[_-]?KEY|SECRET|PASSWORD|PASSWD|TOKEN|CLIENT[_-]?SECRET)[A-Z0-9_]*[\"']?\s*[:=]\s*(?!(?:\$\{|\$[A-Z_]|os\.|process\.env|System\.getenv|env\(|getenv\())[A-Za-z0-9_./+=-]{12,}\s*(?:#.*)?$"""
)
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
_INLINE_JSON_SECRET_RE = re.compile(
    r'''(?i)["'][A-Z0-9_]*(?:API[_-]?KEY|ACCESS[_-]?KEY|SECRET|PASSWORD|PASSWD|TOKEN|CLIENT[_-]?SECRET)[A-Z0-9_]*["']\s*:\s*["'][^"'\r\n]{4,}["']'''
)
_TOKEN_RE = re.compile(
    r"(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|"
    r"sk-(?:live_)?[A-Za-z0-9_-]{24,}|AIza[0-9A-Za-z_-]{30,}|xox[baprs]-[A-Za-z0-9-]{20,}|"
    r"(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^/\s:@]+:[^@\s]+@)"
)
_QUERY_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}|[0-9]{2,}")
_STOP_WORDS = {
    "the", "and", "for", "with", "from", "that", "this", "what", "where",
    "when", "does", "how", "why", "can", "could", "would", "should", "about",
    "into", "file", "code", "function", "class", "please", "explain", "find",
}


class WorkspaceError(ValueError):
    """Safe-to-display workspace validation error without raw OS details."""


@dataclass(frozen=True)
class IndexedFile:
    relative_path: str
    text: str
    size_bytes: int


@dataclass(frozen=True)
class WorkspaceIndex:
    root: Path
    files: tuple[IndexedFile, ...]
    total_bytes: int
    skipped_files: int
    skipped_bytes: int
    truncated: bool

    @property
    def file_count(self) -> int:
        return len(self.files)


def resolve_workspace(path: str | os.PathLike[str]) -> Path:
    """Resolve and validate a user-selected workspace directory."""
    try:
        root = Path(path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise WorkspaceError("The selected workspace path could not be opened.") from exc
    if not root.is_dir():
        raise WorkspaceError("Select an existing project directory.")
    return root


def resolve_workspace_file(root: str | os.PathLike[str], relative_path: str) -> Path:
    """Validate a relative file path and ensure it stays inside the resolved root."""
    canonical_root = resolve_workspace(root)
    if not isinstance(relative_path, str) or not relative_path or "\x00" in relative_path:
        raise WorkspaceError("Invalid workspace-relative file path.")
    normalized = relative_path.replace("\\", "/")
    candidate_posix = PurePosixPath(normalized)
    if candidate_posix.is_absolute() or re.match(r"^[A-Za-z]:", normalized):
        raise WorkspaceError("Invalid workspace-relative file path.")
    if os.name == "nt" and any(":" in part for part in candidate_posix.parts):
        raise WorkspaceError("Invalid workspace-relative file path.")
    if any(part in {"", ".", ".."} for part in candidate_posix.parts):
        raise WorkspaceError("Invalid workspace-relative file path.")
    candidate = canonical_root.joinpath(*candidate_posix.parts)
    current = canonical_root
    try:
        for part in candidate_posix.parts:
            current = current / part
            if _is_symlink_or_reparse_point(current):
                raise WorkspaceError("Symbolic links and junctions are not indexed.")
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(canonical_root)
        if not resolved.is_file():
            raise WorkspaceError("The selected workspace entry is not a regular file.")
    except WorkspaceError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise WorkspaceError("The selected file is unavailable inside this workspace.") from exc
    return resolved


def _is_sensitive_path(relative_path: str) -> bool:
    parts = PurePosixPath(relative_path).parts
    if any(part.casefold() in SENSITIVE_DIRS for part in parts[:-1]):
        return True
    name = parts[-1].casefold()
    if name in SENSITIVE_FILENAMES or name.startswith(".env"):
        return True
    if Path(name).suffix.casefold() in SENSITIVE_SUFFIXES:
        return True
    if any(marker in name for marker in ("credential", "secret", "private_key", "service-account")):
        return True
    return False


def validate_workspace_target(
    root: str | os.PathLike[str], relative_path: str, *, allow_create: bool = False
) -> tuple[Path, bool]:
    """Validate an existing or new source-file target using workspace exclusions."""
    canonical_root = resolve_workspace(root)
    if not isinstance(relative_path, str) or not relative_path or "\x00" in relative_path:
        raise WorkspaceError("Invalid workspace-relative file path.")
    normalized = relative_path.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if (
        PurePosixPath(normalized).is_absolute()
        or re.match(r"^[A-Za-z]:", normalized)
        or any(part in {"", ".", ".."} for part in parts)
        or (os.name == "nt" and any(":" in part for part in parts))
    ):
        raise WorkspaceError("Invalid workspace-relative file path.")
    if any(part.casefold() in EXCLUDED_DIRS for part in parts[:-1]):
        raise WorkspaceError("This path is excluded from workspace changes.")
    if _is_sensitive_path(normalized) or not _is_supported(normalized):
        raise WorkspaceError("This file type or sensitive path cannot be changed.")

    target = canonical_root.joinpath(*parts)
    if target.exists():
        resolved = resolve_workspace_file(canonical_root, normalized)
        return resolved, True
    if not allow_create:
        raise WorkspaceError("The target file no longer exists. Refresh the workspace and regenerate the proposal.")

    parent = target.parent
    try:
        try:
            target.lstat()
            raise WorkspaceError("The target file already exists. Refresh the workspace and regenerate the proposal.")
        except FileNotFoundError:
            pass
        resolved_parent = parent.resolve(strict=True)
        resolved_parent.relative_to(canonical_root)
        if not resolved_parent.is_dir():
            raise WorkspaceError("The target directory is unavailable inside this workspace.")
        current = canonical_root
        for part in parts[:-1]:
            current = current / part
            if _is_symlink_or_reparse_point(current):
                raise WorkspaceError("Symbolic links and junctions cannot be changed.")
    except WorkspaceError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise WorkspaceError("The target directory is unavailable inside this workspace.") from exc
    return target, False


def _is_supported(relative_path: str) -> bool:
    name = PurePosixPath(relative_path).name.casefold()
    return name in SUPPORTED_FILENAMES or Path(name).suffix.casefold() in SUPPORTED_SUFFIXES


def _contains_secret(text: str) -> bool:
    return bool(
        _PRIVATE_KEY_RE.search(text)
        or _SECRET_ASSIGNMENT_RE.search(text)
        or _INLINE_JSON_SECRET_RE.search(text)
        or _UNQUOTED_SECRET_RE.search(text)
        or _TOKEN_RE.search(text)
    )


def _code_fence(text: str) -> str:
    longest = max((len(match.group(0)) for match in re.finditer(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


def _is_symlink_or_reparse_point(path: Path) -> bool:
    """Reject symbolic links and Windows junction/mount-point reparse entries."""
    try:
        if path.is_symlink():
            return True
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return bool(attributes & reparse_flag)
    except OSError:
        return True


def _read_bounded_text(root: Path, relative_path: str, max_bytes: int) -> tuple[str, int] | None:
    try:
        path = resolve_workspace_file(root, relative_path)
        before = path.stat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
            return None
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or opened.st_size > max_bytes:
                return None
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                content = stream.read(max_bytes + 1)
            after = path.stat()
            resolved_after = path.resolve(strict=True)
            resolved_after.relative_to(root)
            if not os.path.samestat(opened, after) or len(content) > max_bytes:
                return None
            if b"\x00" in content:
                return None
            text = content.decode("utf-8", errors="strict")
            if _contains_secret(text):
                return None
            return text, len(content)
        finally:
            os.close(descriptor)
    except (OSError, RuntimeError, UnicodeError, ValueError, WorkspaceError):
        return None


def read_workspace_file(
    root: str | os.PathLike[str],
    relative_path: str,
    *,
    max_bytes: int = MAX_FILE_BYTES,
) -> tuple[str, int]:
    """Safely reread one supported workspace file without exposing OS or file contents in errors."""
    if max_bytes <= 0:
        raise ValueError("File read limit must be positive.")
    canonical_root = resolve_workspace(root)
    normalized = relative_path.replace("\\", "/") if isinstance(relative_path, str) else ""
    if any(ord(char) < 32 or ord(char) == 127 for char in normalized):
        raise WorkspaceError("Workspace paths with control characters are not supported.")
    parts = PurePosixPath(normalized).parts
    if any(part.casefold() in EXCLUDED_DIRS for part in parts[:-1]):
        raise WorkspaceError("This file is in an excluded workspace directory.")
    if not _is_supported(normalized) or _is_sensitive_path(normalized):
        raise WorkspaceError("This file type or sensitive path cannot be added to AI context.")
    path = resolve_workspace_file(canonical_root, normalized)
    loaded = _read_bounded_text(canonical_root, normalized, max_bytes)
    if loaded is None:
        raise WorkspaceError(
            "This file could not be read safely. It may be unreadable, binary, malformed, oversized, changed, or contain sensitive data."
        )
    return loaded


def index_workspace(
    path: str | os.PathLike[str],
    *,
    max_file_bytes: int = MAX_FILE_BYTES,
    max_total_bytes: int = MAX_INDEX_BYTES,
    max_files: int = MAX_INDEX_FILES,
    max_scan_entries: int = MAX_SCAN_ENTRIES,
) -> WorkspaceIndex:
    """Index supported text files within fixed byte/file limits, without writing to disk."""
    if min(max_file_bytes, max_total_bytes, max_files, max_scan_entries) <= 0:
        raise ValueError("Index limits must be positive.")
    root = resolve_workspace(path)
    indexed: list[IndexedFile] = []
    total_bytes = skipped_files = skipped_bytes = scanned_entries = 0
    truncated = False

    for directory, directory_names, filenames in os.walk(root, topdown=True, followlinks=False):
        current_dir = Path(directory)
        safe_dirs = []
        for name in sorted(directory_names):
            if name.casefold() in EXCLUDED_DIRS or name.casefold() in SENSITIVE_DIRS:
                continue
            candidate = current_dir / name
            try:
                if _is_symlink_or_reparse_point(candidate):
                    continue
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(root)
                if resolved.is_dir():
                    safe_dirs.append(name)
            except (OSError, RuntimeError, ValueError):
                continue
        directory_names[:] = safe_dirs

        for name in sorted(filenames):
            scanned_entries += 1
            if scanned_entries > max_scan_entries or len(indexed) >= max_files:
                truncated = True
                break
            path_obj = current_dir / name
            try:
                relative = path_obj.relative_to(root).as_posix()
            except ValueError:
                skipped_files += 1
                continue
            if any(ord(char) < 32 or ord(char) == 127 for char in relative):
                skipped_files += 1
                continue
            if not _is_supported(relative):
                continue
            if _is_sensitive_path(relative):
                skipped_files += 1
                continue
            try:
                expected_size = path_obj.lstat().st_size
                if _is_symlink_or_reparse_point(path_obj):
                    skipped_files += 1
                    continue
            except OSError:
                skipped_files += 1
                continue
            if expected_size > max_file_bytes:
                skipped_files += 1
                skipped_bytes += expected_size
                continue
            if expected_size > max_total_bytes - total_bytes:
                skipped_files += 1
                skipped_bytes += expected_size
                truncated = True
                continue
            loaded = _read_bounded_text(root, relative, max_file_bytes)
            if loaded is None:
                skipped_files += 1
                skipped_bytes += expected_size
                continue
            text, actual_size = loaded
            if actual_size > max_total_bytes - total_bytes:
                skipped_files += 1
                skipped_bytes += actual_size
                truncated = True
                continue
            indexed.append(IndexedFile(relative, text, actual_size))
            total_bytes += actual_size
        if truncated and (scanned_entries > max_scan_entries or len(indexed) >= max_files):
            break

    return WorkspaceIndex(root, tuple(indexed), total_bytes, skipped_files, skipped_bytes, truncated)


def _query_terms(query: str) -> list[str]:
    return [
        token.casefold()
        for token in _QUERY_TOKEN_RE.findall(query)
        if len(token) > 1 and token.casefold() not in _STOP_WORDS
    ]


def _truncate_workspace_excerpt(excerpt: str, max_chars: int) -> str | None:
    """Trim an excerpt while retaining its file header and balanced code fence."""
    try:
        header, language_line, code_and_fence = excerpt.split("\n", 2)
    except ValueError:
        return None
    fence_match = re.match(r"(`+)", language_line)
    if not fence_match:
        return None
    fence = fence_match.group(1)
    ending = "\n" + fence
    if not code_and_fence.endswith(ending):
        return None
    code = code_and_fence[:-len(ending)]
    prefix = f"{header}\n{language_line}\n"
    marker = "\n... [excerpt truncated to fit workspace context limit]"
    room = max_chars - len(prefix) - len(marker) - len(ending)
    if room <= 0:
        return None
    content = code[:room]
    last_newline = content.rfind("\n")
    if last_newline >= int(room * .6):
        content = content[:last_newline]
    result = prefix + content + marker + ending
    return result if len(result) <= max_chars else None


def search_workspace(
    index: WorkspaceIndex,
    query: str,
    *,
    max_results: int = 8,
    max_context_chars: int = MAX_WORKSPACE_CONTEXT_CHARS,
    lines_before: int = 3,
    lines_after: int = 8,
    max_lines_per_excerpt: int = 18,
    exclude_paths: Iterable[str] = (),
) -> str:
    """Find matching code and return bounded excerpts with relative paths and line ranges."""
    if not query.strip() or not index.files or max_results <= 0 or max_context_chars <= 0:
        return "No relevant code excerpts were found in the indexed workspace."
    terms = _query_terms(query)
    if not terms:
        return "No relevant code excerpts were found in the indexed workspace."

    excluded = set(exclude_paths)
    candidates: list[tuple[int, str, str]] = []
    for file in index.files:
        if file.relative_path in excluded:
            continue
        lines = file.text.splitlines()
        path_text = file.relative_path.casefold()
        matching_lines: list[tuple[int, int]] = []
        for line_number, line in enumerate(lines, start=1):
            folded = line.casefold()
            score = sum(folded.count(term) for term in terms)
            if score:
                matching_lines.append((score, line_number))
        path_score = sum(path_text.count(term) * 3 for term in terms)
        if not matching_lines and not path_score:
            continue

        matching_lines.sort(key=lambda item: (-item[0], item[1]))
        windows: list[tuple[int, int, int]] = []
        for score, line_number in matching_lines:
            start = max(1, line_number - lines_before)
            end = min(len(lines), line_number + lines_after)
            if end - start + 1 > max_lines_per_excerpt:
                end = start + max_lines_per_excerpt - 1
            overlapping = next(
                (i for i, (old_start, old_end, _) in enumerate(windows)
                 if start <= old_end + 1 and end >= old_start - 1),
                None,
            )
            if overlapping is None:
                windows.append((start, end, score))
            else:
                old_start, old_end, old_score = windows[overlapping]
                windows[overlapping] = (min(start, old_start), max(end, old_end), old_score + score)
        if not windows and path_score:
            end = min(len(lines), max_lines_per_excerpt)
            windows.append((1, end, path_score))

        ext = Path(file.relative_path).suffix.lstrip(".") or "text"
        for start, end, score in windows[:2]:
            excerpt_lines = []
            for number in range(start, end + 1):
                line = lines[number - 1]
                if len(line) > 1_000:
                    line = line[:1_000] + " … [line truncated]"
                excerpt_lines.append(f"{number}: {line}")
            excerpt_content = "\n".join(excerpt_lines)
            fence = _code_fence(excerpt_content)
            excerpt = (
                f"File: {file.relative_path} (lines {start}-{end})\n"
                f"{fence}{ext}\n{excerpt_content}\n{fence}"
            )
            candidates.append((score + path_score, file.relative_path, excerpt))

    candidates.sort(key=lambda item: (-item[0], item[1]))
    selected: list[str] = []
    used = 0
    separator = "\n\n---\n\n"
    for _, _, excerpt in candidates:
        separator_size = len(separator) if selected else 0
        cost = len(excerpt) + separator_size
        if used + cost > max_context_chars:
            remaining = max_context_chars - used - separator_size
            if remaining >= 100:
                truncated_excerpt = _truncate_workspace_excerpt(excerpt, remaining)
                if truncated_excerpt:
                    selected.append(truncated_excerpt)
            break
        selected.append(excerpt)
        used += cost
        if len(selected) >= max_results:
            break
    return "\n\n---\n\n".join(selected) if selected else "No relevant code excerpts were found in the indexed workspace."
