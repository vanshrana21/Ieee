"""
backend/ai/__init__.py
Phase 10.1-10.5: AI Context Binding, Guardrails, Explanation, Feedback, Adaptive Hinting & Memory
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
from backend.ai.adaptive import (
    compute_adaptation_signals,
    select_adaptation_style,
    get_adaptive_feedback,
    get_hint_for_struggling_student,
    get_adaptation_summary,
    build_adaptive_prompt_modifier,
    DifficultyLevel,
    AdaptationStyle,
    AdaptationSignals
)
from backend.ai.memory import (
    compute_tutor_memory,
    build_memory_context_for_ai,
    get_memory_phrase,
    get_memory_summary,
    TutorMemory,
    TopicStruggle,
    ConfusionPattern,
    MEMORY_PHRASES
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
    "build_feedback_prompt",
    "compute_adaptation_signals",
    "select_adaptation_style",
    "get_adaptive_feedback",
    "get_hint_for_struggling_student",
    "get_adaptation_summary",
    "build_adaptive_prompt_modifier",
    "DifficultyLevel",
    "AdaptationStyle",
    "AdaptationSignals",
    "compute_tutor_memory",
    "build_memory_context_for_ai",
    "get_memory_phrase",
    "get_memory_summary",
    "TutorMemory",
    "TopicStruggle",
    "ConfusionPattern",
    "MEMORY_PHRASES"
]
