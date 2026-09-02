"""WBS / outline-number identity for WSR.

``0`` is the parent of every project in the file.
A single integer (``1``, ``2``, …) is a project name row.
A single decimal (``1.1``, ``2.3``) is a phase of that project.
Deeper versioning (``1.1.1``) is a task, as in the current single-project WSR.
"""

from __future__ import annotations


def parse_outline_code(value: str | None) -> tuple[int, ...] | None:
    text = (value or "").strip()
    if not text:
        return None
    parts = text.split(".")
    if not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def is_portfolio_code(value: str | None) -> bool:
    return parse_outline_code(value) == (0,)


def is_project_code(value: str | None) -> bool:
    parts = parse_outline_code(value)
    return parts is not None and len(parts) == 1 and parts[0] >= 1


def is_phase_code(value: str | None, project_code: str | None = None) -> bool:
    parts = parse_outline_code(value)
    if parts is None or len(parts) != 2 or parts[0] < 1:
        return False
    if project_code:
        wanted = parse_outline_code(project_code)
        return wanted is not None and parts[0] == wanted[0]
    return parts[0] == 1


def is_project_or_phase_code(value: str | None) -> bool:
    parts = parse_outline_code(value)
    if parts is None:
        return False
    if parts == (0,):
        return True
    if len(parts) == 1 and parts[0] >= 1:
        return True
    return len(parts) == 2 and parts[0] >= 1


def project_id(value: str | None) -> int | None:
    parts = parse_outline_code(value)
    if not parts or parts[0] < 1:
        return None
    return parts[0]
