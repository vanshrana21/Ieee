# backend/routes/debate.py
"""
Moot Court Debate Simulation API
Handles the entire moot court simulation flow with AI-powered opposing arguments.
"""
import os
import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import google.generativeai as genai

router = APIRouter(prefix="/api/debate", tags=["Moot Court Debate"])
logger = logging.getLogger(__name__)

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")
else:
    logger.warning("GEMINI_API_KEY not set. Debate endpoint will not function.")
    model = None


# ============================================
# Request/Response Schemas
# ============================================

class DebateLogEntry(BaseModel):
    role: str = Field(..., description="petitioner or respondent")
    argument: str = Field(..., description="The argument text")
    round: str = Field(..., description="opening, rebuttal, or closing")


class DebateRequest(BaseModel):
    case_facts: str = Field(..., description="Facts from Case Simplifier")
    legal_issues: str = Field(..., description="Legal issues from Case Simplifier")
    user_role: str = Field(..., description="User's assigned role: petitioner or respondent")
    current_round: str = Field(default="opening", description="Current debate phase: opening, rebuttal, or closing")
    user_argument: str = Field(default="", description="User's submitted argument (empty for first round)")
    previous_debate_log: List[DebateLogEntry] = Field(default=[], description="History of arguments for context")


class DebateResponse(BaseModel):
    ai_response: str = Field(..., description="AI-generated argument/rebuttal")
    score: int = Field(..., description="Score for user's argument (0-100)")
    feedback: str = Field(..., description="Feedback on user's argument")
    next_round: str = Field(..., description="Next phase of debate or 'finished'")
    debate_log: List[DebateLogEntry] = Field(..., description="Updated history of arguments")


class DebateErrorResponse(BaseModel):
    error: str


# ============================================
# Helper Functions
# ============================================

