# backend/services/ai_analysis_service.py
"""
AI-powered analysis service for legal case data.
Uses RAG pattern: AI analyzes only the provided case data, no hallucination.
Enhanced with structured case brief generation.
"""
import os
import logging
from typing import List, Dict, Optional
import google.generativeai as genai

logger = logging.getLogger(__name__)

# Configure AI API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


def analyze_cases_with_ai(
    cases: List[Dict],
    user_query: str,
    analysis_type: str = "summary"
) -> Dict:
    """
    Analyze retrieved legal cases using AI.
    
    CRITICAL: AI receives ONLY the case data retrieved from CourtListener.
    It does NOT search for cases, invent cases, or access external data.
    
    Args:
        cases: List of case dictionaries from CourtListener
        user_query: Original user search query
        analysis_type: Type of analysis ("summary", "comparison", "legal_issue")
    
    Returns:
        Dictionary containing AI analysis results
    """
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not set in environment")
        raise ValueError("AI API key not configured")
    
    if not cases:
        return {
            "analysis": "No cases were found matching your query. Please try different search terms.",
            "case_count": 0,
            "query": user_query
        }
    
    # Prepare case data for AI context
    case_context = _prepare_case_context(cases)
    
    # Build AI prompt based on analysis type
    prompt = _build_analysis_prompt(
        case_context=case_context,
        user_query=user_query,
        analysis_type=analysis_type,
        case_count=len(cases)
    )
    
    try:
        logger.info(f"Sending {len(cases)} cases to AI for analysis")
        
        # Call AI API
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        
        if not response or not response.text:
            raise RuntimeError("AI API returned empty response")
        
        analysis_text = response.text.strip()
        
        logger.info(f"AI analysis completed successfully")
        
        return {
            "analysis": analysis_text,
            "case_count": len(cases),
            "cases_analyzed": [
                {
                    "case_name": case["case_name"],
                    "court": case["court"],
                    "year": case["year"],
                    "citation": case.get("citation")
                }
                for case in cases
            ],
            "query": user_query
        }
    
    except Exception as e:
        logger.error(f"AI analysis failed: {str(e)}", exc_info=True)
        raise RuntimeError(f"AI analysis error: {str(e)}")


def _prepare_case_context(cases: List[Dict]) -> str:
    """
    Format case data into structured context for AI analysis.
    
    Args:
        cases: List of case dictionaries
    
    Returns:
        Formatted string containing all case data
    """
    context_parts = []
    
    for i, case in enumerate(cases, 1):
        case_text = f"""
CASE {i}:
Case Name: {case['case_name']}
Court: {case['court']}
Year: {case.get('year', 'Unknown')}
Docket Number: {case.get('docket_number', 'N/A')}
Citation: {case.get('citation', 'N/A')}

Opinion Text:
{case['opinion_text']}

---
"""
        context_parts.append(case_text.strip())
    
    return "\n\n".join(context_parts)


def _build_analysis_prompt(
    case_context: str,
    user_query: str,
    analysis_type: str,
    case_count: int
) -> str:
    """
    Build AI prompt with strict grounding instructions.
    
    Args:
        case_context: Formatted case data
        user_query: User's original query
        analysis_type: Type of analysis to perform
        case_count: Number of cases provided
    
    Returns:
        Complete prompt string for AI
    """
    base_instruction = f"""You are a legal research assistant analyzing real legal cases from the CourtListener database.

CRITICAL INSTRUCTIONS:
1. You have been provided with {case_count} real legal case(s) below
2. Base your ENTIRE response ONLY on these provided cases
3. DO NOT invent, imagine, or reference any cases not provided
4. DO NOT use your general knowledge about legal cases
5. If the provided cases don't fully answer the query, say so explicitly
6. Cite specific case names when making points
7. Be precise and factual

USER QUERY: {user_query}

RETRIEVED CASES:
{case_context}

"""
    
    if analysis_type == "summary":
        task = """Provide a comprehensive summary of these cases, including:
- Key holdings and legal principles
- Important facts
- Court reasoning
- Relevance to the user's query"""
    
    elif analysis_type == "comparison":
        task = """Compare and contrast these cases:
- Identify common legal issues
- Highlight differences in court reasoning
- Note any conflicting holdings
- Explain how they relate to each other"""
    
    elif analysis_type == "legal_issue":
        task = """Analyze the legal issues presented in these cases:
- Identify the primary legal questions
- Summarize how each court addressed these issues
- Extract key legal principles
- Note any precedents established"""
    
    else:
        task = """Analyze these cases and provide insights relevant to the user's query."""
    
    return base_instruction + task


