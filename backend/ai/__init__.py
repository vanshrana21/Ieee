"""
backend/ai/__init__.py
Phase 10.1 + 10.2 + 10.3: AI Context Binding, Guardrails, Explanation & Feedback Engine
"""

from backend.ai.context import resolve_ai_context, AIContext
from backend.ai.guards import enforce_scope, ScopeGuard
from backend.ai.prompts import (
    SYSTEM_GUARD_PROMPT,
    build_scoped_prompt,
    build_explanation_prompt,
    build_question_answer_prompt,
    ExplanationType,
    EXPLANATION_STYLE_MAP
)
from backend.ai.service import (
    explain_content,
    ask_about_content,
    get_available_explanation_types,
    clear_explanation_cache
)
from backend.ai.feedback import (
    generate_attempt_feedback,
    get_mcq_option_analysis,
    clear_feedback_cache,
    build_feedback_prompt
)

__all__ = [
    "resolve_ai_context",
    "AIContext",
    "enforce_scope",
    "ScopeGuard",
    "SYSTEM_GUARD_PROMPT",
    "build_scoped_prompt",
    "build_explanation_prompt",
    "build_question_answer_prompt",
    "ExplanationType",
    "EXPLANATION_STYLE_MAP",
    "explain_content",
    "ask_about_content",
    "get_available_explanation_types",
    "clear_explanation_cache",
    "generate_attempt_feedback",
    "get_mcq_option_analysis",
    "clear_feedback_cache",
    "build_feedback_prompt"
]
