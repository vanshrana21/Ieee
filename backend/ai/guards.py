"""
backend/ai/guards.py
Phase 10.1: Scope Guard & Hard Refusal Layer

PURPOSE:
Prevent AI from answering questions outside the student's current scope.

SCOPE RULES:
1. Questions must relate to enrolled subjects only
2. Cannot ask about "any law" or "other subject"
3. Cannot request topics outside syllabus
4. Cannot trick AI into teaching unauthorized content
"""

import logging
import re
from typing import Optional, List
from backend.exceptions import ScopeViolationError

logger = logging.getLogger(__name__)


class ScopeGuard:
    """
    Hard refusal layer for out-of-scope queries.
    
    Detects and blocks:
    - Requests for random/other subjects
    - Attempts to break scope boundaries
    - Questions clearly outside current topic
    """
    
    FORBIDDEN_PATTERNS = [
        r"\b(teach|explain|tell)\s+(me\s+)?about\s+(any|another|different|other)\s+(law|subject|topic)\b",
        r"\blet'?s\s+(talk|learn|discuss)\s+(about\s+)?(something|anything)\s+else\b",
        r"\boutside\s+(the\s+)?syllabus\b",
        r"\bnot\s+(in|part\s+of)\s+(my\s+)?(curriculum|course|syllabus)\b",
        r"\brandom\s+(case|law|topic|subject|question)\b",
        r"\b(any|some)\s+(other|different|random)\s+(case|law|topic)\b",
        r"\bignore\s+(the\s+)?(subject|topic|context|scope)\b",
        r"\bforget\s+(about\s+)?(the\s+)?(context|subject|scope)\b",
        r"\bchange\s+(the\s+)?subject\b",
        r"\bskip\s+(to\s+)?(a\s+)?(different|another|new)\s+(topic|subject)\b",
    ]
    
    SCOPE_ESCAPE_PATTERNS = [
        r"\bpretend\s+(you'?re|to\s+be)\b",
        r"\bact\s+as\s+(if|a)\b",
        r"\brole\s*play\b",
        r"\bignore\s+(your\s+)?(rules|instructions|constraints)\b",
        r"\bsystem\s+prompt\b",
        r"\bjailbreak\b",
    ]
    
    POLITE_REFUSAL = (
        "I can only help you with your current subject: {subject}. "
        "This question is outside your study scope. "
        "Please ask something related to what you're currently learning."
    )
    
    @classmethod
    def check_forbidden_patterns(cls, question: str) -> Optional[str]:
        """
        Check if question contains forbidden patterns.
        
        Returns:
            Matched pattern if found, None otherwise
        """
        question_lower = question.lower()
        
        for pattern in cls.FORBIDDEN_PATTERNS:
            match = re.search(pattern, question_lower)
            if match:
                logger.warning(f"[Scope Guard] Forbidden pattern detected: {match.group()}")
                return match.group()
        
        return None
    
    @classmethod
    def check_escape_attempts(cls, question: str) -> Optional[str]:
        """
        Check for attempts to escape scope restrictions.
        
        Returns:
            Matched pattern if found, None otherwise
        """
        question_lower = question.lower()
        
        for pattern in cls.SCOPE_ESCAPE_PATTERNS:
            match = re.search(pattern, question_lower)
            if match:
                logger.warning(f"[Scope Guard] Escape attempt detected: {match.group()}")
                return match.group()
        
        return None
    
    @classmethod
    def validate(cls, question: str, subject_title: str = "your current subject") -> None:
        """
        Validate question against scope rules.
        
        Args:
            question: User's question
            subject_title: Current subject for refusal message
        
        Raises:
            ScopeViolationError: If question violates scope rules
        """
        forbidden = cls.check_forbidden_patterns(question)
        if forbidden:
            raise ScopeViolationError(
                cls.POLITE_REFUSAL.format(subject=subject_title)
            )
        
        escape = cls.check_escape_attempts(question)
        if escape:
            raise ScopeViolationError(
                "I can only help with your curriculum. Please stay within your study scope."
            )


def enforce_scope(question: str, subject_title: str = None) -> None:
    """
    Convenience function to enforce scope on a question.
    
    Args:
        question: User's question
        subject_title: Optional subject name for error message
    
    Raises:
        ScopeViolationError: If question is out of scope
    """
    ScopeGuard.validate(question, subject_title or "your current subject")


class TopicValidator:
    """
    Validates if a topic/question relates to allowed subjects.
    """
    
    @staticmethod
    def extract_potential_subjects(question: str) -> List[str]:
        """
        Extract potential subject references from question.
        """
        subject_patterns = [
            r"\b(contract|contracts)\s*(law)?\b",
            r"\b(criminal|crime)\s*(law)?\b",
            r"\b(constitutional)\s*(law)?\b",
            r"\b(tort|torts)\s*(law)?\b",
            r"\b(property)\s*(law)?\b",
            r"\b(family)\s*(law)?\b",
            r"\b(company|corporate)\s*(law)?\b",
            r"\b(labour|labor)\s*(law)?\b",
            r"\b(environmental)\s*(law)?\b",
            r"\b(cyber)\s*(law)?\b",
            r"\b(ip|intellectual\s+property)\s*(law)?\b",
            r"\b(ipc|indian\s+penal\s+code)\b",
            r"\b(crpc|code\s+of\s+criminal\s+procedure)\b",
            r"\b(cpc|code\s+of\s+civil\s+procedure)\b",
            r"\b(evidence)\s*(act|law)?\b",
        ]
        
        found = []
        question_lower = question.lower()
        
        for pattern in subject_patterns:
            if re.search(pattern, question_lower):
                match = re.search(pattern, question_lower)
                found.append(match.group())
        
        return found
    
    @staticmethod
    def is_generic_legal_question(question: str) -> bool:
        """
        Check if question is a generic legal question without specific subject.
        
        Generic questions are allowed as they can be answered within current context.
        """
        generic_patterns = [
            r"\b(what|how|why|when|where|who|which|explain|define|describe)\b",
            r"\b(difference|between|compare|contrast)\b",
            r"\b(meaning|definition|concept|principle)\b",
            r"\b(example|case|scenario)\b",
        ]
        
        question_lower = question.lower()
        
        for pattern in generic_patterns:
            if re.search(pattern, question_lower):
                return True
        
        return False