async def generate_gemini_response(prompt: str) -> str:
    """Generate AI response using Gemini model."""
    if not model:
        raise RuntimeError("Gemini model not initialized. Check GEMINI_API_KEY.")
    
    try:
        response = await model.generate_content_async(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Gemini generation error: {str(e)}")
        raise RuntimeError(f"AI generation failed: {str(e)}")


async def score_user_argument(
    user_argument: str,
    case_facts: str,
    legal_issues: str,
    user_role: str,
    current_round: str
) -> Dict[str, Any]:
    """
    Score the user's argument and provide feedback using AI.
    Returns score (0-100) and detailed feedback.
    """
    if not user_argument.strip():
        return {"score": 0, "feedback": "No argument submitted."}
    
    scoring_prompt = f"""
    You are a moot court judge evaluating a legal argument.
    
    CASE FACTS: {case_facts}
    LEGAL ISSUES: {legal_issues}
    
    The {user_role.upper()} submitted the following {current_round} argument:
    "{user_argument}"
    
    Evaluate this argument on the following criteria (each out of 25):
    1. Legal Accuracy: Correct application of law and precedents
    2. Relevance: How well it addresses the legal issues
    3. Persuasiveness: Strength of reasoning and rhetoric
    4. Structure: Organization and clarity of presentation
    
    Provide your response in this exact format:
    SCORE: [total score 0-100]
    FEEDBACK: [2-3 sentences of constructive feedback]
    """
    
    try:
        response = await generate_gemini_response(scoring_prompt)
        
        # Parse response for score and feedback
        lines = response.strip().split('\n')
        score = 75  # Default score
        feedback = "Good effort. Keep refining your arguments."
        
        for line in lines:
            if line.upper().startswith("SCORE:"):
                try:
                    score_text = line.split(":")[1].strip()
                    # Extract just the number
                    score = int(''.join(filter(str.isdigit, score_text.split()[0])))
                    score = max(0, min(100, score))  # Clamp to 0-100
                except (ValueError, IndexError):
                    pass
            elif line.upper().startswith("FEEDBACK:"):
                feedback = line.split(":", 1)[1].strip() if ":" in line else feedback
        
        return {"score": score, "feedback": feedback}
    except Exception as e:
        logger.warning(f"Scoring failed, using defaults: {str(e)}")
        return {"score": 75, "feedback": "Your argument has been noted. Continue to strengthen your legal reasoning."}


# ============================================
# API Endpoints
# ============================================

@router.post("", response_model=DebateResponse)
async def debate(request: DebateRequest) -> Dict[str, Any]:
    """
    Moot Court Debate Endpoint
    
    Handles the entire moot court simulation:
    - Takes case facts and legal issues (from Case Simplifier)
    - User plays assigned role (Petitioner/Respondent)
    - Manages debate flow (opening, rebuttal, closing)
    - Generates AI responses for opposing side
    - Scores user arguments and provides feedback
    
    The debate flows through three rounds:
    1. Opening - Initial arguments from both sides
    2. Rebuttal - Counter-arguments addressing opponent's points
    3. Closing - Final summaries and appeals
    """
    try:
        case_facts = request.case_facts
        legal_issues = request.legal_issues
        user_role = request.user_role.lower()
        current_round = request.current_round.lower()
        user_argument = request.user_argument
        previous_debate_log = request.previous_debate_log

        # Validate user role
        if user_role not in ["petitioner", "respondent"]:
            raise HTTPException(
                status_code=400, 
                detail="Invalid user_role. Must be 'petitioner' or 'respondent'."
            )

        # Validate round
        valid_rounds = ["opening", "rebuttal", "closing"]
        if current_round not in valid_rounds:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid current_round. Must be one of: {', '.join(valid_rounds)}"
            )

        # Determine AI's role (opposite of user)
        ai_role = "respondent" if user_role == "petitioner" else "petitioner"

        # Build context from previous debate
        debate_context = ""
        if previous_debate_log:
            debate_context = "\n\nPREVIOUS ARGUMENTS:\n"
            for entry in previous_debate_log:
                debate_context += f"- {entry.role.upper()} ({entry.round}): {entry.argument[:200]}...\n"

        # Construct prompt for AI based on current round
        if current_round == "opening":
            prompt = f"""
You are participating in a moot court as the {ai_role.upper()}.

CASE FACTS: {case_facts}
LEGAL ISSUES: {legal_issues}
{debate_context}

This is the opening statement round. Present a strong opening argument that:
1. Clearly states your position on the legal issues
2. Outlines your key arguments based on the facts
3. References relevant legal principles or precedents
4. Sets the stage for the remainder of the debate

Keep it concise, legally sound, and under 200 words.
"""
        elif current_round == "rebuttal":
            prompt = f"""
You are the {ai_role.upper()} in a moot court.

CASE FACTS: {case_facts}
LEGAL ISSUES: {legal_issues}
{debate_context}

USER'S ARGUMENT (as {user_role.upper()}): {user_argument}

This is the rebuttal round. Provide a strong counter-argument that:
1. Directly addresses and refutes the opponent's key points
2. Identifies weaknesses in their legal reasoning
3. Reinforces your position with additional arguments
4. Uses the case facts to support your rebuttal

Keep it under 200 words but make every point count.
"""
        else:  # closing
            prompt = f"""
You are the {ai_role.upper()} in a moot court.

CASE FACTS: {case_facts}
LEGAL ISSUES: {legal_issues}
{debate_context}

USER'S ARGUMENT (as {user_role.upper()}): {user_argument}

This is the closing argument round. Deliver a compelling closing that:
1. Summarizes your strongest arguments from the debate
2. Addresses any remaining doubts about your position
3. Makes a final persuasive appeal to the court
4. Concludes with a clear request for judgment in your favor

Keep it under 200 words and make it memorable.
"""

        # Generate AI response
        logger.info(f"Generating AI {ai_role} argument for {current_round} round")
        ai_response = await generate_gemini_response(prompt)

        # Score user's argument (skip if empty/first round opening)
        if user_argument.strip():
            scoring_result = await score_user_argument(
                user_argument, case_facts, legal_issues, user_role, current_round
            )
            score = scoring_result["score"]
            feedback = scoring_result["feedback"]
        else:
            score = 0
            feedback = "Submit your argument to receive scoring and feedback."

        # Determine next round
        current_index = valid_rounds.index(current_round)
        next_round = valid_rounds[current_index + 1] if current_index < len(valid_rounds) - 1 else "finished"

        # Update debate log
        updated_log = list(previous_debate_log)
        if user_argument.strip():
            updated_log.append(DebateLogEntry(
                role=user_role,
                argument=user_argument,
                round=current_round
            ))
        updated_log.append(DebateLogEntry(
            role=ai_role,
            argument=ai_response,
            round=current_round
        ))

        logger.info(f"Debate round '{current_round}' completed. Next: '{next_round}'")

        return {
            "ai_response": ai_response,
            "score": score,
            "feedback": feedback,
            "next_round": next_round,
            "debate_log": updated_log
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Debate endpoint error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Debate processing failed: {str(e)}")


@router.get("/judge-verdict")
async def get_judge_verdict(
    case_facts: str,
    legal_issues: str,
    debate_summary: str
) -> Dict[str, Any]:
    """
    Generate a final judge verdict after the debate concludes.
    
    Query params:
    - case_facts: The case facts
    - legal_issues: The legal issues
    - debate_summary: Summary of all arguments made during the debate
    """
    try:
        verdict_prompt = f"""
You are a High Court judge delivering the final verdict in a moot court competition.

CASE FACTS: {case_facts}
LEGAL ISSUES: {legal_issues}

DEBATE SUMMARY:
{debate_summary}

Deliver your verdict that:
1. Summarizes the key arguments from both sides
2. Analyzes the strengths and weaknesses of each party's case
3. Cites relevant legal principles applied
4. Declares the winning party with clear reasoning
5. Awards a score to each side (out of 100)

Format your response as:
WINNING PARTY: [Petitioner/Respondent]
PETITIONER SCORE: [0-100]
RESPONDENT SCORE: [0-100]
REASONING: [Your detailed legal reasoning, 200-300 words]
"""
        
        verdict = await generate_gemini_response(verdict_prompt)
        
        return {
            "success": True,
            "verdict": verdict
        }
    except Exception as e:
        logger.error(f"Verdict generation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Verdict generation failed: {str(e)}")
