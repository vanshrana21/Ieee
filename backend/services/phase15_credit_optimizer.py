"""
Phase 15 — Credit Optimizer Service

Intelligently truncates and optimizes content to fit within
token budget constraints. Maximizes information density.
"""
import re
from typing import Dict, Any, List, Optional


class CreditOptimizerService:
    """
    Optimizes content for AI model consumption within token budget.
    Target: 500 tokens maximum for cost efficiency.
    """

    # Token estimation: ~4 chars per token (rough estimate)
    CHARS_PER_TOKEN = 4
    MAX_TOKENS = 500
    MAX_CHARS = MAX_TOKENS * CHARS_PER_TOKEN  # 2000 chars

    # Filler phrases to remove
    FILLER_PHRASES = [
        "basically", "essentially", "fundamentally", "at the end of the day",
        "when all is said and done", "in my humble opinion", "i think that",
        "i believe that", "it seems to me", "as far as i can tell",
        "to be honest", "to tell you the truth", "frankly speaking",
        "as a matter of fact", "in reality", "actually", "literally",
        "you know", "like", "sort of", "kind of", "more or less",
        "in a sense", "in some ways", "in many respects",
    ]

    # Repetitive legal phrases (keep first occurrence)
    REPETITIVE_PATTERNS = [
        r"respectfully submitted", r"if it please the court",
        r"may it please the court", r"your honor",
    ]

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Estimate token count from character count.
        Rough approximation: 1 token ≈ 4 characters.
        """
        if not text:
            return 0
        return len(text) // CreditOptimizerService.CHARS_PER_TOKEN

    @staticmethod
    def optimize_text(text: str, max_tokens: int = MAX_TOKENS) -> str:
        """
        Optimize text to fit within token budget.

        Steps:
        1. Strip whitespace
        2. Remove filler phrases
        3. Remove repetitive sentences
        4. Truncate if still over budget
        """
        if not text:
            return ""

        max_chars = max_tokens * CreditOptimizerService.CHARS_PER_TOKEN

        # Step 1: Clean whitespace
        text = CreditOptimizerService._clean_whitespace(text)

        # Step 2: Remove filler phrases
        text = CreditOptimizerService._remove_filler_phrases(text)

        # Step 3: Remove repetitive sentences
        text = CreditOptimizerService._remove_repetitive_sentences(text)

        # Step 4: Truncate intelligently if still over budget
        if len(text) > max_chars:
            text = CreditOptimizerService._intelligent_truncate(text, max_chars)

        return text.strip()

    @staticmethod
    def optimize_match_summary(summary: Dict[str, Any], max_tokens: int = MAX_TOKENS) -> Dict[str, Any]:
        """
        Optimize match summary dictionary for AI consumption.
        """
        optimized = {}

        for key, value in summary.items():
            if isinstance(value, str):
                optimized[key] = CreditOptimizerService.optimize_text(value, max_tokens // 4)
            elif isinstance(value, dict):
                optimized[key] = CreditOptimizerService.optimize_match_summary(value, max_tokens // 4)
            elif isinstance(value, list):
                optimized[key] = CreditOptimizerService._optimize_list(value, max_tokens // 4)
            else:
                optimized[key] = value

        return optimized

    @staticmethod
    def _clean_whitespace(text: str) -> str:
        """Remove extra whitespace and normalize."""
        # Replace multiple spaces with single space
        text = re.sub(r'\s+', ' ', text)
        # Remove spaces around punctuation
        text = re.sub(r'\s*([.,;:!?])\s*', r'\1 ', text)
        return text.strip()

    @staticmethod
    def _remove_filler_phrases(text: str) -> str:
        """Remove common filler phrases."""
        text_lower = text.lower()

        for phrase in CreditOptimizerService.FILLER_PHRASES:
            # Case-insensitive removal
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            text = pattern.sub('', text)

        # Clean up extra spaces
        return CreditOptimizerService._clean_whitespace(text)

    @staticmethod
    def _remove_repetitive_sentences(text: str) -> str:
        """Remove repetitive sentence patterns."""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        seen_patterns = set()
        unique_sentences = []

        for sentence in sentences:
            sentence_lower = sentence.lower().strip()

            # Check if this matches a repetitive pattern
            is_duplicate = False
            for pattern in CreditOptimizerService.REPETITIVE_PATTERNS:
                if re.search(pattern, sentence_lower):
                    if pattern in seen_patterns:
                        is_duplicate = True
                    else:
                        seen_patterns.add(pattern)
                    break

            if not is_duplicate:
                unique_sentences.append(sentence)

        return ' '.join(unique_sentences)

    @staticmethod
    def _intelligent_truncate(text: str, max_chars: int) -> str:
        """
        Truncate text intelligently to preserve meaning.
        Tries to end at sentence boundary.
        """
        if len(text) <= max_chars:
            return text

        # Try to find sentence boundary before limit
        truncated = text[:max_chars]

        # Look for last sentence end
        for punct in ['. ', '! ', '? ']:
            last_end = truncated.rfind(punct)
            if last_end > max_chars * 0.7:  # At least 70% of content
                return truncated[:last_end + 1]

        # If no good sentence boundary, just truncate
        return truncated.rstrip() + "..."

    @staticmethod
    def _optimize_list(items: List[Any], max_tokens: int) -> List[Any]:
        """Optimize a list of items."""
        optimized = []
        current_tokens = 0

        for item in items:
            if isinstance(item, str):
                item_tokens = CreditOptimizerService.estimate_tokens(item)
                if current_tokens + item_tokens <= max_tokens:
                    optimized.append(CreditOptimizerService.optimize_text(item, max_tokens // len(items)))
                    current_tokens += item_tokens
                else:
                    break
            else:
                optimized.append(item)

        return optimized

    @staticmethod
    def calculate_summary_length(summary: Dict[str, Any]) -> Dict[str, int]:
        """
        Calculate token usage for each section of summary.
        Returns breakdown for debugging.
        """
        breakdown = {}
        total_chars = 0

        for key, value in summary.items():
            if isinstance(value, str):
                chars = len(value)
                total_chars += chars
                breakdown[key] = {
                    "chars": chars,
                    "estimated_tokens": chars // CreditOptimizerService.CHARS_PER_TOKEN
                }
            elif isinstance(value, dict):
                sub_breakdown = CreditOptimizerService.calculate_summary_length(value)
                breakdown[key] = sub_breakdown
                # Sum nested
                for sub in sub_breakdown.values():
                    if isinstance(sub, dict) and "chars" in sub:
                        total_chars += sub["chars"]

        breakdown["_total"] = {
            "chars": total_chars,
            "estimated_tokens": total_chars // CreditOptimizerService.CHARS_PER_TOKEN,
            "max_tokens": CreditOptimizerService.MAX_TOKENS,
            "over_budget": total_chars > CreditOptimizerService.MAX_CHARS
        }

        return breakdown

    @staticmethod
    def is_within_budget(text: str, max_tokens: int = MAX_TOKENS) -> bool:
        """Check if text is within token budget."""
        return CreditOptimizerService.estimate_tokens(text) <= max_tokens


# Singleton instance
credit_optimizer = CreditOptimizerService()
