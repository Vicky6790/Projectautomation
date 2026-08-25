SOW_CRITERIA = (
    "Classify only from the supplied SOW text. Do not invent facts.\n"
    "A passage may support more than one finding if it independently meets each rule.\n"
    "If evidence is insufficient, leave that category as an empty list. Never omit a key.\n"
    "- gray_areas: ambiguous, conflicting, or undefined language.\n"
    "- risks: stated or clearly implied threats to scope, schedule, cost, quality, or compliance.\n"
    "- missing_requirements: expected SOW content that is absent "
    "(acceptance criteria, SLAs, RACI, out-of-scope, deliverable definition).\n"
    "- assumptions: unstated conditions the SOW appears to rely on.\n"
    "- dependencies: internal or external items the work relies on.\n"
    "- clarification_questions: questions the PM should ask to resolve ambiguity or gaps.\n"
)

WSR_CRITERIA = (
    "Use only the supplied facts and evidence catalog. Do not invent actuals, "
    "tasks, or project health. Health is computed outside this prompt.\n"
    "- client_needs: client actions, prerequisites, or reviews required to progress.\n"
    "- risks: potential future problems or focus areas.\n"
    "- issues: current problems already occurring.\n"
    "- dependencies: internal or external predecessors.\n"
    "- management_attention: items needing executive awareness.\n"
    "- decisions_required: choices that must be made.\n"
    "- next_7_day_priorities: work due in the next 7 days from the as-of date.\n"
    "Every item must include evidence_names that exist in the catalog. "
    "If evidence is insufficient, leave that category as an empty list.\n"
)

RETRO_CRITERIA = (
    "Use planned vs actual evidence only. "
    "If no actuals exist, set planned_only true and do not invent actuals.\n"
    "- what_went_well: on-time or early items and met milestones.\n"
    "- what_went_poorly: slipped tasks, missed milestones, overruns.\n"
    "- lessons_learned and recommendations must be grounded in that evidence.\n"
    "- schedule_variance, milestone_delivery, and task_completion summarize the metrics.\n"
    "Empty categories stay empty lists.\n"
)
