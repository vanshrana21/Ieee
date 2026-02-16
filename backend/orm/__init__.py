from .base import Base

# Core models
from .user import User
from .institution import Institution
from .institution_admin import InstitutionAdmin
from .sso_configuration import SSOConfiguration
from .bulk_upload_session import BulkUploadSession
from .course import Course
from .bookmark import Bookmark
from .saved_search import SavedSearch
from .user_content_progress import UserContentProgress
from .practice_attempt import PracticeAttempt
from .subject_progress import SubjectProgress
from .user_notes import UserNotes
from .exam_session import ExamSession
from .curriculum import CourseCurriculum
from .subject import Subject
from .practice_question import PracticeQuestion
from .exam_answer import ExamAnswer
from .content_module import ContentModule
from .learn_content import LearnContent
from .smart_note import SmartNote
from .case_content import CaseContent

# Competition + Moot
from .competition import Competition
from .team import Team, TeamMember
from .memorial import MemorialSubmission
from .oral_round import OralRound
from .oral_round_transcript import OralRoundTranscript
from .oral_round_objection import OralRoundObjection
from .oral_round_score import OralRoundScore
from .classroom_session import ClassroomSession, ClassroomParticipant, ClassroomScore, ClassroomArgument
from .classroom_round import ClassroomRound
from .classroom_turn import ClassroomTurn, ClassroomTurnAudit
from .classroom_round_action import ClassroomRoundAction
from .session_state_transition import SessionStateTransition
from .classroom_session_state_log import ClassroomSessionStateLog
from .classroom_participant_audit_log import ClassroomParticipantAuditLog
from .moot_case import MootCase
from .moot_project import MootProject
from .moot_evaluation import MootEvaluation
from .ai_opponent_session import AIOpponentSession

# Phase 4: AI Judge Engine
from .ai_rubrics import AIRubric, AIRubricVersion
from .ai_evaluations import (
    AIEvaluation, AIEvaluationAttempt, FacultyOverride, 
    AIEvaluationAudit, EvaluationStatus, ParseStatus
)

# Phase 5: Immutable Leaderboard Engine
from .session_leaderboard import (
    SessionLeaderboardSnapshot, 
    SessionLeaderboardEntry, 
    SessionLeaderboardAudit,
    LeaderboardSide
)


__all__ = [
    "Base",
    "User",
    "Institution",
    "InstitutionAdmin",
    "SSOConfiguration",
    "BulkUploadSession",
    "Course",
    "Bookmark",
    "SavedSearch",
    "UserContentProgress",
    "PracticeAttempt",
    "SubjectProgress",
    "UserNotes",
    "ExamSession",
    "CourseCurriculum",
    "Subject",
    "PracticeQuestion",
    "ExamAnswer",
    "ContentModule",
    "LearnContent",
    "SmartNote",
    "CaseContent",
    "Competition",
    "Team",
    "TeamMember",
    "MemorialSubmission",
    "OralRound",
    "OralRoundTranscript",
    "OralRoundObjection",
    "OralRoundScore",
    "ClassroomSession",
    "ClassroomParticipant",
    "ClassroomParticipantAuditLog",
    "ClassroomScore",
    "ClassroomArgument",
    "ClassroomRound",
    "ClassroomTurn",
    "ClassroomTurnAudit",
    "ClassroomRoundAction",
    "SessionStateTransition",
    "ClassroomSessionStateLog",
    "MootCase",
    "MootProject",
    "MootEvaluation",
    "AIOpponentSession",
    # Phase 4: AI Judge Engine
    "AIRubric",
    "AIRubricVersion",
    "AIEvaluation",
    "AIEvaluationAttempt",
    "FacultyOverride",
    "AIEvaluationAudit",
    "EvaluationStatus",
    "ParseStatus",
    # Phase 5: Immutable Leaderboard Engine
    "SessionLeaderboardSnapshot",
    "SessionLeaderboardEntry",
    "SessionLeaderboardAudit",
    "LeaderboardSide",
]
