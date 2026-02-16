"""
LLM Adapter for AI Judge Engine — Phase 4

Abstracts LLM calls with retry logic, timeout handling, and metrics.
Supports multiple providers (Gemini, Groq, etc.)
"""
import asyncio
import logging
import time
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass

import google.generativeai as genai
from groq import AsyncGroq

from backend.config.feature_flags import feature_flags

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Standardized LLM response."""
    raw_text: str
    model: str
    model_version: Optional[str]
    latency_ms: int
    token_usage_input: Optional[int]
    token_usage_output: Optional[int]
    success: bool
    error: Optional[str] = None


class LLMError(Exception):
    """LLM call failed."""
    def __init__(self, message: str, retryable: bool = False):
        self.message = message
        self.retryable = retryable
        super().__init__(message)


class LLMTimeoutError(LLMError):
    """LLM call timed out."""
    def __init__(self, timeout_seconds: float):
        super().__init__(f"LLM timeout after {timeout_seconds}s", retryable=True)
        self.timeout_seconds = timeout_seconds


class LLMMalformedError(LLMError):
    """LLM returned malformed output."""
    def __init__(self, message: str):
        super().__init__(message, retryable=False)


class LLMAdapter:
    """
    Adapter for LLM calls with unified interface.
    
    Supports:
    - Gemini (Google)
    - Groq (Llama, Mixtral, etc.)
    - Extensible for more providers
    """
    
    def __init__(self):
        self.gemini_model = None
        self.groq_client = None
        self._init_gemini()
        self._init_groq()
    
    def _init_gemini(self):
        """Initialize Gemini client."""
        import os
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
            self.gemini_model = genai.GenerativeModel('gemini-1.5-pro')
            logger.info("✓ Gemini LLM adapter initialized")
        else:
            logger.warning("⚠️ GEMINI_API_KEY not set, Gemini unavailable")
    
    def _init_groq(self):
        """Initialize Groq client."""
        import os
        api_key = os.getenv("GROQ_API_KEY")
        if api_key:
            self.groq_client = AsyncGroq(api_key=api_key)
            logger.info("✓ Groq LLM adapter initialized")
        else:
            logger.warning("⚠️ GROQ_API_KEY not set, Groq unavailable")
    
    async def call(
        self,
        prompt: str,
        model: str = "gemini-1.5-pro",
        max_tokens: int = 2000,
        temperature: float = 0.1,
        timeout_seconds: float = 30.0
    ) -> LLMResponse:
        """
        Call LLM with unified interface.
        
        Args:
            prompt: The prompt to send
            model: Model identifier (gemini-1.5-pro, llama-3.1-70b, etc.)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            timeout_seconds: Call timeout
            
        Returns:
            LLMResponse with raw text and metadata
        """
        start_time = time.time()
        
        try:
            if model.startswith("gemini"):
                return await self._call_gemini(prompt, model, max_tokens, temperature, timeout_seconds)
            elif model.startswith("llama") or model.startswith("mixtral") or model.startswith("gemma"):
                return await self._call_groq(prompt, model, max_tokens, temperature, timeout_seconds)
            else:
                # Default to Gemini
                return await self._call_gemini(prompt, "gemini-1.5-pro", max_tokens, temperature, timeout_seconds)
                
        except asyncio.TimeoutError:
            latency = int((time.time() - start_time) * 1000)
            logger.warning(f"LLM timeout after {timeout_seconds}s")
            return LLMResponse(
                raw_text="",
                model=model,
                model_version=None,
                latency_ms=latency,
                token_usage_input=None,
                token_usage_output=None,
                success=False,
                error=f"Timeout after {timeout_seconds}s"
            )
        except Exception as e:
            latency = int((time.time() - start_time) * 1000)
            logger.error(f"LLM call failed: {e}")
            return LLMResponse(
                raw_text="",
                model=model,
                model_version=None,
                latency_ms=latency,
                token_usage_input=None,
                token_usage_output=None,
                success=False,
                error=str(e)
            )
    
    async def _call_gemini(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
        timeout_seconds: float
    ) -> LLMResponse:
        """Call Gemini API."""
        if not self.gemini_model:
            raise LLMError("Gemini not initialized (GEMINI_API_KEY missing)")
        
        start_time = time.time()
        
        # Configure generation
        generation_config = genai.types.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
            response_mime_type="application/json"
        )
        
        # Call with timeout
        try:
            response = await asyncio.wait_for(
                self.gemini_model.generate_content_async(
                    prompt,
                    generation_config=generation_config
                ),
                timeout=timeout_seconds
            )
            
            latency = int((time.time() - start_time) * 1000)
            
            # Extract text
            raw_text = response.text if hasattr(response, 'text') else str(response)
            
            # Try to get token usage (Gemini may not always provide this)
            token_input = None
            token_output = None
            if hasattr(response, 'usage_metadata'):
                token_input = response.usage_metadata.prompt_token_count
                token_output = response.usage_metadata.candidates_token_count
            
            return LLMResponse(
                raw_text=raw_text,
                model=model,
                model_version="2024-02",  # Gemini version tracking
                latency_ms=latency,
                token_usage_input=token_input,
                token_usage_output=token_output,
                success=True
            )
            
        except asyncio.TimeoutError:
            raise LLMTimeoutError(timeout_seconds)
    
    async def _call_groq(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
        timeout_seconds: float
    ) -> LLMResponse:
        """Call Groq API."""
        if not self.groq_client:
            raise LLMError("Groq not initialized (GROQ_API_KEY missing)")
        
        start_time = time.time()
        
        # Map model names to Groq model IDs
        model_mapping = {
            "llama-3.1-70b": "llama-3.1-70b-versatile",
            "llama-3.1-8b": "llama-3.1-8b-instant",
            "mixtral-8x7b": "mixtral-8x7b-32768",
            "gemma-2-9b": "gemma2-9b-it"
        }
        
        groq_model = model_mapping.get(model, model)
        
        try:
            chat_completion = await asyncio.wait_for(
                self.groq_client.chat.completions.create(
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an expert moot court judge. Respond only with valid JSON."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    model=groq_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"}
                ),
                timeout=timeout_seconds
            )
            
            latency = int((time.time() - start_time) * 1000)
            
            raw_text = chat_completion.choices[0].message.content
            
            return LLMResponse(
                raw_text=raw_text,
                model=model,
                model_version=groq_model,
                latency_ms=latency,
                token_usage_input=chat_completion.usage.prompt_tokens if chat_completion.usage else None,
                token_usage_output=chat_completion.usage.completion_tokens if chat_completion.usage else None,
                success=True
            )
            
        except asyncio.TimeoutError:
            raise LLMTimeoutError(timeout_seconds)


# Singleton instance
_llm_adapter: Optional[LLMAdapter] = None


def get_llm_adapter() -> LLMAdapter:
    """Get or create LLM adapter singleton."""
    global _llm_adapter
    if _llm_adapter is None:
        _llm_adapter = LLMAdapter()
    return _llm_adapter


async def call_llm_with_retry(
    prompt: str,
    model: str = "gemini-1.5-pro",
    max_retries: int = 2,
    backoff_ms: List[int] = None,
    timeout_seconds: float = 30.0
) -> Tuple[LLMResponse, int]:
    """
    Call LLM with automatic retry on failure.
    
    Args:
        prompt: The prompt
        model: Model to use
        max_retries: Number of retries (total attempts = max_retries + 1)
        backoff_ms: Backoff delays in milliseconds
        timeout_seconds: Timeout per attempt
        
    Returns:
        Tuple of (LLMResponse, attempt_number)
    """
    if backoff_ms is None:
        backoff_ms = [1000, 2000]  # 1s, 2s
    
    adapter = get_llm_adapter()
    last_error = None
    
    for attempt in range(max_retries + 1):
        try:
            response = await adapter.call(
                prompt=prompt,
                model=model,
                timeout_seconds=timeout_seconds
            )
            
            if response.success:
                return response, attempt + 1
            
            # Check if retryable
            if "timeout" in response.error.lower():
                last_error = response.error
                if attempt < max_retries:
                    delay = backoff_ms[min(attempt, len(backoff_ms) - 1)] / 1000
                    logger.warning(f"Attempt {attempt + 1} failed: {response.error}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                continue
            else:
                # Non-retryable error
                return response, attempt + 1
                
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries:
                delay = backoff_ms[min(attempt, len(backoff_ms) - 1)] / 1000
                logger.warning(f"Attempt {attempt + 1} exception: {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
            continue
    
    # All retries exhausted
    return LLMResponse(
        raw_text="",
        model=model,
        model_version=None,
        latency_ms=0,
        token_usage_input=None,
        token_usage_output=None,
        success=False,
        error=f"All {max_retries + 1} attempts failed. Last error: {last_error}"
    ), max_retries + 1
