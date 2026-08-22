"""Approved Project Plan Template Library (WO-23)."""

from __future__ import annotations

PHASES: list[dict] = [
    {
        "id": "discovery",
        "name": "Discovery",
        "deliverables": [
            {
                "id": "discovery_kickoff",
                "name": "Discovery kickoff",
                "set_based": False,
                "tasks": ["Project kickoff", "Stakeholder interviews"],
                "milestones": ["Discovery complete"],
            }
        ],
    },
    {
        "id": "ux",
        "name": "UX",
        "deliverables": [
            {
                "id": "ux_research",
                "name": "UX research",
                "set_based": False,
                "tasks": ["User research", "Persona and journey review"],
                "milestones": [],
            },
            {
                "id": "wireframe_creation",
                "name": "Wireframe creation",
                "set_based": True,
                "tasks": ["Wireframe draft", "Wireframe review"],
                "milestones": ["Wireframes approved"],
            },
            {
                "id": "brand_guidelines_existing",
                "name": "Brand guidelines (existing)",
                "set_based": False,
                "tasks": ["Review existing brand guidelines"],
                "milestones": [],
            },
            {
                "id": "brand_guidelines_create",
                "name": "Brand guidelines (create)",
                "set_based": False,
                "tasks": ["Draft brand guidelines", "Brand guidelines review"],
                "milestones": ["Brand guidelines approved"],
            },
        ],
    },
    {
        "id": "ui",
        "name": "UI",
        "deliverables": [
            {
                "id": "ui_creation",
                "name": "UI creation",
                "set_based": True,
                "tasks": ["UI draft", "UI review"],
                "milestones": ["UI approved"],
            }
        ],
    },
    {
        "id": "html",
        "name": "HTML",
        "deliverables": [
            {
                "id": "html",
                "name": "HTML",
                "set_based": True,
                "tasks": ["HTML build", "HTML review"],
                "milestones": ["HTML complete"],
            }
        ],
    },
    {
        "id": "cms",
        "name": "CMS",
        "deliverables": [
            {
                "id": "cms",
                "name": "CMS",
                "set_based": True,
                "prereq_tasks": ["CMS information architecture", "CMS environment setup"],
                "prereq_milestones": ["CMS foundation ready"],
                "tasks": ["CMS template build", "CMS content load"],
                "milestones": ["CMS set complete"],
            }
        ],
    },
    {
        "id": "qa",
        "name": "QA",
        "deliverables": [
            {
                "id": "qa",
                "name": "QA",
                "set_based": True,
                "tasks": ["QA script", "QA execution"],
                "milestones": ["QA complete"],
            }
        ],
    },
    {
        "id": "uat",
        "name": "UAT",
        "deliverables": [
            {
                "id": "uat",
                "name": "UAT",
                "set_based": True,
                "tasks": ["UAT script", "UAT execution"],
                "milestones": ["UAT signed off"],
            }
        ],
    },
    {
        "id": "launch",
        "name": "Launch",
        "deliverables": [
            {
                "id": "launch",
                "name": "Launch",
                "set_based": False,
                "tasks": ["Launch checklist", "Go-live"],
                "milestones": ["Launched"],
            }
        ],
    },
]

# Sequential FS links between phase ids. Omitted phases drop the edge (no rewrite).
PHASE_SEQUENCE = [
    ("discovery", "ux"),
    ("ux", "ui"),
    ("ui", "html"),
    ("html", "cms"),
    ("cms", "qa"),
    ("qa", "uat"),
    ("uat", "launch"),
]

# Intra-phase deliverable predecessors. Parallel work has no edge.
DELIVERABLE_SEQUENCE = [
    ("ux_research", "wireframe_creation"),
    ("brand_guidelines_create", "ui_creation"),
    ("wireframe_creation", "ui_creation"),
]

SET_DELIVERABLES = {
    "wireframe_creation",
    "ui_creation",
    "html",
    "cms",
    "qa",
    "uat",
}

BRAND_GUIDELINE_MODES = {"brand_guidelines_existing", "brand_guidelines_create"}


def catalog() -> dict:
    return {
        "phases": [
            {
                "id": phase["id"],
                "name": phase["name"],
                "deliverables": [
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "set_based": item["set_based"],
                    }
                    for item in phase["deliverables"]
                ],
            }
            for phase in PHASES
        ],
        "set_deliverables": sorted(SET_DELIVERABLES),
        "brand_guideline_modes": sorted(BRAND_GUIDELINE_MODES),
        "phase_sequence": PHASE_SEQUENCE,
    }