def generate_case_brief(case: Dict) -> Optional[Dict]:
    """
    Generate an AI-powered structured brief for a single case.
    
    Args:
        case: Case dictionary from CourtListener with keys:
              - plain_text: Full opinion text (preferred)
              - html: HTML opinion text (fallback)
              - case_name, court, date_filed, judges, etc.
    
    Returns:
        Dictionary with structured case brief sections, or None if no text available
    """
    if not GEMINI_API_KEY:
        raise ValueError("AI API key not configured")
    
    # Check if we have opinion text
    opinion_text = case.get("plain_text", "") or case.get("html", "")
    
    if not opinion_text or len(opinion_text.strip()) < 100:
        logger.info(f"No sufficient opinion text for case {case.get('id')}, skipping AI brief")
        return None
    
    # Limit text length for API efficiency (first 15000 chars)
    opinion_text = opinion_text[:15000]
    
    prompt = f"""You are a legal research assistant. Generate a structured case brief for the following case.

Case Name: {case.get('case_name', 'Unknown')}
Court: {case.get('court_full_name', case.get('court', 'Unknown'))}
Date Filed: {case.get('date_filed', 'Unknown')}
Judges: {case.get('judges', 'Not specified')}

Opinion Text:
{opinion_text}

Generate a structured case brief with EXACTLY these sections:

1. CASE SUMMARY (2-3 sentences overview)
2. LEGAL ISSUES (bullet points of key legal questions)
3. COURT'S HOLDING (the decision reached)
4. REASONING (court's rationale and legal analysis)
5. FINAL OUTCOME (practical result and implications)

Format your response with clear section headers. Be concise but thorough. Base your brief ONLY on the provided opinion text. Do not invent facts or cite external cases."""
    
    try:
        logger.info(f"Generating AI brief for case {case.get('id')}")
        
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        
        if not response or not response.text:
            logger.warning("AI returned empty response for case brief")
            return None
        
        brief_text = response.text.strip()
        
        # Parse the structured response
        parsed_brief = _parse_structured_brief(brief_text)
        
        logger.info(f"Successfully generated AI brief for case {case.get('id')}")
        return parsed_brief
    
    except Exception as e:
        logger.error(f"Failed to generate case brief: {str(e)}")
        return None


def _parse_structured_brief(brief_text: str) -> Dict:
    """
    Parse AI-generated brief into structured sections.
    
    Args:
        brief_text: Raw AI-generated brief text
    
    Returns:
        Dictionary with structured sections
    """
    sections = {
        "case_summary": "",
        "legal_issues": "",
        "holding": "",
        "reasoning": "",
        "outcome": "",
        "full_brief": brief_text
    }
    
    # Try to extract sections using common patterns
    lines = brief_text.split('\n')
    current_section = None
    current_content = []
    
    section_keywords = {
        "CASE SUMMARY": "case_summary",
        "SUMMARY": "case_summary",
        "LEGAL ISSUES": "legal_issues",
        "ISSUES": "legal_issues",
        "COURT'S HOLDING": "holding",
        "HOLDING": "holding",
        "DECISION": "holding",
        "REASONING": "reasoning",
        "RATIONALE": "reasoning",
        "FINAL OUTCOME": "outcome",
        "OUTCOME": "outcome",
        "RESULT": "outcome"
    }
    
    for line in lines:
        line_upper = line.strip().upper()
        
        # Check if this line is a section header
        matched_section = None
        for keyword, section_key in section_keywords.items():
            if keyword in line_upper and len(line.strip()) < 50:
                matched_section = section_key
                break
        
        if matched_section:
            # Save previous section
            if current_section and current_content:
                sections[current_section] = '\n'.join(current_content).strip()
            
            # Start new section
            current_section = matched_section
            current_content = []
        elif current_section and line.strip():
            current_content.append(line)
    
    # Save last section
    if current_section and current_content:
        sections[current_section] = '\n'.join(current_content).strip()
    
    # If parsing failed, use full text as summary
    if not any(sections[k] for k in ["case_summary", "legal_issues", "holding"]):
        sections["case_summary"] = brief_text[:500]
        sections["legal_issues"] = "See full brief below"
        sections["holding"] = "See full brief below"
        sections["reasoning"] = "See full brief below"
        sections["outcome"] = "See full brief below"
    
    return sections