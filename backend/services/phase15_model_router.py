"""
Phase 15 — Model Router Service

Routes AI evaluation requests to appropriate models based on mode and context.
No creativity drift allowed - deterministic routing.
"""
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class EvaluationMode(Enum):
    """Evaluation modes."""
    SHADOW = "shadow"
    OFFICIAL = "official"


class RoundType(Enum):
    """Round types for model selection."""
    PRELIM = "prelim"
    QUARTER = "quarter"
    SEMI = "semi"
    FINAL = "final"


@dataclass
class ModelConfig:
    """Configuration for AI model."""
    model_name: str
    max_tokens: int
    temperature: float
    top_p: float
    frequency_penalty: float
    presence_penalty: float
    cost_per_1k_tokens: float
    quality_tier: str  # low, balanced, premium


class ModelRouterService:
    """
    Routes evaluation requests to appropriate AI models.
    Ensures cost-efficient model selection while maintaining quality.
    """

    # Model configurations
    MODELS = {
        # Low-cost models for shadow scoring
        "gpt-3.5-turbo": ModelConfig(
            model_name="gpt-3.5-turbo",
            max_tokens=500,
            temperature=0.2,  # Low creativity for consistency
            top_p=0.1,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            cost_per_1k_tokens=0.002,
            quality_tier="low"
        ),

        # Balanced models for official evaluations
        "gpt-4": ModelConfig(
            model_name="gpt-4",
            max_tokens=500,
            temperature=0.2,
            top_p=0.1,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            cost_per_1k_tokens=0.03,
            quality_tier="balanced"
        ),

        # Premium models for finals
        "gpt-4-turbo": ModelConfig(
            model_name="gpt-4-turbo-preview",
            max_tokens=500,
            temperature=0.2,
            top_p=0.1,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            cost_per_1k_tokens=0.01,
            quality_tier="premium"
        ),

        # Heuristic-only (no LLM)
        "heuristic": ModelConfig(
            model_name="heuristic",
            max_tokens=0,
            temperature=0.0,
            top_p=0.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            cost_per_1k_tokens=0.0,
            quality_tier="heuristic"
        ),
    }

    # Routing rules
    DEFAULT_SHADOW_MODEL = "gpt-3.5-turbo"
    DEFAULT_OFFICIAL_MODEL = "gpt-4"
    FINALS_MODEL = "gpt-4-turbo"

    @staticmethod
    def get_model_config(
        mode: str,
        is_finals: bool = False,
        use_heuristics: bool = True,
        budget_constraint: Optional[float] = None
    ) -> ModelConfig:
        """
        Get model configuration based on evaluation parameters.

        Args:
            mode: "shadow" or "official"
            is_finals: Whether this is a finals match
            use_heuristics: Whether to use heuristics for shadow mode
            budget_constraint: Optional budget limit

        Returns:
            ModelConfig with appropriate model settings
        """
        # Finals always get premium model
        if is_finals and mode == EvaluationMode.OFFICIAL.value:
            return ModelRouterService.MODELS[ModelRouterService.FINALS_MODEL]

        # Shadow mode routing
        if mode == EvaluationMode.SHADOW.value:
            if use_heuristics and not is_finals:
                # Use heuristics for non-final shadow scoring
                return ModelRouterService.MODELS["heuristic"]
            return ModelRouterService.MODELS[ModelRouterService.DEFAULT_SHADOW_MODEL]

        # Official mode routing
        if mode == EvaluationMode.OFFICIAL.value:
            if budget_constraint and budget_constraint < 0.01:
                # Low budget - use cheaper model
                return ModelRouterService.MODELS["gpt-3.5-turbo"]
            return ModelRouterService.MODELS[ModelRouterService.DEFAULT_OFFICIAL_MODEL]

        # Default fallback
        return ModelRouterService.MODELS[ModelRouterService.DEFAULT_OFFICIAL_MODEL]

    @staticmethod
    def route_evaluation(
        mode: str,
        round_type: Optional[str] = None,
        is_finals: bool = False,
        use_heuristics: bool = True,
        budget_constraint: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Route evaluation and return complete configuration.

        Returns:
            Dictionary with model configuration and routing info
        """
        config = ModelRouterService.get_model_config(
            mode=mode,
            is_finals=is_finals,
            use_heuristics=use_heuristics,
            budget_constraint=budget_constraint
        )

        return {
            "model_name": config.model_name,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "top_p": config.top_p,
            "frequency_penalty": config.frequency_penalty,
            "presence_penalty": config.presence_penalty,
            "cost_estimate": config.cost_per_1k_tokens * (config.max_tokens / 1000),
            "quality_tier": config.quality_tier,
            "mode": mode,
            "is_finals": is_finals,
            "use_heuristics": use_heuristics and config.model_name == "heuristic",
        }

    @staticmethod
    def estimate_cost(model_name: str, token_count: int) -> float:
        """
        Estimate cost for evaluation.

        Args:
            model_name: Name of the model
            token_count: Estimated token count

        Returns:
            Estimated cost in USD
        """
        if model_name not in ModelRouterService.MODELS:
            return 0.0

        config = ModelRouterService.MODELS[model_name]
        return config.cost_per_1k_tokens * (token_count / 1000)

    @staticmethod
    def get_prompt_template(mode: str) -> str:
        """
        Get scoring prompt template based on mode.

        Returns structured prompt that ensures consistent JSON output.
        """
        base_prompt = """You are an expert moot court judge evaluating a legal debate.

Evaluate the following match based on these criteria:
- legal_knowledge (0-20): Understanding of legal principles
- application_of_law (0-20): Application to facts
- structure_clarity (0-20): Organization and clarity
- etiquette (0-10): Professional conduct
- rebuttal_strength (0-20): Quality of rebuttals
- objection_handling (0-10): Handling of objections

You MUST return ONLY a JSON object in this exact format:
{
  "petitioner": {
    "legal_knowledge": int,
    "application_of_law": int,
    "structure_clarity": int,
    "etiquette": int,
    "rebuttal_strength": int,
    "objection_handling": int,
    "total": int
  },
  "respondent": {
    "legal_knowledge": int,
    "application_of_law": int,
    "structure_clarity": int,
    "etiquette": int,
    "rebuttal_strength": int,
    "objection_handling": int,
    "total": int
  },
  "winner": "PETITIONER" or "RESPONDENT",
  "reasoning_summary": "Brief 1-2 sentence explanation",
  "confidence": float between 0 and 1
}

Rules:
1. Each total MUST be sum of components (max 100)
2. Winner MUST have higher total score
3. Confidence reflects certainty in judgment
4. Be objective and consistent

Match Summary:
{match_summary}
"""

        if mode == EvaluationMode.SHADOW.value:
            # Shadow mode - lighter prompt for speed
            return base_prompt + "\n\nProvide quick provisional assessment."

        return base_prompt + "\n\nProvide thorough official evaluation."

    @staticmethod
    def validate_mode(mode: str) -> bool:
        """Validate evaluation mode."""
        return mode in [m.value for m in EvaluationMode]

    @staticmethod
    def get_available_models() -> Dict[str, Dict[str, Any]]:
        """Get list of available models with their configs."""
        return {
            name: {
                "max_tokens": config.max_tokens,
                "temperature": config.temperature,
                "quality_tier": config.quality_tier,
                "cost_per_1k": config.cost_per_1k_tokens,
            }
            for name, config in ModelRouterService.MODELS.items()
        }


# Singleton instance
model_router = ModelRouterService()
