"""
Phase 4: Memorial Analysis Service

Extracts text from PDF and performs AI analysis with India-specific legal feedback.
"""
import os
import re
import json
from typing import List, Dict, Tuple, Optional
from datetime import datetime


class MemorialAnalysisService:
    """
    Service for extracting text from memorial PDFs and performing AI analysis.
    """
    
    # India-specific legal terms and case patterns
    SCC_PATTERN = r'\(\d{4}\)\s*\d+\s*SCC\s*\d+'
    AIR_PATTERN = r'AIR\s*\d{4}\s*(SC|All|Bom|Cal|Del|Mad)?\s*\d+'
    
    # Key Indian legal doctrines to check
    KEY_DOCTRINES = {
        "proportionality": [
            "proportionality test",
            "Puttaswamy",
            "para 184",
            "legitimate aim",
            "suitability",
            "necessity",
            "balancing"
        ],
        "basic_structure": [
            "basic structure",
            "Kesavananda",
            "unchangeable",
            "constitutional identity"
        ],
        "article_21": [
            "Article 21",
            "right to life",
            "personal liberty",
            "due process"
        ],
        "irac": [
            "issue",
            "rule",
            "application",
            "conclusion"
        ]
    }
    
    # Key cases for moot problems
    KEY_CASES = {
        "Puttaswamy": ["Puttaswamy", "privacy", "Article 21", "2017"],
        "Maneka": ["Maneka", "Gandhi", "procedure established by law", "1978"],
        "Kesavananda": ["Kesavananda", "basic structure", "1973"],
        "Navtej": ["Navtej", "Singh", "dignity", "2018"],
        "ADM Jabalpur": ["ADM Jabalpur", "habeas corpus", "emergency"]
    }
    
    @staticmethod
    def extract_text_and_pages(file_path: str) -> Tuple[str, int]:
        """
        Extract text from PDF and count pages.
        
        Args:
            file_path: Path to PDF file
        
        Returns:
            Tuple of (extracted_text, page_count)
        """
        try:
            import pdfplumber
            
            text_parts = []
            page_count = 0
            
            with pdfplumber.open(file_path) as pdf:
                page_count = len(pdf.pages)
                
                # Extract text from first 50 pages only
                for i, page in enumerate(pdf.pages[:50]):
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            
            full_text = "\n\n".join(text_parts)
            return full_text, page_count
            
        except ImportError:
            raise RuntimeError("pdfplumber not installed. Install with: pip install pdfplumber")
        except Exception as e:
            raise RuntimeError(f"PDF extraction failed: {str(e)}")
    
    @staticmethod
    def check_citations(text: str) -> Dict:
        """
        Check SCC and AIR citation format in the text.
        
        Args:
            text: Extracted text from PDF
        
        Returns:
            Dictionary with citation analysis results
        """
        scc_matches = re.findall(MemorialAnalysisService.SCC_PATTERN, text)
        air_matches = re.findall(MemorialAnalysisService.AIR_PATTERN, text, re.IGNORECASE)
        
        # Check for improper formats
        improper_patterns = [
            r'\(\d{4}\)\s*SCC',  # Missing volume
            r'SCC\s*\d+\s*\(\d{4}\)',  # Wrong order
        ]
        
        improper_citations = []
        for pattern in improper_patterns:
            improper_citations.extend(re.findall(pattern, text))
        
        return {
            "scc_count": len(scc_matches),
            "air_count": len(air_matches),
            "improper_count": len(improper_citations),
            "proper_format_ratio": len(scc_matches) / (len(scc_matches) + len(improper_citations) + 0.01),
            "sample_citations": scc_matches[:5] if scc_matches else []
        }
    
    @staticmethod
    def check_irac_structure(text: str) -> Dict:
        """
        Check for IRAC structure in the text.
        
        Args:
            text: Extracted text from PDF
        
        Returns:
            Dictionary with IRAC analysis results
        """
        text_lower = text.lower()
        
        # Check for IRAC components
        has_issue = bool(re.search(r'\b(issue|issues|question|questions)\b', text_lower))
        has_rule = bool(re.search(r'\b(rule|law|statute|act|article|section)\b', text_lower))
        has_application = bool(re.search(r'\b(application|apply|applied|analysis|argue)\b', text_lower))
        has_conclusion = bool(re.search(r'\b(conclusion|conclude|therefore|thus|hence)\b', text_lower))
        
        # Count IRAC sections
        issue_keywords = len(re.findall(r'\bissue\b', text_lower))
        rule_keywords = len(re.findall(r'\b(rule|rules)\b', text_lower))
        
        components_present = sum([has_issue, has_rule, has_application, has_conclusion])
        
        return {
            "has_issue": has_issue,
            "has_rule": has_rule,
            "has_application": has_application,
            "has_conclusion": has_conclusion,
            "components_present": components_present,
            "irac_completeness": components_present / 4.0,
            "issue_count": issue_keywords,
            "rule_references": rule_keywords
        }
    
    @staticmethod
    def detect_cases(text: str) -> List[Dict]:
        """
        Detect key case citations in the text.
        
        Args:
            text: Extracted text from PDF
        
        Returns:
            List of detected cases with context
        """
        detected = []
        text_lower = text.lower()
        
        for case_name, keywords in MemorialAnalysisService.KEY_CASES.items():
            # Check if any keyword is present
            found = any(keyword.lower() in text_lower for keyword in keywords)
            
            if found:
                # Count occurrences
                count = sum(text_lower.count(keyword.lower()) for keyword in keywords[:2])
                
                # Find context (first occurrence)
                context = ""
                for keyword in keywords[:2]:
                    idx = text_lower.find(keyword.lower())
                    if idx != -1:
                        start = max(0, idx - 100)
                        end = min(len(text), idx + 100)
                        context = text[start:end].strip()
                        break
                
                detected.append({
                    "name": case_name,
                    "found": True,
                    "count": count,
                    "context": context[:200],
                    "keywords_found": [k for k in keywords if k.lower() in text_lower][:3]
                })
        
        return detected
    
    @staticmethod
    def check_doctrines(text: str) -> List[Dict]:
        """
        Check for key legal doctrines in the text.
        
        Args:
            text: Extracted text from PDF
        
        Returns:
            List of doctrine analysis results
        """
        text_lower = text.lower()
        results = []
        
        for doctrine, keywords in MemorialAnalysisService.KEY_DOCTRINES.items():
            found_keywords = [k for k in keywords if k.lower() in text_lower]
            found_count = len(found_keywords)
            
            # Determine status
            if found_count >= 2:
                status = "present"
            elif found_count == 1:
                status = "mentioned"
            else:
                status = "missing"
            
            results.append({
                "doctrine": doctrine,
                "status": status,
                "keywords_found": found_keywords,
                "count": found_count
            })
        
        return results
    
    @staticmethod
    def generate_ai_prompt(text: str, team_side: str, page_count: int) -> str:
        """
        Generate AI prompt for memorial analysis.
        
        Args:
            text: Extracted memorial text
            team_side: 'petitioner' or 'respondent'
            page_count: Number of pages in PDF
        
        Returns:
            Formatted AI prompt string
        """
        # Truncate text if too long
        max_chars = 8000
        truncated_text = text[:max_chars] if len(text) > max_chars else text
        
        prompt = f"""You are an Indian Supreme Court judge evaluating a moot court memorial.

MEMORIAL DETAILS:
- Team Side: {team_side.upper()}
- Page Count: {page_count}

MEMORIAL TEXT:
{truncated_text}

EVALUATION CRITERIA (Score 1-5 for each):
1. IRAC STRUCTURE: Does the memorial follow Issue-Rule-Application-Conclusion format? Are issues clearly identified? (1=Poor, 5=Perfect)

2. SCC CITATION FORMAT: Are citations in correct SCC format (YEAR) VOLUME SCC PAGE? Are AIR citations properly formatted? (1=Many errors, 5=Perfect)

3. LEGAL REASONING: Is the legal analysis sound? Are precedents properly applied? Is argumentation logical? (1=Weak, 5=Exceptional)

Provide specific feedback on:
- Strengths (3-5 points)
- Areas for improvement (3-5 specific suggestions)
- Missing doctrines (proportionality, basic structure, etc.)
- Case citation issues

Return response in this JSON format:
{{
  "scores": {{
    "irac_structure": 1-5,
    "citation_format": 1-5,
    "legal_reasoning": 1-5,
    "overall": average of three scores (1 decimal)
  }},
  "feedback": {{
    "strengths": ["point 1", "point 2", "point 3"],
    "improvements": ["suggestion 1", "suggestion 2", "suggestion 3"],
    "missing_doctrines": ["doctrine 1", "doctrine 2"]
  }}
}}"""
        
        return prompt
    
    @staticmethod
    def analyze_memorial(file_path: str, team_side: str, moot_problem: Optional[Dict] = None) -> Dict:
        """
        Complete memorial analysis pipeline.
        
        Args:
            file_path: Path to PDF file
            team_side: 'petitioner' or 'respondent'
            moot_problem: Optional moot problem context
        
        Returns:
            Complete analysis results
        """
        # Step 1: Extract text
        text, page_count = MemorialAnalysisService.extract_text_and_pages(file_path)
        
        # Step 2: Run analysis checks
        citation_analysis = MemorialAnalysisService.check_citations(text)
        irac_analysis = MemorialAnalysisService.check_irac_structure(text)
        detected_cases = MemorialAnalysisService.detect_cases(text)
        doctrine_analysis = MemorialAnalysisService.check_doctrines(text)
        
        # Step 3: Calculate scores based on analysis
        citation_score = min(5, max(1, int(citation_analysis["proper_format_ratio"] * 5)))
        irac_score = min(5, max(1, int(irac_analysis["irac_completeness"] * 5) + 1))
        
        # Reasoning score based on case detection and doctrine coverage
        cases_score = len(detected_cases) / len(MemorialAnalysisService.KEY_CASES)
        doctrines_present = sum(1 for d in doctrine_analysis if d["status"] == "present")
        reasoning_score = min(5, max(1, int((cases_score + doctrines_present/4) * 2.5) + 1))
        
        overall = round((citation_score + irac_score + reasoning_score) / 3, 1)
        
        # Step 4: Generate feedback
        strengths = []
        improvements = []
        missing_doctrines = []
        
        # Citation feedback
        if citation_score >= 4:
            strengths.append("Proper SCC citation format throughout")
        else:
            improvements.append("Correct SCC citation format to (YEAR) VOLUME SCC PAGE")
        
        # IRAC feedback
        if irac_score >= 4:
            strengths.append("Clear IRAC structure with well-defined issues")
        else:
            missing_components = []
            if not irac_analysis["has_issue"]:
                missing_components.append("issue identification")
            if not irac_analysis["has_rule"]:
                missing_components.append("rule statement")
            if not irac_analysis["has_application"]:
                missing_components.append("application")
            if not irac_analysis["has_conclusion"]:
                missing_components.append("conclusion")
            if missing_components:
                improvements.append(f"Add missing IRAC components: {', '.join(missing_components)}")
        
        # Case detection feedback
        if detected_cases:
            case_names = [c["name"] for c in detected_cases[:3]]
            strengths.append(f"Good use of precedents: {', '.join(case_names)}")
        
        # Doctrine feedback
        for doctrine in doctrine_analysis:
            if doctrine["status"] == "missing":
                missing_doctrines.append(doctrine["doctrine"])
                if doctrine["doctrine"] == "proportionality":
                    improvements.append("Apply Puttaswamy proportionality test (para 184) for Article 21 challenges")
                elif doctrine["doctrine"] == "basic_structure":
                    improvements.append("Include Kesavananda basic structure doctrine for constitutional challenges")
        
        return {
            "scores": {
                "irac_structure": irac_score,
                "citation_format": citation_score,
                "legal_reasoning": reasoning_score,
                "overall": overall,
                "percentage": int(overall / 5 * 100)
            },
            "analysis_details": {
                "citations": citation_analysis,
                "irac": irac_analysis,
                "cases": detected_cases,
                "doctrines": doctrine_analysis,
                "page_count": page_count
            },
            "feedback": {
                "strengths": strengths,
                "improvements": improvements,
                "missing_doctrines": missing_doctrines
            },
            "ai_prompt": MemorialAnalysisService.generate_ai_prompt(text, team_side, page_count)
        }
    
    @staticmethod
    def generate_mock_analysis(file_path: str, team_side: str) -> Dict:
        """
        Generate mock analysis for testing without AI API.
        
        Args:
            file_path: Path to PDF file
            team_side: 'petitioner' or 'respondent'
        
        Returns:
            Mock analysis results
        """
        try:
            text, page_count = MemorialAnalysisService.extract_text_and_pages(file_path)
        except:
            text, page_count = "", 24
        
        return {
            "scores": {
                "irac_structure": 4,
                "citation_format": 5,
                "legal_reasoning": 3,
                "overall": 4.0,
                "percentage": 80
            },
            "analysis_details": {
                "page_count": page_count,
                "citations": {
                    "scc_count": 8,
                    "air_count": 3,
                    "improper_count": 0
                }
            },
            "feedback": {
                "strengths": [
                    "Perfect SCC citation format throughout",
                    "Clear issue identification in IRAC structure",
                    "Strong application of Maneka precedent"
                ],
                "improvements": [
                    "Apply Puttaswamy proportionality test (para 184) to Article 21 arguments",
                    "Include Kesavananda basic structure doctrine for constitutional challenges",
                    "Trim verbose sections - focus on 3-4 strongest precedents"
                ],
                "missing_doctrines": ["proportionality", "detailed basic structure analysis"]
            },
            "mock": True
        }
