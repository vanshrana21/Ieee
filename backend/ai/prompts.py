"""
backend/ai/prompts.py
Phase 10.1: System-Level Prompt Guards

PURPOSE:
Define system prompts that enforce scope restrictions at the LLM level.

STRICT RULES FOR AI:
1. Answer ONLY using provided curriculum content
2. Refuse questions outside subject/module
3. NEVER introduce new laws, cases, or sections
4. NEVER change learning order
5. NEVER suggest skipping topics
"""

from typing import Optional
from backend.ai.context import AIContext


SYSTEM_GUARD_PROMPT = """You are Juris AI Tutor, an educational assistant for Indian law students.

STRICT RULES - YOU MUST FOLLOW THESE:
1. Answer ONLY using the provided curriculum content below.
2. If a question goes outside the student's current subject/module, refuse politely.
3. NEVER introduce new laws, cases, or sections not in the curriculum.
4. NEVER change the learning order or suggest skipping topics.
5. NEVER give legal advice for real situations.
6. If you're unsure whether something is in scope, say: "This is outside your current study scope."

CURRENT SCOPE:
{scope_description}

CURRICULUM CONTENT:
{content_summary}

Remember: You are a tutor, not a lawyer. Your role is to help students understand their curriculum, not to expand it.
"""


REFUSAL_RESPONSES = {
    "out_of_scope": (
        "I can only help you with your current subject: {subject}. "
        "This question is outside your study scope. "
        "Would you like to ask something about {subject} instead?"
    ),
    "off_topic": (
        "This topic isn't part of your current study material. "
        "Let's stay focused on {subject}. "
        "What would you like to know about your current lesson?"
    ),
    "unknown_subject": (
        "I'm not sure if that's in your syllabus. "
        "Please ask about topics from your current subject: {subject}."
    ),
    "legal_advice": (
        "I can only provide educational explanations, not legal advice. "
        "For your specific situation, please consult a qualified lawyer."
    ),
    "skip_request": (
        "I can't help you skip ahead in the curriculum. "
        "Each topic builds on the previous one. "
        "Let's make sure you understand the current material first."
    )
}


def build_scoped_prompt(
    context: AIContext,
    additional_content: Optional[str] = None
) -> str:
    """
    Build a system prompt with scope restrictions.
    
    Args:
        context: Validated AI context
        additional_content: Optional extra curriculum content to include
    
    Returns:
        Complete system prompt with scope guards
    """
    scope_parts = []
    
    if context.subject_title:
        scope_parts.append(f"Subject: {context.subject_title}")
    if context.module_title:
        scope_parts.append(f"Module: {context.module_title}")
    if context.content_title:
        scope_parts.append(f"Current Topic: {context.content_title}")
    
    scope_description = "\n".join(scope_parts) if scope_parts else "No specific scope set"
    
    content_summary = ""
    if context.content_body:
        max_content_length = 2000
        body = context.content_body[:max_content_length]
        if len(context.content_body) > max_content_length:
            body += "... [content truncated for context]"
        content_summary = f"### {context.content_title or 'Current Content'}\n{body}"
    
    if additional_content:
        content_summary += f"\n\n### Additional Context\n{additional_content}"
    
    if not content_summary:
        content_summary = "No specific content loaded. Answer based on general curriculum knowledge within the subject scope."
    
    return SYSTEM_GUARD_PROMPT.format(
        scope_description=scope_description,
        content_summary=content_summary
    )


def get_refusal_message(
    refusal_type: str,
    subject_title: str = "your current subject"
) -> str:
    """
    Get appropriate refusal message.
    
    Args:
        refusal_type: Key from REFUSAL_RESPONSES
        subject_title: Subject name for message
    
    Returns:
        Formatted refusal message
    """
    template = REFUSAL_RESPONSES.get(refusal_type, REFUSAL_RESPONSES["out_of_scope"])
    return template.format(subject=subject_title)


TOPIC_SPECIFIC_INSTRUCTIONS = {
    "contract": """
When teaching Contract Law:
- Focus on Indian Contract Act, 1872
- Reference leading Indian cases (Mohori Bibee, Balfour v Balfour applicability in India)
- Explain consideration, offer, acceptance, capacity
- Do NOT teach contract drafting or negotiation tactics
""",
    "criminal": """
When teaching Criminal Law:
- Focus on IPC (Indian Penal Code) and CrPC
- Explain elements of offenses, mens rea, actus reus
- Reference SC and HC judgments only
- Do NOT advise on how to handle criminal charges
""",
    "constitutional": """
When teaching Constitutional Law:
- Focus on Indian Constitution
- Explain fundamental rights, DPSP, amendments
- Reference landmark SC judgments
- Note any recent changes (Article 370 revocation, etc.)
- Do NOT discuss political implications
""",
}


def get_subject_specific_instructions(subject_code: str) -> str:
    """
    Get subject-specific teaching instructions.
    
    Args:
        subject_code: Subject identifier (e.g., 'contract', 'criminal')
    
    Returns:
        Subject-specific instructions or empty string
    """
    subject_lower = subject_code.lower()
    
    for key, instructions in TOPIC_SPECIFIC_INSTRUCTIONS.items():
        if key in subject_lower:
            return instructions
    
    return ""
