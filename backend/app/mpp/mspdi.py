from __future__ import annotations

from xml.etree import ElementTree as ET


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def child_text(parent: ET.Element, name: str) -> str | None:
    for child in list(parent):
        if local_name(child.tag) == name:
            return child.text
    return None


def has_child(parent: ET.Element, name: str) -> bool:
    return any(local_name(child.tag) == name for child in list(parent))


def inspect_mspdi(xml: bytes) -> list[str]:
    """Return problems with an MSPDI document. Empty list means the file is usable."""
    if b"Project" not in xml:
        return ["document is not MSPDI XML"]
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        return [f"XML parse error: {exc}"]

    tasks = [element for element in root.iter() if local_name(element.tag) == "Task"]
    if not tasks:
        return ["no Task elements"]

    problems: list[str] = []
    levels = {child_text(task, "OutlineLevel") for task in tasks}
    if not any(level and level not in {"0", "1"} for level in levels) and len(levels) < 2:
        problems.append("task hierarchy (OutlineLevel) is missing")

    if not any(child_text(task, "Milestone") in {"1", "true", "True"} for task in tasks):
        problems.append("no milestone tasks")

    if not any((child_text(task, "Name") or "").startswith("Set ") for task in tasks):
        problems.append("no Set summary tasks")

    if not any(has_child(task, "PredecessorLink") for task in tasks):
        problems.append("no predecessor links")

    leaf_durations = [
        child_text(task, "Duration")
        for task in tasks
        if child_text(task, "Milestone") not in {"1", "true", "True"}
        and child_text(task, "Summary") not in {"1", "true", "True"}
    ]
    if leaf_durations and not any(
        duration and ("PT8H" in duration or "P1D" in duration)
        for duration in leaf_durations
        if duration
    ):
        problems.append("leaf tasks do not use a one-day duration")

    for task in tasks:
        percent = child_text(task, "PercentComplete")
        if percent not in {None, "0", "0.0"}:
            problems.append("percent complete is not 0")
            break

    if any(local_name(element.tag) == "Assignment" for element in root.iter()):
        problems.append("resource assignments are present")
    return problems
