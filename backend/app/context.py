from contextvars import ContextVar

current_operator_id: ContextVar[str | None] = ContextVar("current_operator_id", default=None)
current_operator_role: ContextVar[str | None] = ContextVar("current_operator_role", default=None)
