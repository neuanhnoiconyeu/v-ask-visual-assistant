"""Workspace file selection, tree construction, and bounded multi-file AI context."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from config import MAX_SELECTED_WORKSPACE_CONTEXT_CHARS, MAX_WORKSPACE_CONTEXT_CHARS
from workspace_reader import (
    WorkspaceError,
    WorkspaceIndex,
    read_workspace_file,
    search_workspace,
)

_FILE_HEADER = re.compile(r"(?m)^File: (.+?)(?: \(lines \d+-\d+\))?$")
_BACKTICK_RUN = re.compile(r"`+")


def _code_fence(text: str) -> str:
    """Choose a Markdown fence that cannot be closed by an in-file backtick run."""
    longest = max((len(run) for run in _BACKTICK_RUN.findall(text)), default=0)
    return "`" * max(3, longest + 1)


@dataclass
class FileTreeNode:
    directories: dict[str, "FileTreeNode"] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FileContextIssue:
    path: str
    reason: str


@dataclass(frozen=True)
class SelectedFileContext:
    content: str
    included_files: tuple[str, ...]
    omitted_files: tuple[FileContextIssue, ...]
    truncated_files: tuple[str, ...]
    char_count: int
    estimated_tokens: int


@dataclass(frozen=True)
class WorkspaceContext:
    content: str
    included_files: tuple[str, ...]
    retrieved_files: tuple[str, ...]
    omitted_files: tuple[FileContextIssue, ...]
    truncated_files: tuple[str, ...]
    char_count: int
    estimated_tokens: int


def build_file_tree(index: WorkspaceIndex) -> FileTreeNode:
    """Build a browsable tree using only safe files accepted by the workspace index."""
    root = FileTreeNode()
    for indexed_file in index.files:
        parts = PurePosixPath(indexed_file.relative_path).parts
        if not parts:
            continue
        node = root
        for directory in parts[:-1]:
            node = node.directories.setdefault(directory, FileTreeNode())
        node.files.append(indexed_file.relative_path)
    return root


def assemble_selected_files(
    index: WorkspaceIndex,
    selected_paths: tuple[str, ...] | list[str] | set[str],
    *,
    max_chars: int = MAX_SELECTED_WORKSPACE_CONTEXT_CHARS,
) -> SelectedFileContext:
    """Reread selected indexed files safely and render bounded, explicit file boundaries."""
    if max_chars < 0:
        raise ValueError("Context limit cannot be negative.")
    indexed_paths = {file.relative_path for file in index.files}
    requested = sorted(set(selected_paths))
    blocks: list[str] = []
    included: list[str] = []
    omitted: list[FileContextIssue] = []
    truncated: list[str] = []
    used = 0

    for position, relative_path in enumerate(requested):
        if relative_path not in indexed_paths:
            omitted.append(FileContextIssue(
                relative_path,
                "This file is not in the current index. Refresh the workspace and select it again.",
            ))
            continue
        if used >= max_chars:
            omitted.append(FileContextIssue(relative_path, "The selected-file context limit has been reached."))
            continue
        try:
            file_text, _ = read_workspace_file(index.root, relative_path)
        except WorkspaceError as exc:
            omitted.append(FileContextIssue(relative_path, str(exc)))
            continue

        suffix = Path(relative_path).suffix.lstrip(".") or "text"
        fence = _code_fence(file_text)
        prefix = f"File: {relative_path}\n{fence}{suffix}\n"
        ending = f"\n{fence}"
        full_block = prefix + file_text + ending
        separator = "\n\n---\n\n" if blocks else ""
        remaining = max_chars - used - len(separator)
        if len(full_block) <= remaining:
            blocks.append(separator + full_block)
            included.append(relative_path)
            used += len(separator) + len(full_block)
            continue

        marker = "\n... [file content truncated to fit the selected-file context limit]"
        content_room = remaining - len(prefix) - len(marker) - len(ending)
        if content_room > 0:
            excerpt = file_text[:content_room]
            last_newline = excerpt.rfind("\n")
            if last_newline >= int(content_room * .6):
                excerpt = excerpt[:last_newline]
            partial_block = prefix + excerpt + marker + ending
            blocks.append(separator + partial_block)
            included.append(relative_path)
            truncated.append(relative_path)
            used += len(separator) + len(partial_block)
        else:
            omitted.append(FileContextIssue(
                relative_path,
                "Not enough context budget remained to include this file's path and content.",
            ))
        for following in requested[position + 1:]:
            omitted.append(FileContextIssue(following, "The selected-file context limit was reached."))
        break

    content = "".join(blocks)
    return SelectedFileContext(
        content=content,
        included_files=tuple(included),
        omitted_files=tuple(omitted),
        truncated_files=tuple(truncated),
        char_count=len(content),
        estimated_tokens=math.ceil(len(content) / 4),
    )


def build_workspace_context(
    index: WorkspaceIndex | None,
    query: str,
    selected_paths: tuple[str, ...] | list[str] | set[str] = (),
    *,
    max_context_chars: int = MAX_WORKSPACE_CONTEXT_CHARS,
    max_selected_chars: int = MAX_SELECTED_WORKSPACE_CONTEXT_CHARS,
) -> WorkspaceContext:
    """Prioritize selected full files, then fill remaining budget with existing RAG excerpts."""
    if max_context_chars < 0 or max_selected_chars < 0:
        raise ValueError("Context limits cannot be negative.")
    if index is None:
        issues = tuple(
            FileContextIssue(path, "Select and index a workspace before including this file.")
            for path in sorted(set(selected_paths))
        )
        return WorkspaceContext("", (), (), issues, (), 0, 0)

    selected_label = "Selected workspace files (full contents):\n"
    search_label = "Relevant workspace excerpts:\n"
    selected_budget = min(
        max_selected_chars,
        max(0, max_context_chars - len(selected_label) - len(search_label) - 4),
    )
    selected = assemble_selected_files(index, selected_paths, max_chars=selected_budget)
    sections: list[str] = []
    if selected.content:
        sections.append(selected_label + selected.content)

    used = sum(len(section) for section in sections)
    separator_size = 2 if sections else 0
    search_budget = max(
        0,
        max_context_chars - used - separator_size - (len(search_label) if query.strip() else 0),
    )
    retrieved = ""
    if query.strip() and search_budget >= 100:
        retrieved = search_workspace(
            index,
            query,
            max_context_chars=search_budget,
            exclude_paths=set(selected.included_files) - set(selected.truncated_files),
        )
        if retrieved.startswith("File:"):
            sections.append(search_label + retrieved)

    content = "\n\n".join(sections)
    # Keep a defensive bound if labels or future formatting change.
    content = content[:max_context_chars]
    retrieved_paths: list[str] = []
    for match in _FILE_HEADER.finditer(retrieved):
        path = match.group(1)
        if path not in selected.included_files and path not in retrieved_paths:
            retrieved_paths.append(path)
    return WorkspaceContext(
        content=content,
        included_files=selected.included_files,
        retrieved_files=tuple(retrieved_paths),
        omitted_files=selected.omitted_files,
        truncated_files=selected.truncated_files,
        char_count=len(content),
        estimated_tokens=math.ceil(len(content) / 4),
    )
