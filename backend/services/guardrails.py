"""
backend/services/guardrails.py
Academic & Safety Guardrails for AI-Generated Content

PHASE 8: Intelligent Learning Engine - Component 4

PURPOSE:
Validate all AI-generated responses to ensure:
- Constitutional accuracy
- No legal advice
- No political bias
- No speculation
- Educational tone
- IEEE compliance

This service acts as a gate before any AI content reaches the user.
"""
import logging
import re
from typing import Tuple, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.orm.case_content import CaseContent

logger = logging.getLogger(__name__)


class GuardrailViolation(Exception):
    """Raised when content violates academic/safety guidelines"""
    pass


class ContentGuardrails:
    """
    Validates AI-generated legal educational content.
    
    All checks are deterministic and rule-based (no ML).
    """
    
    # ========== PROHIBITED PATTERNS ==========
    
    LEGAL_ADVICE_PHRASES = [
        "you should hire a lawyer",
        "you should file a case",
        "you should sue",
        "take legal action",
        "you have grounds to",
        "consult me for",
        "i recommend you",
        "your best option is to",
        "file an fir",
        "approach the court",
    ]
    
    POLITICAL_KEYWORDS = [
        "bjp is",
        "congress is",
        "government is wrong",
        "ruling party",
        "opposition party",
        "political agenda",
        "modi government",
        "rahul gandhi",
    ]
    
    SPECULATIVE_LANGUAGE = [
        "i think",
        "i believe",
        "in my opinion",
        "probably",
        "maybe",
        "might be",
        "could be that",
        "i guess",
        "it seems",
    ]
    
    OUTDATED_CONSTITUTIONAL_REFS = [
        ("article 370", ["revoked", "abrogated", "no longer"]),  # Must mention status
        ("section 377", ["decriminalized", "read down"]),         # Must mention SC ruling
    ]
    
    # ========== VALIDATION METHODS ==========
    
    @staticmethod
    def validate_no_legal_advice(text: str) -> Tuple[bool, Optional[str]]:
        """
        Check for legal advice language.
        
        Educational content explains law; legal advice applies law to specific situations.
        
        Returns:
            (is_valid, error_message)
        """
        text_lower = text.lower()
        
        for phrase in ContentGuardrails.LEGAL_ADVICE_PHRASES:
            if phrase in text_lower:
                logger.warning(f"Legal advice detected: '{phrase}'")
                return False, f"Response contains legal advice language: '{phrase}'"
        
        # Check for direct recommendations
        if re.search(r'\byou\s+(should|must|need to)\s+\w+', text_lower):
            if any(action in text_lower for action in ["file", "sue", "hire", "approach court"]):
                return False, "Response gives specific legal recommendations"
        
        return True, None
    
    @staticmethod
    def validate_no_political_bias(text: str) -> Tuple[bool, Optional[str]]:
        """
        Check for political statements or bias.
        
        Legal education must remain politically neutral.
        """
        text_lower = text.lower()
        
        for keyword in ContentGuardrails.POLITICAL_KEYWORDS:
            if keyword in text_lower:
                logger.warning(f"Political content detected: '{keyword}'")
                return False, f"Response contains political commentary: '{keyword}'"
        
        return True, None
    
    @staticmethod
    def validate_no_speculation(text: str) -> Tuple[bool, Optional[str]]:
        """
        Check for speculative language.
        
        Educational content should be factual and definitive.
        """
        text_lower = text.lower()
        
        for phrase in ContentGuardrails.SPECULATIVE_LANGUAGE:
            if phrase in text_lower:
                logger.warning(f"Speculative language detected: '{phrase}'")
                return False, f"Response contains speculation: '{phrase}'"
        
        return True, None
    
    @staticmethod
    def validate_constitutional_accuracy(text: str) -> Tuple[bool, Optional[str]]:
        """
        Check for outdated constitutional references.
        
        Examples:
        - Article 370 (revoked in 2019)
        - Section 377 (decriminalized in 2018)
        """
        text_lower = text.lower()
        
        for outdated_ref, required_mentions in ContentGuardrails.OUTDATED_CONSTITUTIONAL_REFS:
            if outdated_ref in text_lower:
                # Check if status is mentioned
                has_status = any(mention in text_lower for mention in required_mentions)
                if not has_status:
                    logger.warning(f"Outdated reference without status: '{outdated_ref}'")
                    return False, f"Reference to '{outdated_ref}' must mention current status"
        
        return True, None
    
    @staticmethod
    async def validate_case_citations(
        text: str,
        db: AsyncSession
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify that cited cases exist in database.
        
        Prevents hallucinated judgments.
        
        Pattern: "Case Name v. Party Name (Year)"
        """
        # Extract potential case citations
        case_pattern = r'([A-Z][a-zA-Z\s]+)\s+v\.?\s+([A-Z][a-zA-Z\s]+)\s*\((\d{4})\)'
        matches = re.findall(case_pattern, text)
        
        if not matches:
            return True, None  # No cases cited
        
        for party1, party2, year in matches:
            case_name = f"{party1.strip()} v. {party2.strip()}"
            
            # Check if case exists in database
            stmt = select(CaseContent.id).where(
                CaseContent.case_name.ilike(f"%{party1.strip()}%")
            ).where(
                CaseContent.case_name.ilike(f"%{party2.strip()}%")
            )
            
            result = await db.execute(stmt)
            case_exists = result.scalar_one_or_none() is not None
            
            if not case_exists:
                logger.warning(f"Unverified case citation: {case_name} ({year})")
                return False, f"Case '{case_name}' not found in verified database"
        
        return True, None
    
    @staticmethod
    def validate_educational_tone(text: str) -> Tuple[bool, Optional[str]]:
        """
        Check for appropriate educational tone.
        
        Should avoid:
        - Informal language
        - Slang
        - Overly casual tone
        """
        text_lower = text.lower()
        
        informal_phrases = [
            "gonna", "wanna", "kinda", "sorta",
            "yeah", "nope", "yep",
            "basically just",
            "to be honest",
            "like i said"
        ]
        
        for phrase in informal_phrases:
            if phrase in text_lower:
                logger.warning(f"Informal language detected: '{phrase}'")
                return False, f"Response uses informal language: '{phrase}'"
        
        return True, None
    
    # ========== MAIN VALIDATION PIPELINE ==========
    
    @staticmethod
    async def validate_response(
        text: str,
        db: AsyncSession,
        strict_mode: bool = True
    ) -> Tuple[bool, List[str]]:
        """
        Run all validation checks on AI-generated response.
        
        Args:
            text: AI-generated response
            db: Database session for case verification
            strict_mode: If True, any violation fails validation
        
        Returns:
            (is_valid, list_of_errors)
        
        Raises:
            GuardrailViolation if strict_mode=True and validation fails
        """
        errors = []
        
        # Check 1: No legal advice
        valid, error = ContentGuardrails.validate_no_legal_advice(text)
        if not valid:
            errors.append(error)
        
        # Check 2: No political bias
        valid, error = ContentGuardrails.validate_no_political_bias(text)
        if not valid:
            errors.append(error)
        
        # Check 3: No speculation
        valid, error = ContentGuardrails.validate_no_speculation(text)
        if not valid:
            errors.append(error)
        
        # Check 4: Constitutional accuracy
        valid, error = ContentGuardrails.validate_constitutional_accuracy(text)
        if not valid:
            errors.append(error)
        
        # Check 5: Case citations (async)
        valid, error = await ContentGuardrails.validate_case_citations(text, db)
        if not valid:
            errors.append(error)
        
        # Check 6: Educational tone
        valid, error = ContentGuardrails.validate_educational_tone(text)
        if not valid:
            errors.append(error)
        
        is_valid = len(errors) == 0
        
        if not is_valid:
            logger.warning(f"Guardrail violations: {errors}")
            if strict_mode:
                raise GuardrailViolation("; ".join(errors))
        
        return is_valid, errors
    
    # ========== DISCLAIMER INJECTION ==========
    
    @staticmethod
    def add_disclaimer(text: str, user_role: str) -> str:
        """
        Add role-appropriate disclaimer to response.
        
        Args:
            text: Validated response
            user_role: 'student' | 'lawyer' | 'general'
        
        Returns:
            Response with disclaimer appended
        """
        disclaimers = {
            "student": "\n\n⚖️ **Educational Content**: This is for learning purposes only, not legal advice.",
            "lawyer": "\n\n⚖️ **Academic Reference**: Verify with latest statutes and case law before application.",
            "general": "\n\n⚖️ **Informational Only**: This is general information, not legal advice. Consult a qualified lawyer for your specific situation."
        }
        
        disclaimer = disclaimers.get(user_role, disclaimers["general"])
        return text + disclaimer
    
    # ========== CONTENT SANITIZATION ==========
    
    @staticmethod
    def sanitize_response(text: str) -> str:
        """
        Clean up AI response for presentation.
        
        - Remove excessive newlines
        - Fix spacing
        - Ensure proper formatting
        """
        # Remove excessive newlines (max 2 consecutive)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Fix spacing around punctuation
        text = re.sub(r'\s+([.,;:!?])', r'\1', text)
        
        # Remove leading/trailing whitespace
        text = text.strip()
        
        return text


# ========== CONVENIENCE FUNCTION ==========

async def validate_and_format_response(
    response: str,
    user_role: str,
    db: AsyncSession,
    strict: bool = True
) -> str:
    """
    Complete validation and formatting pipeline.
    
    Args:
        response: Raw AI response
        user_role: User's role (for disclaimer)
        db: Database session
        strict: Raise exception on violation
    
    Returns:
        Validated, formatted response with disclaimer
    
    Raises:
        GuardrailViolation if validation fails in strict mode
    """
    # Validate
    is_valid, errors = await ContentGuardrails.validate_response(
        response, db, strict_mode=strict
    )
    
    if not is_valid and strict:
        raise GuardrailViolation(f"Content validation failed: {'; '.join(errors)}")
    
    # Sanitize
    clean_response = ContentGuardrails.sanitize_response(response)
    
    # Add disclaimer
    final_response = ContentGuardrails.add_disclaimer(clean_response, user_role)
    
    logger.info("Response validated and formatted successfully")
    return final_response