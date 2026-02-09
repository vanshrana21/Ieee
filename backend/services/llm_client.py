"""
backend/services/llm_client.py
Phase 3: LLM Client for AI Judge

Handles real LLM calls to OpenRouter (Claude 3.5 Sonnet) or Groq (Llama 3.1 70B).
Includes timeout, retry logic, and cost tracking.
"""
import os
import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Cost constants
MAX_TOKENS_PER_SESSION = 1000  # 3 turns × ~300 tokens
COST_PER_MILLION_TOKENS = 0.70  # OpenRouter Claude 3.5 Sonnet rate


class LLMClient:
    """
    LLM client for AI Judge with fallback support.
    
    Supports:
    - OpenRouter API (Claude 3.5 Sonnet) - preferred
    - Groq API (Llama 3.1 70B) - fallback
    """
    
    def __init__(self):
        """Initialize LLM client and load API keys from environment."""
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")
        self.groq_key = os.getenv("GROQ_API_KEY")
        self.total_tokens_used = 0  # Track for cost monitoring
        
    def is_configured(self) -> bool:
        """Check if at least one API key is configured."""
        return bool(self.openrouter_key) or bool(self.groq_key)
    
    def generate_judge_response(self, prompt: str, max_tokens: int = 300) -> Optional[str]:
        """
        Generate judge response from LLM.
        
        Args:
            prompt: The formatted prompt for the judge
            max_tokens: Maximum tokens to generate (default 300)
        
        Returns:
            LLM response text, or None if API fails/fallback needed
        """
        if not self.is_configured():
            logger.info("No LLM API key configured - will use mock feedback")
            return None
        
        # Try OpenRouter first (Claude 3.5 Sonnet)
        if self.openrouter_key:
            result = self._call_openrouter(prompt, max_tokens)
            if result:
                return result
        
        # Fallback to Groq
        if self.groq_key:
            result = self._call_groq(prompt, max_tokens)
            if result:
                return result
        
        # Both failed - return None to trigger mock fallback
        logger.warning("All LLM calls failed - falling back to mock feedback")
        return None
    
    def _call_openrouter(self, prompt: str, max_tokens: int) -> Optional[str]:
        """
        Call OpenRouter API with Claude 3.5 Sonnet.
        
        Timeout: 10 seconds
        Retry: max 2 attempts
        """
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://ieee-moot-court.app",  # Required by OpenRouter
            "X-Title": "IEEE Moot Court AI Judge"
        }
        payload = {
            "model": "anthropic/claude-3.5-sonnet",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.7  # Consistent but creative
        }
        
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=10  # 10 second timeout
                )
                response.raise_for_status()
                data = response.json()
                
                # Track tokens used
                tokens_used = data.get("usage", {}).get("total_tokens", 0)
                self.total_tokens_used += tokens_used
                logger.info(f"OpenRouter call: {tokens_used} tokens (total: {self.total_tokens_used})")
                
                return data["choices"][0]["message"]["content"]
                
            except requests.exceptions.Timeout:
                logger.warning(f"OpenRouter timeout (attempt {attempt + 1}/{max_retries + 1})")
                if attempt < max_retries:
                    time.sleep(1)  # Wait before retry
                    continue
                return None
                
            except requests.exceptions.RequestException as e:
                logger.error(f"OpenRouter API error: {e}")
                if attempt < max_retries:
                    time.sleep(1)
                    continue
                return None
            
            except Exception as e:
                logger.error(f"Unexpected error calling OpenRouter: {e}")
                return None
        
        return None
    
    def _call_groq(self, prompt: str, max_tokens: int) -> Optional[str]:
        """
        Call Groq API with Llama 3.1 70B.
        
        Timeout: 10 seconds
        Retry: max 2 attempts
        """
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.groq_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama-3.1-70b-versatile",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.7
        }
        
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=10
                )
                response.raise_for_status()
                data = response.json()
                
                # Track tokens used
                tokens_used = data.get("usage", {}).get("total_tokens", 0)
                self.total_tokens_used += tokens_used
                logger.info(f"Groq call: {tokens_used} tokens (total: {self.total_tokens_used})")
                
                return data["choices"][0]["message"]["content"]
                
            except requests.exceptions.Timeout:
                logger.warning(f"Groq timeout (attempt {attempt + 1}/{max_retries + 1})")
                if attempt < max_retries:
                    time.sleep(1)
                    continue
                return None
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Groq API error: {e}")
                if attempt < max_retries:
                    time.sleep(1)
                    continue
                return None
            
            except Exception as e:
                logger.error(f"Unexpected error calling Groq: {e}")
                return None
        
        return None
    
    def get_cost_estimate(self) -> dict:
        """Get cost estimate based on tokens used."""
        cost = (self.total_tokens_used / 1_000_000) * COST_PER_MILLION_TOKENS
        return {
            "total_tokens": self.total_tokens_used,
            "estimated_cost_usd": round(cost, 4),
            "max_tokens_per_session": MAX_TOKENS_PER_SESSION
        }
