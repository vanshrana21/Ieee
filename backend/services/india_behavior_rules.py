"""
backend/services/india_behavior_rules.py
Phase 4: India-Specific Judge Behaviors

Enforces 5 India-specific courtroom norms:
1. "My Lord" etiquette (mandatory address)
2. SCC citation format policing
3. Judicial interruptions (after 60 words)
4. Landmark case nudges (from Phase 1 KB)
5. Proportionality test focus (constitutional law)
"""
import logging
from typing import List, Dict, Optional
from knowledge_base import india as kb

logger = logging.getLogger(__name__)

# Constants
MAX_WORDS_BEFORE_INTERRUPTION = 60
ETIQUETTE_DEDUCTION_TURN_1 = 0
ETIQUETTE_DEDUCTION_TURN_2 = 2
ETIQUETTE_DEDUCTION_TURN_3 = 3


class IndiaBehaviorRules:
    """
    Enforces India-specific courtroom behaviors for AI Moot Court.
    
    Uses Phase 1 knowledge base (knowledge_base.india) for case validation.
    All behaviors are runtime enforcement — no database changes.
    """
    
    def __init__(self, kb_service=None):
        """
        Initialize behavior rules.
        
        Args:
            kb_service: Optional knowledge base service (defaults to knowledge_base.india)
        """
        self.kb = kb_service or kb
    
    def check_my_lord_etiquette(self, argument: str, turn_number: int) -> Dict:
        """
        Check if student addressed the bench as "My Lord".
        
        Rules:
        - Turn 1: Gentle reminder, 0 points deducted
        - Turn 2: Warning, 2 points deducted
        - Turn 3: Serious lapse, 3 points deducted
        
        Detection: case-insensitive "my lord" in first 15 characters
        
        Returns:
            {
                "has_etiquette": bool,
                "feedback": str,
                "points_deducted": int,
                "severity": str  # "reminder", "warning", "serious"
            }
        """
        # Check first 15 characters for "my lord"
        opening = argument[:15].lower()
        has_etiquette = "my lord" in opening
        
        if has_etiquette:
            return {
                "has_etiquette": True,
                "feedback": "",
                "points_deducted": 0,
                "severity": "none"
            }
        
        # Determine severity by turn
        if turn_number == 1:
            feedback = "Counsel, address the bench as 'My Lord'"
            points = ETIQUETTE_DEDUCTION_TURN_1
            severity = "reminder"
        elif turn_number == 2:
            feedback = "You failed to address the bench properly"
            points = ETIQUETTE_DEDUCTION_TURN_2
            severity = "warning"
        else:  # turn_number >= 3
            feedback = "Repeated failure to address bench — serious lapse"
            points = ETIQUETTE_DEDUCTION_TURN_3
            severity = "serious"
        
        return {
            "has_etiquette": False,
            "feedback": feedback,
            "points_deducted": points,
            "severity": severity
        }
    
    def check_scc_citation(self, argument: str) -> Dict:
        """
        Check for valid SCC citation format.
        
        Steps:
        1. Find relevant cases from KB
        2. Check for valid SCC pattern
        3. Report missing/wrong format citations
        
        Returns:
            {
                "valid_citation": bool,
                "missing_cases": List[str],
                "wrong_format_cases": List[str],
                "feedback": str,
                "expected_cases": List[str]
            }
        """
        # Step 1: Find expected cases from KB
        relevant_cases = self.kb.find_relevant_cases(argument)
        expected_cases = [case.name for case in relevant_cases]
        
        # Step 2: Check SCC format using KB pattern
        has_valid_scc = self.kb.is_valid_scc_citation(argument)
        
        # Step 3: Find case name mentions (even without proper citation)
        wrong_format_cases = []
        missing_cases = []
        
        # Common case name patterns students use (wrong format)
        informal_patterns = {
            "Puttaswamy": ["Puttaswamy case", "Justice Puttaswamy", "K.S. Puttaswamy"],
            "Subramanian Swamy": ["Swamy case", "Subramanian case", "Dr. Swamy"],
            "Ramji Lal Modi": ["Modi case", "Ramji case", "1957 case"],
            "Gurbaksh Singh Sibbia": ["Sibbia case", "1980 case", "Gurbaksh case"],
            "Shreya Singhal": ["Shreya case", "Singhal case", "66A case"],
            "Vishaka": ["Vishaka case", "Vishaka guidelines", "1997 case"],
            "M.C. Mehta": ["Mehta case", "MC Mehta", "Oleum gas case"]
        }
        
        # Check for informal mentions without proper SCC
        arg_lower = argument.lower()
        for case_name, informal_names in informal_patterns.items():
            # Check if case is mentioned at all
            case_mentioned = any(informal.lower() in arg_lower for informal in informal_names)
            case_mentioned = case_mentioned or case_name.lower() in arg_lower
            
            if case_mentioned and not has_valid_scc:
                # Case mentioned but no proper SCC citation
                if case_name == "Puttaswamy":
                    wrong_format_cases.append(f"{case_name} (2017) 10 SCC 1")
                elif case_name == "Subramanian Swamy":
                    wrong_format_cases.append(f"{case_name} (2016) 7 SCC 221")
                elif case_name == "Ramji Lal Modi":
                    wrong_format_cases.append(f"{case_name} (1957) SCR 874")
                elif case_name == "Gurbaksh Singh Sibbia":
                    wrong_format_cases.append(f"{case_name} (1980) 2 SCC 565")
                elif case_name == "Shreya Singhal":
                    wrong_format_cases.append(f"{case_name} (2015) 5 SCC 1")
                elif case_name == "Vishaka":
                    wrong_format_cases.append(f"{case_name} (1997) 6 SCC 241")
                elif case_name == "M.C. Mehta":
                    wrong_format_cases.append(f"{case_name} (1987) 1 SCC 395")
        
        # Build feedback
        feedback = ""
        if wrong_format_cases:
            case = wrong_format_cases[0]
            if "Puttaswamy" in case:
                feedback = f"Cite Puttaswamy as (2017) 10 SCC 1, not 'Puttaswamy case'"
            elif "Swamy" in case:
                feedback = f"Cite Subramanian Swamy as (2016) 7 SCC 221"
            elif "Modi" in case:
                feedback = f"Cite Ramji Lal Modi as (1957) SCR 874"
            elif "Sibbia" in case:
                feedback = f"Cite Gurbaksh Singh Sibbia as (1980) 2 SCC 565"
            else:
                feedback = f"Use SCC format for {case}"
        
        return {
            "valid_citation": has_valid_scc,
            "missing_cases": missing_cases,
            "wrong_format_cases": wrong_format_cases,
            "feedback": feedback,
            "expected_cases": expected_cases
        }
    
    def check_judicial_interruption(self, argument: str) -> Dict:
        """
        Check if argument is too long (triggers judicial interruption).
        
        Indian judges interrupt after ~60 words of rambling.
        
        Returns:
            {
                "should_interrupt": bool,
                "word_count": int,
                "feedback": str
            }
        """
        word_count = len(argument.split())
        should_interrupt = word_count > MAX_WORDS_BEFORE_INTERRUPTION
        
        if should_interrupt:
            feedback = f"⚡ Judge interrupted after {word_count} words — be concise, Counsel"
        else:
            feedback = ""
        
        return {
            "should_interrupt": should_interrupt,
            "word_count": word_count,
            "feedback": feedback
        }
    
    def check_proportionality_test(self, argument: str, problem_context: Dict) -> Dict:
        """
        Check if student addressed proportionality test for constitutional law.
        
        Triggers for: privacy, free speech, rights restriction problems.
        
        Returns:
            {
                "needs_proportionality": bool,
                "addressed": bool,
                "feedback": str
            }
        """
        problem_title = problem_context.get("title", "").lower()
        problem_issue = problem_context.get("legal_issue", "").lower()
        
        # Check if problem involves rights restriction
        needs_proportionality = any(keyword in problem_title or keyword in problem_issue 
                                     for keyword in ["privacy", "free speech", "article 19", 
                                                    "article 21", "fundamental right", "restriction"])
        
        if not needs_proportionality:
            return {
                "needs_proportionality": False,
                "addressed": False,
                "feedback": ""
            }
        
        # Check if student mentioned proportionality test elements
        prop_keywords = ["proportionality", "legitimate aim", "necessary", "balancing", 
                        "rational nexus", "least restrictive"]
        arg_lower = argument.lower()
        addressed = any(keyword in arg_lower for keyword in prop_keywords)
        
        if not addressed:
            feedback = "How does your argument satisfy the four-prong Puttaswamy proportionality test?"
        else:
            feedback = ""
        
        return {
            "needs_proportionality": True,
            "addressed": addressed,
            "feedback": feedback
        }
    
    def check_landmark_case_nudge(self, argument: str, problem_context: Dict) -> Dict:
        """
        Check if student cited required landmark cases.
        
        Uses Phase 1 KB to determine expected cases.
        
        Returns:
            {
                "expected_cases": List[str],
                "cited_cases": List[str],
                "missing_cases": List[str],
                "feedback": str
            }
        """
        problem_title = problem_context.get("title", "").lower()
        problem_issue = problem_context.get("legal_issue", "").lower()
        
        # Get expected cases from KB
        expected_cases = []
        cited_cases = []
        
        # Domain-specific landmark cases
        if "privacy" in problem_title or "aadhaar" in problem_title:
            expected_cases = ["Puttaswamy (2017) 10 SCC 1"]
        elif "deepfake" in problem_title or "defamation" in problem_title:
            expected_cases = ["Subramanian Swamy (2016) 7 SCC 221"]
        elif "religious" in problem_title or "295a" in problem_title:
            expected_cases = ["Ramji Lal Modi (1957) SCR 874"]
        elif "bail" in problem_title or "anticipatory" in problem_title:
            expected_cases = ["Gurbaksh Singh Sibbia (1980) 2 SCC 565"]
        elif "free speech" in problem_title or "section 66a" in problem_title:
            expected_cases = ["Shreya Singhal (2015) 5 SCC 1"]
        elif "sexual harassment" in problem_title or "workplace" in problem_title:
            expected_cases = ["Vishaka (1997) 6 SCC 241"]
        elif "environment" in problem_title:
            expected_cases = ["M.C. Mehta (1987) 1 SCC 395"]
        
        # Check for case mentions in argument
        arg_lower = argument.lower()
        for case in expected_cases:
            case_name_lower = case.lower().split()[0]  # Get first word (e.g., "Puttaswamy")
            if case_name_lower in arg_lower:
                cited_cases.append(case)
        
        # Find missing cases
        missing_cases = [c for c in expected_cases if c not in cited_cases]
        
        # Generate feedback
        feedback = ""
        if missing_cases:
            case = missing_cases[0]
            feedback = f"You missed citing {case}"
        
        return {
            "expected_cases": expected_cases,
            "cited_cases": cited_cases,
            "missing_cases": missing_cases,
            "feedback": feedback
        }
    
    def generate_behavior_enforcement_prompt(
        self,
        argument: str,
        problem_context: Dict,
        turn_number: int
    ) -> str:
        """
        Build enhanced prompt that INSTRUCTS LLM to enforce India-specific behaviors.
        
        Returns:
            Enhanced prompt string with behavior enforcement instructions
        """
        # Run all behavior checks
        etiquette = self.check_my_lord_etiquette(argument, turn_number)
        citation = self.check_scc_citation(argument)
        interruption = self.check_judicial_interruption(argument)
        proportionality = self.check_proportionality_test(argument, problem_context)
        landmark = self.check_landmark_case_nudge(argument, problem_context)
        
        problem_title = problem_context.get("title", "the matter")
        side = problem_context.get("side", "petitioner")
        
        # Build enforcement notes
        enforcement_notes = []
        
        if not etiquette["has_etiquette"]:
            enforcement_notes.append(
                f"1. ETIQUETTE VIOLATION: Student missed 'My Lord'. "
                f"Deduct {etiquette['points_deducted']} points. "
                f"Feedback: '{etiquette['feedback']}'"
            )
        
        if citation["wrong_format_cases"]:
            enforcement_notes.append(
                f"2. CITATION ERROR: Wrong format. "
                f"Feedback: '{citation['feedback']}'"
            )
        elif not citation["valid_citation"] and landmark["missing_cases"]:
            enforcement_notes.append(
                f"2. MISSING CASE: {landmark['missing_cases'][0]}. "
                f"Feedback: 'Counsel, cite {landmark['missing_cases'][0]}'"
            )
        
        if interruption["should_interrupt"]:
            enforcement_notes.append(
                f"3. INTERRUPTION: Argument too long ({interruption['word_count']} words). "
                f"Interrupt and demand brevity."
            )
        
        if proportionality["needs_proportionality"] and not proportionality["addressed"]:
            enforcement_notes.append(
                f"4. PROPORTIONALITY: Student didn't address Puttaswamy test. "
                f"Question: '{proportionality['feedback']}'"
            )
        
        enforcement_section = "\n".join(enforcement_notes) if enforcement_notes else "All behaviors correct. Be fair but demanding."
        
        prompt = f"""You are Justice D.Y. Chandrachud, Chief Justice of India. STRICT INDIAN COURTROOM ENFORCEMENT.

MOOT PROBLEM: {problem_title}
STUDENT'S SIDE: {side}
TURN NUMBER: {turn_number}

STUDENT ARGUMENT:
"{argument}"

BEHAVIOR ENFORCEMENT RULES — APPLY STRICTLY:
{enforcement_section}

JUDICIAL STANDARDS:
- Address student as "Counsel" (never by name)
- Student MUST say "My Lord" — enforce this
- SCC format mandatory: "(2017) 10 SCC 1" NOT "Puttaswamy case"
- Interrupt rambling arguments (>60 words)
- For privacy/free speech: demand proportionality test analysis
- Never praise excessively — be strict but fair
- Max 80 words in response

RESPONSE FORMAT:
[FEEDBACK]: Your judicial correction + feedback
[QUESTION]: One sharp follow-up question

BE STRICT. Indian moot courts deduct marks for these lapses."""
        
        return prompt
    
    def enforce_india_behaviors(
        self,
        argument: str,
        turn_number: int,
        problem_context: Dict
    ) -> Dict:
        """
        Run all India behavior checks and return comprehensive enforcement data.
        
        Returns:
            {
                "etiquette_check": dict,
                "citation_check": dict,
                "interruption_check": dict,
                "proportionality_check": dict,
                "landmark_check": dict,
                "enhanced_prompt": str,
                "total_deductions": int,
                "behavior_summary": str
            }
        """
        # Run all checks
        etiquette = self.check_my_lord_etiquette(argument, turn_number)
        citation = self.check_scc_citation(argument)
        interruption = self.check_judicial_interruption(argument)
        proportionality = self.check_proportionality_test(argument, problem_context)
        landmark = self.check_landmark_case_nudge(argument, problem_context)
        
        # Generate enhanced prompt
        enhanced_prompt = self.generate_behavior_enforcement_prompt(
            argument, problem_context, turn_number
        )
        
        # Calculate total deductions
        total_deductions = etiquette["points_deducted"]
        
        # Build behavior summary for UI
        violations = []
        if not etiquette["has_etiquette"]:
            violations.append("etiquette")
        if citation["wrong_format_cases"] or not citation["valid_citation"]:
            violations.append("citation")
        if interruption["should_interrupt"]:
            violations.append("interruption")
        if proportionality["needs_proportionality"] and not proportionality["addressed"]:
            violations.append("proportionality")
        if landmark["missing_cases"]:
            violations.append("landmark")
        
        behavior_summary = ", ".join(violations) if violations else "all_correct"
        
        return {
            "etiquette_check": etiquette,
            "citation_check": citation,
            "interruption_check": interruption,
            "proportionality_check": proportionality,
            "landmark_check": landmark,
            "enhanced_prompt": enhanced_prompt,
            "total_deductions": total_deductions,
            "behavior_summary": behavior_summary
        }
