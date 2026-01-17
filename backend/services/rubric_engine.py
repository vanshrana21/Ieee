"""
backend/services/rubric_engine.py
Phase 5.1: Deterministic Evaluation Rubric Engine

Generates IRAC-aligned marking rubrics for Indian law exam answers.
Supports 5/10/15 mark questions across essay, case_analysis, and short_answer types.

Rubric Allocation Logic:
-------------------------
The IRAC framework (Issue, Rule, Application, Conclusion) is the standard for legal analysis.
Mark allocation follows exam-realistic patterns used in Indian law universities.

For ESSAY questions:
- Emphasizes comprehensive legal principles and application
- More marks for analysis depth

For CASE_ANALYSIS questions:
- Emphasizes fact identification and application to legal principles
- Balanced focus on issue spotting and legal reasoning

For SHORT_ANSWER questions:
- Compact rubric with fewer components
- Focus on precision and key points
"""

from typing import Dict, List, Any, Literal

QuestionType = Literal["essay", "case_analysis", "short_answer"]
MarkValue = Literal[5, 10, 15]

RUBRIC_TEMPLATES: Dict[int, Dict[str, List[Dict[str, Any]]]] = {
    5: {
        "essay": [
            {"name": "Issue Identification", "marks": 1, "description": "Clear statement of the legal issue"},
            {"name": "Legal Principles", "marks": 2, "description": "Relevant legal rules and provisions"},
            {"name": "Application & Conclusion", "marks": 2, "description": "Application to facts with reasoned conclusion"},
        ],
        "case_analysis": [
            {"name": "Fact Summary", "marks": 1, "description": "Key facts identification"},
            {"name": "Legal Issue", "marks": 1, "description": "Issue identification from facts"},
            {"name": "Rule Application", "marks": 2, "description": "Application of legal principles"},
            {"name": "Conclusion", "marks": 1, "description": "Reasoned conclusion"},
        ],
        "short_answer": [
            {"name": "Definition/Concept", "marks": 2, "description": "Accurate definition or concept explanation"},
            {"name": "Key Points", "marks": 2, "description": "Essential elements or characteristics"},
            {"name": "Legal Authority", "marks": 1, "description": "Relevant section/case reference"},
        ],
    },
    10: {
        "essay": [
            {"name": "Issue Identification", "marks": 2, "description": "Clear identification of legal issues"},
            {"name": "Legal Principles", "marks": 3, "description": "Comprehensive statement of applicable law"},
            {"name": "Application to Facts", "marks": 3, "description": "Logical application with reasoning"},
            {"name": "Conclusion", "marks": 2, "description": "Well-reasoned conclusion"},
        ],
        "case_analysis": [
            {"name": "Fact Identification", "marks": 2, "description": "Material facts extracted accurately"},
            {"name": "Issue Spotting", "marks": 2, "description": "Legal issues identified from facts"},
            {"name": "Legal Principles", "marks": 2, "description": "Relevant rules and precedents"},
            {"name": "Application", "marks": 2, "description": "Application of law to facts"},
            {"name": "Conclusion", "marks": 2, "description": "Logical conclusion with reasoning"},
        ],
        "short_answer": [
            {"name": "Definition", "marks": 2, "description": "Clear and accurate definition"},
            {"name": "Key Elements", "marks": 3, "description": "Essential components explained"},
            {"name": "Legal Provisions", "marks": 3, "description": "Relevant statutory sections"},
            {"name": "Example/Application", "marks": 2, "description": "Practical example or application"},
        ],
    },
    15: {
        "essay": [
            {"name": "Issue Identification", "marks": 2, "description": "Comprehensive issue identification"},
            {"name": "Legal Framework", "marks": 4, "description": "Statutory provisions and precedents", "sub_points": [
                {"name": "Statutory Provisions", "marks": 2},
                {"name": "Case Law", "marks": 2},
            ]},
            {"name": "Application to Facts", "marks": 5, "description": "Detailed analysis and application", "sub_points": [
                {"name": "Analysis of Facts", "marks": 2},
                {"name": "Legal Reasoning", "marks": 3},
            ]},
            {"name": "Counter-Arguments", "marks": 2, "description": "Alternative viewpoints considered"},
            {"name": "Conclusion", "marks": 2, "description": "Balanced conclusion with recommendations"},
        ],
        "case_analysis": [
            {"name": "Fact Summary", "marks": 2, "description": "Comprehensive fact identification"},
            {"name": "Issue Identification", "marks": 2, "description": "All legal issues spotted"},
            {"name": "Legal Principles", "marks": 4, "description": "Applicable laws and precedents", "sub_points": [
                {"name": "Statutory Law", "marks": 2},
                {"name": "Judicial Precedents", "marks": 2},
            ]},
            {"name": "Application", "marks": 4, "description": "Detailed application to facts", "sub_points": [
                {"name": "Primary Analysis", "marks": 2},
                {"name": "Secondary Issues", "marks": 2},
            ]},
            {"name": "Conclusion", "marks": 3, "description": "Reasoned conclusion with practical implications"},
        ],
        "short_answer": [
            {"name": "Definition", "marks": 3, "description": "Comprehensive definition"},
            {"name": "Essential Elements", "marks": 4, "description": "Key components with explanation", "sub_points": [
                {"name": "Primary Elements", "marks": 2},
                {"name": "Secondary Elements", "marks": 2},
            ]},
            {"name": "Legal Provisions", "marks": 4, "description": "Statutory and case law references"},
            {"name": "Application/Examples", "marks": 2, "description": "Practical illustrations"},
            {"name": "Significance", "marks": 2, "description": "Legal importance and implications"},
        ],
    },
}


