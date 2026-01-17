from pydantic import BaseModel, Field
from typing import List, Optional

class TutorChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)

class TutorChatResponse(BaseModel):
    answer: str
    confidence: str
    linked_topics: List[str]
    why_this_answer: str
