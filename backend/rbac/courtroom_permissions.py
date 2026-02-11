"""
Phase 0: Virtual Courtroom Infrastructure - Role-Based Access Control (RBAC)

Permission definitions for courtroom actions with enforcement helpers.
"""
from enum import Enum
from typing import Dict, List, Optional, Set
from functools import wraps
from fastapi import HTTPException, status
import logging

logger = logging.getLogger(__name__)


class UserRole(str, Enum):
    """User roles in the courtroom system."""
    JUDGE = "judge"
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"
    ADMIN = "admin"
    OBSERVER = "observer"


class CourtroomAction(str, Enum):
    """All possible courtroom actions."""
    # Timer controls
    START_TIMER = "start_timer"
    PAUSE_TIMER = "pause_timer"
    RESUME_TIMER = "resume_timer"
    RESET_TIMER = "reset_timer"
    
    # Objections
    RAISE_OBJECTION = "raise_objection"
    RULE_ON_OBJECTION = "rule_on_objection"
    
    # Scoring
    SUBMIT_SCORE = "submit_score"
    VIEW_DRAFT_SCORES = "view_draft_scores"
    VIEW_SUBMITTED_SCORES = "view_submitted_scores"
    
    # Recording
    START_RECORDING = "start_recording"
    STOP_RECORDING = "stop_recording"
    
    # Transcripts
    FINALIZE_TRANSCRIPT = "finalize_transcript"
    VIEW_LIVE_TRANSCRIPT = "view_live_transcript"
    
    # AI Opponent
    ENABLE_AI_OPPONENT = "enable_ai_opponent"
    
    # Round management
    CHANGE_SPEAKER = "change_speaker"
    COMPLETE_ROUND = "complete_round"


# Permission matrix: action -> allowed roles
PERMISSION_MATRIX: Dict[CourtroomAction, Set[UserRole]] = {
    # Timer controls - Judges and Admins only
    CourtroomAction.START_TIMER: {UserRole.JUDGE, UserRole.ADMIN},
    CourtroomAction.PAUSE_TIMER: {UserRole.JUDGE, UserRole.ADMIN},
    CourtroomAction.RESUME_TIMER: {UserRole.JUDGE, UserRole.ADMIN},
    CourtroomAction.RESET_TIMER: {UserRole.JUDGE, UserRole.ADMIN},
    
    # Objections - Teams raise, Judges rule
    CourtroomAction.RAISE_OBJECTION: {UserRole.PETITIONER, UserRole.RESPONDENT},
    CourtroomAction.RULE_ON_OBJECTION: {UserRole.JUDGE, UserRole.ADMIN},
    
    # Scoring - Judges and Admins only
    CourtroomAction.SUBMIT_SCORE: {UserRole.JUDGE, UserRole.ADMIN},
    CourtroomAction.VIEW_DRAFT_SCORES: {UserRole.JUDGE, UserRole.ADMIN},
    CourtroomAction.VIEW_SUBMITTED_SCORES: {
        UserRole.JUDGE, UserRole.ADMIN, 
        UserRole.PETITIONER, UserRole.RESPONDENT
    },
    
    # Recording - All participants
    CourtroomAction.START_RECORDING: {
        UserRole.JUDGE, UserRole.PETITIONER, 
        UserRole.RESPONDENT, UserRole.ADMIN
    },
    CourtroomAction.STOP_RECORDING: {
        UserRole.JUDGE, UserRole.PETITIONER, 
        UserRole.RESPONDENT, UserRole.ADMIN
    },
    
    # Transcripts - Judges control, all view live
    CourtroomAction.FINALIZE_TRANSCRIPT: {UserRole.JUDGE, UserRole.ADMIN},
    CourtroomAction.VIEW_LIVE_TRANSCRIPT: {
        UserRole.JUDGE, UserRole.ADMIN,
        UserRole.PETITIONER, UserRole.RESPONDENT,
        UserRole.OBSERVER
    },
    
    # AI Opponent - Team captains only (simplified: team members)
    CourtroomAction.ENABLE_AI_OPPONENT: {UserRole.PETITIONER, UserRole.RESPONDENT},
    
    # Round management - Judges and Admins only
    CourtroomAction.CHANGE_SPEAKER: {UserRole.JUDGE, UserRole.ADMIN},
    CourtroomAction.COMPLETE_ROUND: {UserRole.JUDGE, UserRole.ADMIN},
}


def has_permission(user_role: UserRole, action: CourtroomAction) -> bool:
    """
    Check if a user role has permission to perform an action.
    
    Args:
        user_role: The user's role
        action: The action to check
    
    Returns:
        True if permitted, False otherwise
    """
    allowed_roles = PERMISSION_MATRIX.get(action, set())
    return user_role in allowed_roles


