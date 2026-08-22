from __future__ import annotations

from app.errors import AppError
from app.plan.expand import PlanConfiguration
from app.plan.library import PHASE_SEQUENCE, PHASES, SET_DELIVERABLES


def validate_plan_configuration(config: PlanConfiguration) -> None:
    if not config.phases:
        raise AppError(
            400,
            "PLAN_EMPTY",
            "At least one phase is required",
            retryable=False,
        )
    if not 1 <= config.common_set_count <= 99:
        raise AppError(
            400,
            "SET_COUNT_INVALID",
            "Set count must be a whole number from 1 through 99",
            retryable=False,
        )
    known_phases = {phase["id"] for phase in PHASES}
    known_deliverables = {
        item["id"]: phase["id"]
        for phase in PHASES
        for item in phase["deliverables"]
    }
    selected: list[str] = []
    seen: set[str] = set()
    for selection in config.phases:
        if selection.phase_id not in known_phases:
            raise AppError(
                400,
                "UNKNOWN_PHASE",
                f"Unknown phase: {selection.phase_id}",
                retryable=False,
            )
        if selection.phase_id in seen:
            raise AppError(
                400,
                "DUPLICATE_PHASE",
                f"Phase {selection.phase_id} is selected more than once",
                retryable=False,
            )
        seen.add(selection.phase_id)
        selected.append(selection.phase_id)
        for deliverable_id in selection.deliverables:
            if deliverable_id not in known_deliverables:
                raise AppError(
                    400,
                    "UNKNOWN_DELIVERABLE",
                    f"Unknown deliverable: {deliverable_id}",
                    retryable=False,
                )
            if known_deliverables[deliverable_id] != selection.phase_id:
                raise AppError(
                    400,
                    "UNKNOWN_DELIVERABLE",
                    f"Deliverable {deliverable_id} does not belong to {selection.phase_id}",
                    retryable=False,
                )
            if deliverable_id in SET_DELIVERABLES:
                count = selection.set_overrides.get(deliverable_id, config.common_set_count)
                if not 1 <= count <= 99:
                    raise AppError(
                        400,
                        "SET_COUNT_INVALID",
                        "Set count must be a whole number from 1 through 99",
                        retryable=False,
                    )
    order = {phase_id: index for index, phase_id in enumerate(selected)}
    conflicts: list[list[str]] = []
    for predecessor, successor in PHASE_SEQUENCE:
        if predecessor in order and successor in order and order[successor] < order[predecessor]:
            conflicts.append([predecessor, successor])
    if conflicts:
        raise AppError(
            409,
            "SEQUENCE_CONFLICT",
            "Configured phase sequence conflicts with approved dependency rules",
            retryable=False,
            details={"conflicting_phases": conflicts},
        )
