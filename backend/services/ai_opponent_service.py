"""
backend/services/ai_opponent_service.py
Dynamic AI Opponent for Moot Court - Context-Aware Rebuttal Generation

Generates unique counter-arguments based on:
- User's argument content
- Moot problem context (fact sheet, legal issues, relevant cases)
- Previous arguments (to avoid repetition)
"""
import json
import logging
import os
from typing import List, Dict, Optional
from datetime import datetime, timezone

from backend.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


class AIOpponentService:
    """
    Dynamic AI opponent that generates context-aware rebuttals.
    Uses the same LLM provider as AI Judge (OpenRouter/Groq via LLMClient).
    """
    
    def __init__(self):
        """Initialize AI Opponent with LLM client."""
        self.llm_client = LLMClient()
        self.use_llm = self.llm_client.is_configured()
        
        # Context cache to avoid repeated DB queries
        self._context_cache: Dict[int, dict] = {}
        
        if self.use_llm:
            logger.info("AI Opponent: Using real LLM for dynamic rebuttals")
        else:
            logger.info("AI Opponent: Using template-based rebuttals (LLM not configured)")
    
    def generate_rebuttal(
        self,
        user_argument: str,
        opponent_side: str,
        moot_problem_context: dict,
        previous_arguments: List[str] = None
    ) -> dict:
        """
        Generate dynamic rebuttal based on user's argument + case context.
        
        Args:
            user_argument: User's argument text to rebut
            opponent_side: "petitioner" or "respondent" - which side AI represents
            moot_problem_context: Dict with fact_sheet, legal_issues, relevant_cases
            previous_arguments: List of previous arguments in this round (to avoid repetition)
        
        Returns:
            Dict with rebuttal_text, legal_points, suggested_cases, doctrine_applied
        """
        # Build context from moot problem
        fact_sheet = moot_problem_context.get("fact_sheet", "")
        legal_issues = moot_problem_context.get("legal_issues", [])
        relevant_cases = moot_problem_context.get("relevant_cases", [])
        
        if self.use_llm:
            return self._generate_llm_rebuttal(
                user_argument=user_argument,
                opponent_side=opponent_side,
                fact_sheet=fact_sheet,
                legal_issues=legal_issues,
                relevant_cases=relevant_cases,
                previous_arguments=previous_arguments or []
            )
        else:
            return self._generate_template_rebuttal(
                user_argument=user_argument,
                opponent_side=opponent_side,
                legal_issues=legal_issues,
                relevant_cases=relevant_cases
            )
    
    def _generate_llm_rebuttal(
        self,
        user_argument: str,
        opponent_side: str,
        fact_sheet: str,
        legal_issues: List[str],
        relevant_cases: List[str],
        previous_arguments: List[str]
    ) -> dict:
        """Generate rebuttal using LLM with full context."""
        
        # Determine rebuttal strategy based on opponent side
        strategy_prompt = self._get_strategy_prompt(opponent_side, legal_issues)
        
        # Format lists for prompt
        legal_issues_text = "\n".join([f"- {issue}" for issue in legal_issues[:5]])
        relevant_cases_text = "\n".join([f"- {case}" for case in relevant_cases[:7]])
        previous_args_text = "\n".join([f"- {arg[:150]}..." for arg in previous_arguments[-3:]]) if previous_arguments else "None"
        
        prompt = f"""You are an AI moot court opponent representing the {opponent_side.upper()} side.

CASE CONTEXT (Fact Sheet):
{fact_sheet[:1500]}

LEGAL ISSUES IN DISPUTE:
{legal_issues_text}

RELEVANT PRECEDENTS:
{relevant_cases_text}

{strategy_prompt}

USER'S ARGUMENT (to rebut):
{user_argument[:1000]}

PREVIOUS ARGUMENTS IN THIS ROUND (avoid repetition):
{previous_args_text}

INSTRUCTIONS:
1. Analyze the user's argument for logical flaws, missing precedents, or misapplied doctrines
2. Generate a 2-3 minute rebuttal (300-400 words) that:
   - Directly addresses the user's points with counter-arguments
   - Cites 1-2 relevant cases from the context above
   - Applies constitutional doctrines (proportionality test, basic structure, etc.)
   - Uses proper Indian courtroom etiquette ("My Lord", "Your Lordship", "Counsel")
3. Identify 2-3 key legal points you made
4. Suggest 1-2 additional cases that strengthen your position
5. Note which constitutional doctrine you applied

IMPORTANT RULES:
- Use Indian legal English only ('Counsel', 'Petitioner', 'Respondent')
- Cite cases in SCC format ONLY: (YEAR) VOLUME SCC PAGE
- Address the bench as "My Lord" or "Your Lordship"
- Be respectful but firm in your rebuttal
- Don't repeat points from previous arguments
- Maximum 400 words for rebuttal text

RETURN VALID JSON ONLY (no markdown, no code blocks):
{{"rebuttal_text": "My Lord, the learned counsel for the {'petitioner' if opponent_side == 'respondent' else 'respondent'} has ...", "legal_points": ["Point 1", "Point 2", "Point 3"], "suggested_cases": ["Case 1 citation", "Case 2 citation"], "doctrine_applied": "e.g., proportionality test from Puttaswamy"}}"""
        
        try:
            # Call LLM with higher token limit for rebuttals
            response = self.llm_client.generate_judge_response(prompt, max_tokens=800)
            
            if response:
                # Parse JSON response
                result = self._parse_rebuttal_response(response)
                result["generated_at"] = datetime.now(timezone.utc).isoformat()
                result["source"] = "llm"
                return result
            else:
                # LLM failed, fall back to template
                logger.warning("LLM rebuttal generation failed, using template fallback")
                return self._generate_template_rebuttal(
                    user_argument, opponent_side, legal_issues, relevant_cases
                )
                
        except Exception as e:
            logger.error(f"Error generating LLM rebuttal: {e}")
            return self._generate_template_rebuttal(
                user_argument, opponent_side, legal_issues, relevant_cases
            )
    
    def _generate_template_rebuttal(
        self,
        user_argument: str,
        opponent_side: str,
        legal_issues: List[str],
        relevant_cases: List[str]
    ) -> dict:
        """Generate template-based rebuttal when LLM unavailable."""
        
        # Select a relevant case to cite
        cited_case = relevant_cases[0] if relevant_cases else "Puttaswamy (2017) 10 SCC 1"
        
        if opponent_side == "respondent":
            rebuttal_text = f"""My Lord, with utmost respect, the learned counsel for the petitioner has failed to appreciate the nuances of this case. 

The submission overlooks the binding precedent in {cited_case}, which clearly establishes that the State has a legitimate interest in enacting reasonable restrictions. The proportionality test, as elucidated by this Hon'ble Court, requires the measure to be suitable and necessary - both conditions are satisfied here.

Moreover, the petitioner's argument mischaracterizes the factual matrix. The impugned provision does not impose an absolute prohibition but merely a reasonable regulation, well within the contours of Article 19(2).

For these reasons, I humbly submit that the petition lacks merit and ought to be dismissed."""
            
            legal_points = [
                "State has legitimate interest in reasonable restrictions",
                "Proportionality test is satisfied - measure is suitable and necessary",
                "Impugned provision is regulation, not prohibition"
            ]
            doctrine_applied = "Proportionality test and reasonable restrictions under Article 19(2)"
            
        else:  # petitioner
            rebuttal_text = f"""My Lord, the learned counsel for the respondent has misconstrued the fundamental rights at stake.

The ratio in {cited_case} squarely supports the petitioner's position. This Hon'ble Court has consistently held that fundamental rights cannot be curtailed by executive overreach masquerading as regulation.

The respondent's reliance on 'reasonable restrictions' is misplaced. As held in Maneka Gandhi v. Union of India, any restriction must not be arbitrary or excessive. The impugned action fails on both counts - it is disproportionate and lacks procedural safeguards.

I pray this Hon'ble Court may be pleased to allow the petition and declare the impugned provision unconstitutional."""
            
            legal_points = [
                "Fundamental rights cannot be curtailed by executive overreach",
                "Restriction must not be arbitrary or excessive per Maneka Gandhi",
                "Impugned action is disproportionate and lacks safeguards"
            ]
            doctrine_applied = "Basic structure doctrine and proportionality test"
        
        return {
            "rebuttal_text": rebuttal_text,
            "legal_points": legal_points,
            "suggested_cases": relevant_cases[1:3] if len(relevant_cases) > 1 else [cited_case],
            "doctrine_applied": doctrine_applied,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "template"
        }
    
    def _get_strategy_prompt(self, opponent_side: str, legal_issues: List[str]) -> str:
        """Generate strategy prompt based on side and legal issues."""
        if opponent_side == "respondent":
            return """YOUR STRATEGY (Respondent):
- Defend the existing law/policy as constitutional and reasonable
- Argue that the petitioner's interpretation is too broad or impractical
- Emphasize state interest, public welfare, and reasonable restrictions
- Use precedents that uphold governmental powers under Articles 19(2), 21A, etc.
- Apply proportionality test to show the law passes all four prongs:
  1. Suitable (rationally connected to objective)
  2. Necessary (least restrictive means)
  3. Proportionate (balance of interests)
  4. Has safeguards (fair procedures)"""
        else:  # petitioner
            return """YOUR STRATEGY (Petitioner):
- Challenge the law/policy as unconstitutional and disproportionate
- Argue violation of fundamental rights (Articles 14, 19, 21, 25 as applicable)
- Show precedent supports your narrow interpretation
- Highlight procedural flaws, vagueness, or overreach
- Apply proportionality test to show the law fails at least one prong:
  1. Not suitable (irrational connection)
  2. Not necessary (less restrictive alternatives exist)
  3. Not proportionate (disproportionate burden)
  4. No safeguards (unfair procedures)"""
    
    def _parse_rebuttal_response(self, response: str) -> dict:
        """Parse LLM JSON response for rebuttal data."""
        try:
            # Clean up response - remove markdown code blocks if present
            cleaned = response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            
            # Parse JSON
            data = json.loads(cleaned)
            
            # Validate required fields
            required = ["rebuttal_text", "legal_points", "suggested_cases", "doctrine_applied"]
            for field in required:
                if field not in data:
                    data[field] = self._get_default_value(field)
            
            return data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse rebuttal JSON: {e}")
            # Return fallback with raw text
            return {
                "rebuttal_text": response[:500] if len(response) > 100 else "My Lord, with respect, I must differ from the learned counsel's submission.",
                "legal_points": ["Argument addresses legal merits", "Cites relevant precedents"],
                "suggested_cases": ["See relevant precedents in moot problem"],
                "doctrine_applied": "Constitutional interpretation principles"
            }
    
    def _get_default_value(self, field: str):
        """Get default value for missing fields."""
        defaults = {
            "rebuttal_text": "My Lord, the learned counsel's submission requires careful consideration.",
            "legal_points": ["Addresses legal merits", "Considers precedents"],
            "suggested_cases": ["Refer to moot problem context"],
            "doctrine_applied": "Constitutional interpretation"
        }
        return defaults.get(field, "")
    
    def cache_context(self, round_id: int, context: dict):
        """Cache moot problem context for a round to avoid repeated DB queries."""
        self._context_cache[round_id] = context
        logger.info(f"Cached moot context for round {round_id}")
    
    def get_cached_context(self, round_id: int) -> Optional[dict]:
        """Retrieve cached context for a round."""
        return self._context_cache.get(round_id)
    
    def clear_cache(self, round_id: int = None):
        """Clear context cache for a round or all rounds."""
        if round_id:
            self._context_cache.pop(round_id, None)
        else:
            self._context_cache.clear()