def can_perform_action(
    user_id: int,
    user_role: UserRole,
    action: CourtroomAction,
    round_id: int,
    round_data: Optional[dict] = None
) -> bool:
    """
    Check if user can perform action on a specific round.
    
    Extends basic permission check with round-specific validations:
    - Judges must be assigned to the round
    - Team members must be on the correct team
    
    Args:
        user_id: User ID
        user_role: User role
        action: Action to check
        round_id: Round ID
        round_data: Optional round data with team/judge assignments
    
    Returns:
        True if action is permitted
    """
    # Check basic permission
    if not has_permission(user_role, action):
        return False
    
    # Round-specific checks
    if round_data:
        # Judges must be assigned to round
        if user_role == UserRole.JUDGE:
            presiding = round_data.get("presiding_judge_id")
            co_judges = round_data.get("co_judges_ids", [])
            if user_id != presiding and user_id not in co_judges:
                return False
        
        # Teams must match their side
        if user_role == UserRole.PETITIONER:
            if user_id != round_data.get("petitioner_team_id"):
                return False
        
        if user_role == UserRole.RESPONDENT:
            if user_id != round_data.get("respondent_team_id"):
                return False
    
    return True


def require_permission(action: CourtroomAction):
    """
    Decorator for FastAPI endpoints to enforce permissions.
    
    Usage:
        @router.post("/timer/start")
        @require_permission(CourtroomAction.START_TIMER)
        async def start_timer(...):
            ...
    
    Args:
        action: Required permission action
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract current_user from kwargs (set by auth dependency)
            current_user = kwargs.get("current_user")
            
            if not current_user:
                logger.warning(f"Permission check failed: no current_user for {action}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )
            
            user_role = current_user.get("role")
            user_id = current_user.get("id")
            
            if not user_role:
                logger.warning(f"Permission check failed: no role for user {user_id}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Role information required"
                )
            
            # Convert string role to enum if needed
            if isinstance(user_role, str):
                try:
                    user_role = UserRole(user_role.lower())
                except ValueError:
                    logger.warning(f"Invalid role: {user_role}")
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Invalid role: {user_role}"
                    )
            
            # Check permission
            if not has_permission(user_role, action):
                logger.warning(
                    f"Permission denied: user {user_id} ({user_role.value}) "
                    f"attempted {action.value}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {action.value} requires {', '.join(
                        r.value for r in PERMISSION_MATRIX.get(action, [])
                    )}"
                )
            
            # Log successful permission check
            logger.info(f"Permission granted: {user_id} ({user_role.value}) for {action.value}")
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def get_allowed_actions(user_role: UserRole) -> List[CourtroomAction]:
    """
    Get list of all actions a role is permitted to perform.
    
    Args:
        user_role: User role to check
    
    Returns:
        List of permitted actions
    """
    return [
        action for action, roles in PERMISSION_MATRIX.items()
        if user_role in roles
    ]


def check_permission_json(user_role: str, action: str) -> dict:
    """
    JSON-friendly permission check for API responses.
    
    Args:
        user_role: Role string (e.g., "judge", "petitioner")
        action: Action string (e.g., "start_timer")
    
    Returns:
        Dict with allowed (bool), action, and role
    """
    try:
        role_enum = UserRole(user_role.lower())
        action_enum = CourtroomAction(action.lower())
        allowed = has_permission(role_enum, action_enum)
    except (ValueError, KeyError):
        allowed = False
    
    return {
        "allowed": allowed,
        "action": action,
        "role": user_role,
        "requires": [
            r.value for r in PERMISSION_MATRIX.get(
            CourtroomAction(action.lower()) if action else None, set()
        )]
    }


# Permission descriptions for documentation
PERMISSION_DESCRIPTIONS: Dict[CourtroomAction, str] = {
    CourtroomAction.START_TIMER: "Start the round timer",
    CourtroomAction.PAUSE_TIMER: "Pause the round timer",
    CourtroomAction.RESUME_TIMER: "Resume the round timer",
    CourtroomAction.RESET_TIMER: "Reset the round timer",
    CourtroomAction.RAISE_OBJECTION: "Raise a legal objection",
    CourtroomAction.RULE_ON_OBJECTION: "Rule on an objection (sustain/overrule)",
    CourtroomAction.SUBMIT_SCORE: "Submit or update scores",
    CourtroomAction.VIEW_DRAFT_SCORES: "View draft scores",
    CourtroomAction.VIEW_SUBMITTED_SCORES: "View finalized scores",
    CourtroomAction.START_RECORDING: "Start audio recording",
    CourtroomAction.STOP_RECORDING: "Stop audio recording",
    CourtroomAction.FINALIZE_TRANSCRIPT: "Finalize and publish transcript",
    CourtroomAction.VIEW_LIVE_TRANSCRIPT: "View live transcript updates",
    CourtroomAction.ENABLE_AI_OPPONENT: "Enable AI opponent for practice",
    CourtroomAction.CHANGE_SPEAKER: "Change current speaker",
    CourtroomAction.COMPLETE_ROUND: "Mark round as complete",
}


def get_permission_matrix_json() -> List[dict]:
    """
    Get complete permission matrix as JSON-serializable list.
    
    Returns:
        List of dicts with action, description, and allowed_roles
    """
    return [
        {
            "action": action.value,
            "description": PERMISSION_DESCRIPTIONS.get(action, ""),
            "allowed_roles": [r.value for r in roles]
        }
        for action, roles in PERMISSION_MATRIX.items()
    ]