def generate_rubric(marks: int, question_type: str) -> Dict[str, Any]:
    """
    Generate a deterministic evaluation rubric for a legal answer.
    
    Args:
        marks: Total marks for the question (5, 10, or 15)
        question_type: Type of question (essay, case_analysis, short_answer)
    
    Returns:
        Structured rubric JSON with components that sum to total marks
    
    Raises:
        ValueError: If marks or question_type is invalid
    """
    if marks not in [5, 10, 15]:
        raise ValueError(f"Invalid marks value: {marks}. Must be 5, 10, or 15.")
    
    question_type = question_type.lower().strip()
    if question_type not in ["essay", "case_analysis", "short_answer"]:
        raise ValueError(f"Invalid question_type: {question_type}. Must be essay, case_analysis, or short_answer.")
    
    components = RUBRIC_TEMPLATES[marks][question_type]
    
    rubric = {
        "max_marks": marks,
        "question_type": question_type,
        "framework": "IRAC",
        "components": components,
    }
    
    total = sum(c["marks"] for c in components)
    assert total == marks, f"Rubric marks sum ({total}) does not equal max_marks ({marks})"
    
    return rubric


def get_component_weight(component_name: str, rubric: Dict[str, Any]) -> float:
    """
    Get the weight (percentage) of a component in the rubric.
    
    Args:
        component_name: Name of the component
        rubric: The rubric dictionary
    
    Returns:
        Weight as a float between 0 and 1
    """
    max_marks = rubric["max_marks"]
    for comp in rubric["components"]:
        if comp["name"].lower() == component_name.lower():
            return comp["marks"] / max_marks
    return 0.0


def validate_rubric(rubric: Dict[str, Any]) -> bool:
    """
    Validate that a rubric is well-formed.
    
    Args:
        rubric: The rubric dictionary to validate
    
    Returns:
        True if valid, raises ValueError otherwise
    """
    required_keys = ["max_marks", "question_type", "components"]
    for key in required_keys:
        if key not in rubric:
            raise ValueError(f"Missing required key: {key}")
    
    if not rubric["components"]:
        raise ValueError("Rubric must have at least one component")
    
    total = sum(c["marks"] for c in rubric["components"])
    if total != rubric["max_marks"]:
        raise ValueError(f"Component marks ({total}) do not sum to max_marks ({rubric['max_marks']})")
    
    return True


def rubric_to_prompt_format(rubric: Dict[str, Any]) -> str:
    """
    Convert rubric to a string format suitable for AI prompts.
    Used by Phase 5.2 AI evaluation.
    
    Args:
        rubric: The rubric dictionary
    
    Returns:
        Formatted string representation
    """
    lines = [
        f"MARKING RUBRIC (Total: {rubric['max_marks']} marks)",
        f"Question Type: {rubric['question_type'].replace('_', ' ').title()}",
        f"Framework: {rubric['framework']}",
        "",
        "Components:",
    ]
    
    for i, comp in enumerate(rubric["components"], 1):
        lines.append(f"  {i}. {comp['name']} ({comp['marks']} marks)")
        if "description" in comp:
            lines.append(f"     - {comp['description']}")
        if "sub_points" in comp:
            for sp in comp["sub_points"]:
                lines.append(f"       * {sp['name']} ({sp['marks']} marks)")
    
    return "\n".join(lines)
