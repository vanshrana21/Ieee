"""
backend/services/ai_judge_service.py
Phase 4: AI Moot Court Practice Mode - Judge Engine with India-Specific Behaviors

AI judge service with:
- Real LLM integration (OpenRouter/Groq) + mock fallback
- Phase 4: India-specific behavior enforcement (My Lord, SCC format, interruptions)
- Phase 1 knowledge base for case validation
"""
import logging
from typing import List, Dict, Optional

from knowledge_base import india as kb
from backend.services.llm_client import LLMClient
from backend.services.india_behavior_rules import IndiaBehaviorRules

logger = logging.getLogger(__name__)


class AIJudgeEngine:
    """
    AI Judge engine for solo moot court practice.
    
    Evaluates arguments using:
    - Real LLM (Claude 3.5 Sonnet via OpenRouter or Llama 3.1 via Groq)
    - Phase 1 knowledge base for case validation
    - Mock fallback if LLM unavailable
    """
    
    def __init__(self, kb_service=None):
        """
        Initialize AI Judge Engine with India behavior rules.
        
        Args:
            kb_service: Optional knowledge base service (defaults to knowledge_base.india)
        """
        self.kb = kb_service or kb
        self.llm_client = LLMClient()
        self.use_llm = self.llm_client.is_configured()
        self.behavior_rules = IndiaBehaviorRules(self.kb)
        
        if self.use_llm:
            logger.info("AI Judge: Using real LLM (OpenRouter/Groq) with India behavior enforcement")
        else:
            logger.info("AI Judge: Using mock feedback with India behavior enforcement")
    
    def generate_feedback(
        self,
        argument: str,
        problem_context: dict,
        turn_number: int
    ) -> dict:
        """
        Generate AI judge feedback for user's argument.
        
        Args:
            argument: User's argument text
            problem_context: Dict with problem details (title, etc.)
            turn_number: Current turn number (1, 2, or 3)
        
        Returns:
            dict with feedback_text, missing_cases, citation_valid, 
            has_etiquette, scores, next_question, and behavior_data
        """
        # Phase 4: Run India behavior enforcement checks
        behavior_enforcement = self.behavior_rules.enforce_india_behaviors(
            argument=argument,
            turn_number=turn_number,
            problem_context=problem_context
        )
        
        # Extract behavior check results
        etiquette_check = behavior_enforcement["etiquette_check"]
        citation_check = behavior_enforcement["citation_check"]
        interruption_check = behavior_enforcement["interruption_check"]
        proportionality_check = behavior_enforcement["proportionality_check"]
        landmark_check = behavior_enforcement["landmark_check"]
        
        # Combine missing cases from all checks
        missing_cases = landmark_check["missing_cases"] + citation_check["missing_cases"]
        
        # Citation validity from behavior check
        citation_valid = citation_check["valid_citation"]
        
        # Etiquette from behavior check
        has_etiquette = etiquette_check["has_etiquette"]
        
        # Step 5: Generate feedback using enhanced prompt with behavior enforcement
        if self.use_llm:
            feedback_text = self._generate_llm_feedback(
                argument=argument,
                problem_context=problem_context,
                missing_cases=missing_cases,
                citation_valid=citation_valid,
                has_etiquette=has_etiquette,
                turn_number=turn_number,
                behavior_prompt=behavior_enforcement["enhanced_prompt"]
            )
            # If LLM fails, fallback to mock
            if feedback_text is None:
                logger.warning("LLM failed, falling back to mock feedback")
                feedback_text = self._generate_mock_feedback(
                    argument, problem_context, missing_cases, citation_valid, 
                    has_etiquette, turn_number, behavior_enforcement
                )
        else:
            feedback_text = self._generate_mock_feedback(
                argument, problem_context, missing_cases, citation_valid, 
                has_etiquette, turn_number, behavior_enforcement
            )
        
        # Step 6: Calculate scores with behavior deductions
        scores = self.calculate_scores({
            "missing_cases": missing_cases,
            "citation_valid": citation_valid,
            "has_etiquette": has_etiquette,
            "turn_number": turn_number,
            "points_deducted": behavior_enforcement["total_deductions"]
        })
        
        # Step 7: Inject behavior feedback into response text
        behavior_prefix = ""
        if interruption_check["should_interrupt"]:
            behavior_prefix += f"[INTERRUPTION] {interruption_check['feedback']}\n\n"
        if not etiquette_check["has_etiquette"]:
            behavior_prefix += f"[ETIQUETTE] {etiquette_check['feedback']}\n\n"
        if citation_check["wrong_format_cases"]:
            behavior_prefix += f"[CITATION] {citation_check['feedback']}\n\n"
        if proportionality_check["needs_proportionality"] and not proportionality_check["addressed"]:
            behavior_prefix += f"[PROPORTIONALITY] {proportionality_check['feedback']}\n\n"
        if landmark_check["missing_cases"] and not citation_check["wrong_format_cases"]:
            behavior_prefix += f"[CASE LAW] {landmark_check['feedback']}\n\n"
        
        if behavior_prefix:
            feedback_text = behavior_prefix + feedback_text
        
        # Step 8: Generate next judicial question
        next_question = self._generate_next_question(turn_number, problem_context)
        
        return {
            "feedback_text": feedback_text,
            "missing_cases": missing_cases,
            "citation_valid": citation_valid,
            "has_etiquette": has_etiquette,
            "scores": scores,
            "next_question": next_question,
            "behavior_data": behavior_enforcement  # Phase 4: Include behavior data for UI
        }
    
    def get_prompt_for_turn(
        self,
        argument: str,
        problem_context: dict,
        missing_cases: List[str],
        turn_number: int
    ) -> str:
        """
        Build enhanced prompt for LLM with India KB context.
        
        Args:
            argument: User's argument text
            problem_context: Problem details (title, legal_issue, side)
            missing_cases: List of cases student failed to cite
            turn_number: Current turn (1, 2, or 3)
        
        Returns:
            Formatted prompt string for LLM
        """
        problem_title = problem_context.get("title", "the matter")
        side = problem_context.get("side", "petitioner")
        legal_issue = problem_context.get("legal_issue", "the constitutional question")
        
        # Build missing case line if applicable
        missing_case_line = ""
        if missing_cases:
            missing_case_line = f"\nMISSING CASE: {missing_cases[0]}"
        
        # Domain-specific question guidance
        domain_question = ""
        if "privacy" in problem_title.lower() or "aadhaar" in problem_title.lower():
            domain_question = "- For privacy: \"How does your argument satisfy the Puttaswamy proportionality test para 184?\""
        elif "free speech" in problem_title.lower() or "defamation" in problem_title.lower():
            domain_question = "- For free speech: \"Does your argument distinguish between advocacy and incitement per Shreya Singhal?\""
        elif "bail" in argument.lower():
            domain_question = "- For bail: \"What exceptional circumstances justify anticipatory bail here?\""
        
        prompt = f"""You are Justice D.Y. Chandrachud, former Chief Justice of India. Strict but fair.

MOOT PROBLEM: {problem_title}
LEGAL ISSUE: {legal_issue}
STUDENT'S SIDE: {side}{missing_case_line}

STUDENT ARGUMENT:
"{argument}"

YOUR TASK:
1. [CORRECTION] Fix ONE critical error:
   - If missing landmark case: "Counsel, cite {missing_cases[0] if missing_cases else 'Puttaswamy (2017) 10 SCC 1'}"
   - If wrong citation format: "Cite as (2017) 10 SCC 1, not 'Puttaswamy case'"
   - If no 'My Lord': "Address the bench as 'My Lord'"
   - If legal principle wrong: "The ratio in Puttaswamy actually holds that..."
2. [JUDICIAL QUESTION] Ask ONE sharp follow-up testing depth:
   {domain_question}
   - Generic: "How does this court apply that precedent here?"

RULES:
- Indian legal English only ('Counsel', 'Petitioner', 'Respondent')
- Max 80 words total
- Never praise excessively ('adequate' not 'excellent')
- Cite cases in SCC format ONLY
- Be strict but fair

RESPONSE FORMAT:
[FEEDBACK]: ...
[QUESTION]: ..."""
        
        return prompt
    
    def _generate_llm_feedback(
        self,
        argument: str,
        problem_context: dict,
        missing_cases: List[str],
        citation_valid: bool,
        has_etiquette: bool,
        turn_number: int,
        behavior_prompt: str = None
    ) -> Optional[str]:
        """
        Generate feedback using real LLM with behavior enforcement.
        
        Returns:
            LLM response or None if call fails
        """
        # Use behavior-enhanced prompt if available
        if behavior_prompt:
            prompt = behavior_prompt
        else:
            prompt = self.get_prompt_for_turn(argument, problem_context, missing_cases, turn_number)
        
        # Call LLM with 400 token limit (allowing for behavior prefixes)
        response = self.llm_client.generate_judge_response(prompt, max_tokens=400)
        
        if response:
            # Parse response to extract feedback and question
            feedback_text = self._parse_llm_response(response)
            return feedback_text
        
        return None
    
    def _parse_llm_response(self, response: str) -> str:
        """
        Parse LLM response to extract feedback and question.
        
        Handles format:
        [FEEDBACK]: Counsel, cite Puttaswamy...
        [QUESTION]: State the legal issue...
        """
        feedback = ""
        question = ""
        
        lines = response.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('[FEEDBACK]:'):
                feedback = line.replace('[FEEDBACK]:', '').strip()
            elif line.startswith('[QUESTION]:'):
                question = line.replace('[QUESTION]:', '').strip()
        
        # If parsing failed, use raw response (first 80 words)
        if not feedback:
            words = response.split()[:80]
            return ' '.join(words)
        
        # Combine feedback and question
        full = feedback
        if question:
            full += f" {question}"
        
        # Enforce 80 word limit
        words = full.split()
        if len(words) > 80:
            full = ' '.join(words[:80])
        
        return full
    
    def _generate_mock_feedback(
        self,
        argument: str,
        problem_context: dict,
        missing_cases: List[str],
        citation_valid: bool,
        has_etiquette: bool,
        turn_number: int,
        behavior_enforcement: dict = None
    ) -> str:
        """
        Generate mock judicial feedback (fallback when LLM unavailable).
        Phase 4: Uses behavior enforcement data for accurate feedback.
        """
        problem_title = problem_context.get("title", "the matter")
        side = problem_context.get("side", "petitioner")
        
        # Use behavior enforcement if available
        if behavior_enforcement:
            etiquette = behavior_enforcement["etiquette_check"]
            citation = behavior_enforcement["citation_check"]
            landmark = behavior_enforcement["landmark_check"]
            interruption = behavior_enforcement["interruption_check"]
            proportionality = behavior_enforcement["proportionality_check"]
        else:
            # Fallback to basic checks
            etiquette = {"has_etiquette": has_etiquette, "feedback": "Address the bench as 'My Lord'"}
            citation = {"valid_citation": citation_valid, "wrong_format_cases": [], "feedback": ""}
            landmark = {"missing_cases": missing_cases, "feedback": missing_cases[0] if missing_cases else ""}
            interruption = {"should_interrupt": False}
            proportionality = {"needs_proportionality": False}
        
        # Build feedback components from behavior enforcement
        corrections = []
        
        # Add etiquette correction
        if not etiquette["has_etiquette"]:
            corrections.append(etiquette["feedback"])
        
        # Add citation/case corrections
        if citation["wrong_format_cases"]:
            corrections.append(citation["feedback"])
        elif landmark["missing_cases"]:
            corrections.append(f"Counsel, cite {landmark['missing_cases'][0]}")
        
        # Add proportionality nudge
        if proportionality["needs_proportionality"] and not proportionality["addressed"]:
            corrections.append(proportionality["feedback"])
        
        # Add interruption warning
        if interruption["should_interrupt"]:
            corrections.append(interruption["feedback"])
        
        # Mock feedback generation based on analysis
        if corrections:
            feedback = corrections[0]
        elif citation["valid_citation"] and etiquette["has_etiquette"]:
            feedback = f"Noted, Counsel. Proceed with your submission on {problem_title}."
        else:
            feedback = f"Heard. Continue your argument on {problem_title}."
        
        # Add judicial question based on turn
        if turn_number == 1:
            question = " State the legal issue you're addressing, Counsel."
        elif turn_number == 2:
            question = " Cite the landmark case that supports your proposition."
        else:
            if "privacy" in problem_title.lower() or "aadhaar" in problem_title.lower():
                question = " How does your argument satisfy the Puttaswamy proportionality test?"
            elif "defamation" in problem_title.lower() or "deepfake" in problem_title.lower():
                question = " Does your argument satisfy the 'publication' requirement under Section 499?"
            else:
                question = " What remedy do you seek from this Court?"
        
        full_feedback = feedback + question
        
        # Enforce 80 word limit
        words = full_feedback.split()
        if len(words) > 80:
            full_feedback = " ".join(words[:80])
        
        return full_feedback
    
    def _generate_next_question(self, turn_number: int, problem_context: dict) -> str:
        """Generate the next judicial question based on turn number."""
        problem_title = problem_context.get("title", "").lower()
        
        if turn_number == 1:
            return "State the legal issue you're addressing, Counsel."
        elif turn_number == 2:
            return "Cite the landmark case that supports your proposition."
        else:  # turn_number == 3
            if "privacy" in problem_title or "aadhaar" in problem_title:
                return "How does your argument satisfy the Puttaswamy proportionality test?"
            elif "defamation" in problem_title or "deepfake" in problem_title:
                return "Does your argument satisfy the 'publication' requirement under Section 499?"
            elif "religious" in problem_title or "295a" in problem_title:
                return "Does the comedian's routine have 'deliberate and malicious intention' per Ramji Lal Modi?"
            else:
                return "What remedy do you seek from this Court?"
    
    def calculate_scores(self, feedback_analysis: dict) -> dict:
        """
        Calculate scores based on feedback analysis with behavior deductions.
        
        Phase 4: Deducts etiquette points based on turn progression.
        
        Scoring rubric:
        - legal_accuracy: 5 if missing_cases empty else 3 if 1 case missing else 1
        - citation: 5 if citation_valid else 2
        - etiquette: 5 minus deductions (stricter by turn)
        
        Returns:
            dict with legal_accuracy, citation, etiquette scores (0-5)
        """
        missing_cases = feedback_analysis.get("missing_cases", [])
        citation_valid = feedback_analysis.get("citation_valid", False)
        has_etiquette = feedback_analysis.get("has_etiquette", False)
        points_deducted = feedback_analysis.get("points_deducted", 0)
        
        # Legal accuracy score
        if not missing_cases:
            legal_accuracy = 5
        elif len(missing_cases) == 1:
            legal_accuracy = 3
        else:
            legal_accuracy = 1
        
        # Citation score
        citation = 5 if citation_valid else 2
        
        # Etiquette score with deductions from behavior enforcement
        if has_etiquette:
            etiquette = 5
        else:
            etiquette = max(0, 5 - points_deducted)
        
        return {
            "legal_accuracy": legal_accuracy,
            "citation": citation,
            "etiquette": etiquette
        }

    def enforce_india_behaviors(self, argument: str, turn_number: int, problem_context: dict) -> dict:
        """
        Run all India behavior checks and return enforcement data.
        
        Wrapper method for IndiaBehaviorRules.enforce_india_behaviors().
        
        Returns:
            dict with all behavior checks + enhanced prompt
        """
        return self.behavior_rules.enforce_india_behaviors(
            argument=argument,
            turn_number=turn_number,
            problem_context=problem_context
        )
    
    def analyze_argument_with_context(
        self,
        argument: str,
        side: str,
        moot_problem_context: dict,
        previous_turns: List[dict] = None
    ) -> dict:
        """
        Enhanced AI judge that understands case context + argument flow.
        Checks for: relevance, logical consistency, doctrine application
        
        Args:
            argument: User's argument text to evaluate
            side: "petitioner" or "respondent"
            moot_problem_context: Dict with fact_sheet, legal_issues, relevant_cases
            previous_turns: List of previous argument turns for consistency checking
        
        Returns:
            Dict with feedback, scores, flags (irrelevance, contradictions), suggestions
        """
        fact_sheet = moot_problem_context.get("fact_sheet", "")
        legal_issues = moot_problem_context.get("legal_issues", [])
        relevant_cases = moot_problem_context.get("relevant_cases", [])
        
        # Build argument history context (last 3 turns only to manage tokens)
        history_context = ""
        if previous_turns:
            history_context = "\nPREVIOUS ARGUMENTS IN THIS SESSION:\n"
            for turn in previous_turns[-3:]:
                turn_side = turn.get('side', 'unknown')
                turn_arg = turn.get('argument', '')[:200]
                history_context += f"{turn_side.upper()}: {turn_arg}...\n"
        
        # Format lists for prompt
        legal_issues_text = "\n".join([f"- {issue}" for issue in legal_issues[:5]])
        relevant_cases_text = "\n".join([f"- {case}" for case in relevant_cases[:7]])
        
        # Run India behavior checks (etiquette, citation format, etc.)
        behavior_data = self.behavior_rules.enforce_india_behaviors(
            argument=argument,
            turn_number=1,  # Context-aware method doesn't track turns
            problem_context=moot_problem_context
        )
        
        # Extract behavior check results
        etiquette_check = behavior_data["etiquette_check"]
        citation_check = behavior_data["citation_check"]
        landmark_check = behavior_data["landmark_check"]
        proportionality_check = behavior_data["proportionality_check"]
        
        if self.use_llm:
            feedback_result = self._analyze_with_llm_context(
                argument=argument,
                side=side,
                fact_sheet=fact_sheet,
                legal_issues_text=legal_issues_text,
                relevant_cases_text=relevant_cases_text,
                history_context=history_context,
                behavior_data=behavior_data
            )
        else:
            feedback_result = self._analyze_with_mock_context(
                argument=argument,
                side=side,
                legal_issues=legal_issues,
                relevant_cases=relevant_cases,
                behavior_data=behavior_data
            )
        
        # Merge behavior check results into response
        feedback_result["behavior_data"] = behavior_data
        feedback_result["has_etiquette"] = etiquette_check["has_etiquette"]
        feedback_result["citation_valid"] = citation_check["valid_citation"]
        feedback_result["missing_cases"] = landmark_check["missing_cases"]
        
        return feedback_result
    
    def _analyze_with_llm_context(
        self,
        argument: str,
        side: str,
        fact_sheet: str,
        legal_issues_text: str,
        relevant_cases_text: str,
        history_context: str,
        behavior_data: dict
    ) -> dict:
        """Use LLM for context-aware analysis."""
        
        prompt = f"""You are an Indian Supreme Court judge evaluating moot court arguments.

MOOT PROBLEM CONTEXT:
{fact_sheet[:1500]}

KEY LEGAL ISSUES:
{legal_issues_text}

RELEVANT PRECEDENTS FOR THIS CASE:
{relevant_cases_text}

{history_context}

CURRENT ARGUMENT TO EVALUATE ({side.upper()}):
{argument[:1000]}

EVALUATION CRITERIA:
1. RELEVANCE: Does the argument address the legal issues above? Flag irrelevant points.
2. LOGICAL CONSISTENCY: Does it contradict previous arguments or established facts?
3. DOCTRINE APPLICATION: Correctly applies proportionality test, basic structure doctrine, etc.?
4. PRECEDENT USAGE: Cites cases from the context above (not random unrelated cases)
5. SCC CITATION FORMAT: (YEAR) VOLUME SCC PAGE (e.g., (2017) 10 SCC 1)
6. COURTROOM ETIQUETTE: Begins with "My Lord" or "Your Lordship"

BEHAVIOR CHECK RESULTS:
- Etiquette: {'PASS' if behavior_data['etiquette_check']['has_etiquette'] else 'FAIL - ' + behavior_data['etiquette_check']['feedback']}
- Citation Format: {'PASS' if behavior_data['citation_check']['valid_citation'] else 'FAIL - ' + behavior_data['citation_check']['feedback']}
- Landmark Cases: {'PASS' if not behavior_data['landmark_check']['missing_cases'] else 'MISSING - ' + ', '.join(behavior_data['landmark_check']['missing_cases'][:2])}

INSTRUCTIONS:
Provide specific feedback addressing each evaluation criterion. Be strict but constructive.
Identify any irrelevant points, logical contradictions, or misapplied doctrines.
Suggest relevant cases from the context and doctrines that should be applied.

RETURN VALID JSON ONLY:
{{"feedback": "Your detailed feedback here...", "scores": {{"relevance": 1-5, "logical_consistency": 1-5, "doctrine_application": 1-5, "citation_format": 1-5, "etiquette": 1-5}}, "flags": {{"irrelevant_points": ["Point 1", "Point 2"], "logical_contradictions": ["Contradiction 1"], "missing_doctrines": ["Proportionality test"], "wrong_precedents": ["Case not relevant to this issue"]}}, "suggestions": {{"relevant_cases_to_cite": ["Case 1", "Case 2"], "doctrines_to_apply": ["Doctrine 1"], "etiquette_note": "Address bench properly"}}}}"""
        
        try:
            response = self.llm_client.generate_judge_response(prompt, max_tokens=1000)
            
            if response:
                return self._parse_context_analysis_response(response)
            else:
                return self._get_fallback_context_analysis(behavior_data)
                
        except Exception as e:
            logger.error(f"Error in LLM context analysis: {e}")
            return self._get_fallback_context_analysis(behavior_data)
    
    def _analyze_with_mock_context(
        self,
        argument: str,
        side: str,
        legal_issues: List[str],
        relevant_cases: List[str],
        behavior_data: dict
    ) -> dict:
        """Mock analysis when LLM unavailable."""
        
        etiquette_check = behavior_data["etiquette_check"]
        citation_check = behavior_data["citation_check"]
        landmark_check = behavior_data["landmark_check"]
        
        # Build feedback
        feedback_parts = []
        flags = {"irrelevant_points": [], "logical_contradictions": [], "missing_doctrines": [], "wrong_precedents": []}
        suggestions = {"relevant_cases_to_cite": [], "doctrines_to_apply": [], "etiquette_note": ""}
        
        if not etiquette_check["has_etiquette"]:
            feedback_parts.append(etiquette_check["feedback"])
            suggestions["etiquette_note"] = "Begin with 'My Lord' or 'Your Lordship'"
        
        if citation_check["wrong_format_cases"]:
            feedback_parts.append(citation_check["feedback"])
            flags["wrong_precedents"] = citation_check["wrong_format_cases"][:2]
        
        if landmark_check["missing_cases"]:
            feedback_parts.append(landmark_check["feedback"])
            suggestions["relevant_cases_to_cite"] = landmark_check["missing_cases"][:2]
        
        # Check for proportionality test mention
        if "proportionality" not in argument.lower() and "proportionate" not in argument.lower():
            flags["missing_doctrines"].append("Proportionality test from Puttaswamy")
            suggestions["doctrines_to_apply"].append("Apply the four-pronged proportionality test")
        
        # Generate scores
        scores = {
            "relevance": 4 if legal_issues else 3,
            "logical_consistency": 4,
            "doctrine_application": 5 if not flags["missing_doctrines"] else 3,
            "citation_format": 5 if citation_check["valid_citation"] else 2,
            "etiquette": 5 if etiquette_check["has_etiquette"] else 2
        }
        
        # Build final feedback
        if feedback_parts:
            feedback = " ".join(feedback_parts)
        else:
            feedback = f"Argument addresses the legal issues. Consider citing {relevant_cases[0] if relevant_cases else 'landmark precedents'} to strengthen your position."
        
        return {
            "feedback": feedback,
            "scores": scores,
            "flags": flags,
            "suggestions": suggestions
        }
    
    def _parse_context_analysis_response(self, response: str) -> dict:
        """Parse LLM JSON response for context-aware analysis."""
        try:
            # Clean response
            cleaned = response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            
            data = json.loads(cleaned)
            
            # Validate and set defaults
            result = {
                "feedback": data.get("feedback", "Analysis complete."),
                "scores": data.get("scores", {"relevance": 3, "logical_consistency": 3, "doctrine_application": 3, "citation_format": 3, "etiquette": 3}),
                "flags": data.get("flags", {"irrelevant_points": [], "logical_contradictions": [], "missing_doctrines": [], "wrong_precedents": []}),
                "suggestions": data.get("suggestions", {"relevant_cases_to_cite": [], "doctrines_to_apply": [], "etiquette_note": ""})
            }
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse context analysis JSON: {e}")
            return {
                "feedback": response[:500] if len(response) > 50 else "Evaluation complete. Review citation format and etiquette.",
                "scores": {"relevance": 3, "logical_consistency": 3, "doctrine_application": 3, "citation_format": 3, "etiquette": 3},
                "flags": {"irrelevant_points": [], "logical_contradictions": [], "missing_doctrines": [], "wrong_precedents": []},
                "suggestions": {"relevant_cases_to_cite": [], "doctrines_to_apply": [], "etiquette_note": ""}
            }
    
    def _get_fallback_context_analysis(self, behavior_data: dict) -> dict:
        """Fallback analysis when LLM fails."""
        return {
            "feedback": "AI Judge analysis service temporarily unavailable. Basic checks completed.",
            "scores": {"relevance": 3, "logical_consistency": 3, "doctrine_application": 3, "citation_format": 3, "etiquette": 3},
            "flags": {
                "irrelevant_points": [],
                "logical_contradictions": [],
                "missing_doctrines": [],
                "wrong_precedents": []
            },
            "suggestions": {
                "relevant_cases_to_cite": behavior_data["landmark_check"]["missing_cases"][:2],
                "doctrines_to_apply": ["Review proportionality test"],
                "etiquette_note": behavior_data["etiquette_check"]["feedback"] if not behavior_data["etiquette_check"]["has_etiquette"] else ""
            }
        }
