"""
Feature Flags Configuration

Centralized feature flag management for the backend.
All feature flags should be loaded from environment variables.
"""
import os
from typing import Optional


def get_bool_env(key: str, default: bool = False) -> bool:
    """Get a boolean value from environment variable."""
    value = os.getenv(key, str(default)).lower()
    return value in ('true', '1', 'yes', 'on', 'enabled')


class FeatureFlags:
    """
    Feature flags for the application.
    
    To add a new feature flag:
    1. Add it here as a class property
    2. Load it from environment variable
    3. Use it in your code
    """
    
    # Classroom State Machine Feature Flag
    FEATURE_CLASSROOM_SM: bool = get_bool_env('FEATURE_CLASSROOM_SM', False)
    
    # Phase 3: Round Engine
    FEATURE_CLASSROOM_ROUND_ENGINE: bool = get_bool_env('FEATURE_CLASSROOM_ROUND_ENGINE', False)
    FEATURE_AUTO_SUBMIT_ON_TIMEOUT: bool = get_bool_env('FEATURE_AUTO_SUBMIT_ON_TIMEOUT', False)
    FEATURE_ALLOW_LATE_SUBMISSION: bool = get_bool_env('FEATURE_ALLOW_LATE_SUBMISSION', False)
    
    # Phase 4: AI Judge Engine (Evaluation)
    FEATURE_AI_JUDGE_EVALUATION: bool = get_bool_env('FEATURE_AI_JUDGE_EVALUATION', False)
    FEATURE_AI_EVAL_AUTO_RETRY: bool = get_bool_env('FEATURE_AI_EVAL_AUTO_RETRY', True)
    FEATURE_AI_EVAL_REQUIRES_REVIEW: bool = get_bool_env('FEATURE_AI_EVAL_REQUIRES_REVIEW', True)
    
    # Phase 5: Leaderboard Engine (Immutable Leaderboards)
    FEATURE_LEADERBOARD_ENGINE: bool = get_bool_env('FEATURE_LEADERBOARD_ENGINE', False)
    FEATURE_LEADERBOARD_AUTO_FREEZE: bool = get_bool_env('FEATURE_LEADERBOARD_AUTO_FREEZE', False)
    
    # Phase 15: AI Judge Intelligence Layer
    FEATURE_AI_JUDGE_SHADOW: bool = get_bool_env('FEATURE_AI_JUDGE_SHADOW', False)
    FEATURE_AI_JUDGE_OFFICIAL: bool = get_bool_env('FEATURE_AI_JUDGE_OFFICIAL', False)
    FEATURE_AI_JUDGE_CACHE: bool = get_bool_env('FEATURE_AI_JUDGE_CACHE', True)
    FEATURE_AI_JUDGE_HEURISTICS: bool = get_bool_env('FEATURE_AI_JUDGE_HEURISTICS', True)
    
    # Phase 16: Performance Analytics & Ranking Intelligence Layer
    FEATURE_ANALYTICS_ENGINE: bool = get_bool_env('FEATURE_ANALYTICS_ENGINE', False)
    FEATURE_RANKING_ENGINE: bool = get_bool_env('FEATURE_RANKING_ENGINE', False)
    FEATURE_JUDGE_ANALYTICS: bool = get_bool_env('FEATURE_JUDGE_ANALYTICS', False)
    FEATURE_TREND_ENGINE: bool = get_bool_env('FEATURE_TREND_ENGINE', False)
    
    # Phase 17: Appeals & Governance Override Engine
    FEATURE_APPEALS_ENGINE: bool = get_bool_env('FEATURE_APPEALS_ENGINE', False)
    FEATURE_MULTI_JUDGE_APPEALS: bool = get_bool_env('FEATURE_MULTI_JUDGE_APPEALS', False)
    FEATURE_APPEAL_OVERRIDE_RANKING: bool = get_bool_env('FEATURE_APPEAL_OVERRIDE_RANKING', True)
    FEATURE_APPEAL_AUTO_CLOSE: bool = get_bool_env('FEATURE_APPEAL_AUTO_CLOSE', True)
    
    # Phase 18: Scheduling & Court Allocation Engine
    FEATURE_SCHEDULING_ENGINE: bool = get_bool_env('FEATURE_SCHEDULING_ENGINE', False)
    FEATURE_JUDGE_AVAILABILITY: bool = get_bool_env('FEATURE_JUDGE_AVAILABILITY', False)
    
    # Phase 19: Moot Courtroom Operations & Live Session Management
    FEATURE_MOOT_OPERATIONS: bool = get_bool_env('FEATURE_MOOT_OPERATIONS', False)
    FEATURE_SESSION_RECORDING: bool = get_bool_env('FEATURE_SESSION_RECORDING', False)
    
    # Phase 20: Tournament Lifecycle Orchestrator
    FEATURE_TOURNAMENT_LIFECYCLE: bool = False
    
    # Phase 21: Admin Command Center (Operational Control Layer)
    FEATURE_ADMIN_COMMAND_CENTER: bool = get_bool_env('FEATURE_ADMIN_COMMAND_CENTER', False)
    
    # Analytics Dashboard (if needed in future)
    FEATURE_ANALYTICS_V2: bool = get_bool_env('FEATURE_ANALYTICS_V2', False)
    
    @classmethod
    def is_enabled(cls, flag_name: str) -> bool:
        """Check if a feature flag is enabled by name."""
        return getattr(cls, flag_name, False)
    
    @classmethod
    def get_all_flags(cls) -> dict:
        """Get all feature flags as a dictionary."""
        return {
            key: value
            for key, value in cls.__dict__.items()
            if not key.startswith('_') and isinstance(value, bool)
        }


# Singleton instance for easy importing
feature_flags = FeatureFlags()
