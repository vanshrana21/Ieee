import os
import logging
from typing import Dict, Any
import google.generativeai as genai

logger = logging.getLogger(__name__)

# Read API key at module level (after main.py has loaded .env)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY environment variable not set")
    logger.error("Make sure .env file exists and contains GEMINI_API_KEY")
    raise EnvironmentError(
        "GEMINI_API_KEY environment variable not set. "
        "Check that .env file exists in project root with valid GEMINI_API_KEY."
    )

# Configure Gemini with API key
genai.configure(api_key=GEMINI_API_KEY)

# Initialize model
model = genai.GenerativeModel("gemini-1.5-flash")

logger.info("Gemini API configured successfully")


async def run_verified_legal_query(query: str) -> dict:
    """
    Execute two-step verified legal query using Gemini.
    
    Step 1: Generate legal answer
    Step 2: Verify the answer
    
    Args:
        query: Legal research question
        
    Returns:
        dict with keys: success, query, generated_answer, verification, model
    """
    try:
        # Step 1: Generate legal answer
        generation_prompt = f"""You are a legal research assistant specializing in Indian law.

User Query: {query}

Provide a comprehensive legal answer that includes:
1. Direct answer to the query
2. Relevant legal provisions or case laws
3. Jurisdiction-specific considerations
4. Practical implications

Keep the response professional, accurate, and cite sources where applicable."""

        logger.info(f"Generating legal answer for query: {query[:100]}...")
        
        generation_response = await model.generate_content_async(generation_prompt)
        generated_answer = generation_response.text

        logger.info("Legal answer generated successfully")

        # Step 2: Verify the generated answer
        verification_prompt = f"""You are a legal verification assistant. Review the following legal answer for accuracy, completeness, and potential issues.

Original Query: {query}

Generated Answer:
{generated_answer}

Verify:
1. Legal accuracy
2. Citation correctness
3. Relevance to the query
4. Completeness of information
5. Any potential misleading statements

Provide a verification report with:
- Overall confidence score (0-100)
- Identified issues (if any)
- Suggestions for improvement (if any)
- Final assessment (APPROVED/NEEDS_REVIEW/REJECTED)"""

        logger.info("Verifying generated answer...")
        
        verification_response = await model.generate_content_async(verification_prompt)
        verification_result = verification_response.text

        logger.info("Verification completed successfully")

        return {
            "success": True,
            "query": query,
            "generated_answer": generated_answer,
            "verification": verification_result,
            "model": "gemini-1.5-flash"
        }

    except Exception as e:
        logger.error(f"Error in run_verified_legal_query: {str(e)}")
        return {
            "success": False,
            "query": query,
            "error": str(e),
            "generated_answer": None,
            "verification": None
        }