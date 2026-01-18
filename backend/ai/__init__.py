"""
backend/ai/__init__.py
Phase 10.1: AI Context Binding & Guardrails Module
"""

from backend.ai.context import resolve_ai_context, AIContext
from backend.ai.guards import enforce_scope, ScopeGuard
from backend.ai.prompts import SYSTEM_GUARD_PROMPT, build_scoped_prompt

__all__ = [
    "resolve_ai_context",
    "AIContext",
    "enforce_scope",
    "ScopeGuard",
    "SYSTEM_GUARD_PROMPT",
    "build_scoped_prompt"
]
