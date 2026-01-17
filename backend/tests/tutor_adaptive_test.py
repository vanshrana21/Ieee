import unittest
import asyncio
import json
import hashlib
from unittest.mock import MagicMock, AsyncMock, patch
from backend.services.tutor_adaptive import determine_depth, build_adaptive_prompt, process_adaptive_chat

class TestTutorAdaptive(unittest.TestCase):

    def setUp(self):
        self.mock_context = {
            "student": {"course": "BA LLB", "semester": 3},
            "active_subjects": [{"id": 1, "title": "Constitutional Law"}],
            "weak_topics": [{"topic_tag": "article-21", "mastery_percent": 30.0}],
            "strong_topics": [{"topic_tag": "judicial-review", "mastery_percent": 85.0}],
            "recent_activity": {"last_practice_days_ago": 2, "last_subject": "Constitutional Law"}
        }
        self.user_id = 1
        self.db = AsyncMock()
        
        # Configure DB mock to return empty list of masteries by default
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        self.db.execute.return_value = mock_result

    def test_determine_depth_scaffolded(self):
        # mastery 30% < 50% -> scaffolded
        loop = asyncio.get_event_loop()
        depth = loop.run_until_complete(determine_depth(self.user_id, "Explain article 21", self.mock_context, self.db))
        self.assertEqual(depth, "scaffolded")

    def test_determine_depth_concise(self):
        # mastery 85% >= 75% -> concise
        loop = asyncio.get_event_loop()
        depth = loop.run_until_complete(determine_depth(self.user_id, "What is judicial review?", self.mock_context, self.db))
        self.assertEqual(depth, "concise")

    def test_determine_depth_default(self):
        # No match in context, check DB fallback (mocked as empty)
        loop = asyncio.get_event_loop()
        depth = loop.run_until_complete(determine_depth(self.user_id, "Unknown topic", self.mock_context, self.db))
        self.assertEqual(depth, "standard")

    def test_deterministic_prompt(self):
        # same inputs => same prompt
        p1 = build_adaptive_prompt("Question", self.mock_context, "scaffolded")
        p2 = build_adaptive_prompt("Question", self.mock_context, "scaffolded")
        self.assertEqual(p1, p2)
        
        h1 = hashlib.sha256(p1.encode()).hexdigest()
        h2 = hashlib.sha256(p2.encode()).hexdigest()
        self.assertEqual(h1, h2)

    @patch("backend.services.tutor_adaptive.assemble_context")
    @patch("backend.services.tutor_adaptive.call_gemini_deterministic")
    def test_remediation_pack(self, mock_call_ai, mock_assemble):
        mock_assemble.return_value = self.mock_context
        
        # Mock AI response for remediation (scaffolded)
        ai_response = {
            "answer": "Explanation of article 21",
            "depth": "scaffolded",
            "mini_lesson": ["Step 1", "Step 2", "Step 3"],
            "worked_examples": [{"title": "Example 1"}, {"title": "Example 2"}],
            "study_actions": [{"type": "practice", "module_id": 123}],
            "why_this_help": "Low mastery detected",
            "provenance": [],
            "confidence_score": 0.9,
            "linked_topics": ["article-21"]
        }
        
        mock_call_ai.return_value = {
            "success": True,
            "text": json.dumps(ai_response),
            "prompt_hash": "abc",
            "response_hash": "xyz",
            "latency": 0.5,
            "model": "gemini-1.5-flash"
        }
        
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(process_adaptive_chat(self.user_id, "Explain article 21", "adaptive", self.db))
        
        self.assertEqual(result["depth"], "scaffolded")
        self.assertEqual(len(result["mini_lesson"]), 3)
        self.assertEqual(len(result["worked_examples"]), 2)

    @patch("backend.services.tutor_adaptive.assemble_context")
    @patch("backend.services.tutor_adaptive.call_gemini_deterministic")
    def test_refusal_logic(self, mock_call_ai, mock_assemble):
        # The AI is responsible for refusal based on the prompt instructions
        mock_assemble.return_value = self.mock_context
        
        refusal_response = {
            "answer": "I couldn't find that in your syllabus. You might be interested in Judicial Review or Article 21.",
            "depth": "concise",
            "study_actions": [],
            "why_this_help": "Outside syllabus",
            "provenance": [],
            "confidence_score": 1.0,
            "linked_topics": []
        }
        
        mock_call_ai.return_value = {
            "success": True,
            "text": json.dumps(refusal_response),
            "prompt_hash": "abc",
            "response_hash": "xyz",
            "latency": 0.5,
            "model": "gemini-1.5-flash"
        }
        
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(process_adaptive_chat(self.user_id, "Quantum Physics", "adaptive", self.db))
        
        self.assertIn("couldn't find that in your syllabus", result["answer"])

if __name__ == "__main__":
    unittest.main()
