from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.orm.memorial import MemorialSubmission, MemorialStatus
from backend.orm.team import Team
from backend.services.ai_judge_service import AIJudgeService
from datetime import datetime, timezone
import os
import pdfplumber

async def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from PDF using pdfplumber with safety limits"""
    try:
        with pdfplumber.open(file_path) as pdf:
            # Limit to first 50 pages (prevent DoS with 1000-page PDFs)
            pages_to_read = min(len(pdf.pages), 50)
            text = ""
            for i in range(pages_to_read):
                page_text = pdf.pages[i].extract_text()
                if page_text:
                    text += page_text + "\n"
            # Limit to 10k chars (AI token limits)
            return text[:10000]
    except Exception as e:
        raise ValueError(f"Failed to parse PDF: {str(e)}")

async def analyze_memorial_background(memorial_id: int, db: AsyncSession):
    try:
        result = await db.execute(
            select(MemorialSubmission).where(MemorialSubmission.id == memorial_id)
        )
        memorial = result.scalar_one_or_none()
        if not memorial:
            return
        
        if not os.path.exists(memorial.file_path):
            memorial.status = MemorialStatus.REJECTED
            memorial.ai_feedback = "File not found"
            await db.commit()
            return
        
        # Extract text using pdfplumber
        try:
            content = await extract_text_from_pdf(memorial.file_path)
        except ValueError as e:
            memorial.status = MemorialStatus.REJECTED
            memorial.ai_feedback = str(e)
            await db.commit()
            return
        
        if not content or len(content.strip()) < 100:
            memorial.status = MemorialStatus.REJECTED
            memorial.ai_feedback = "Could not extract readable text from PDF. Please ensure the PDF contains selectable text (not scanned images only)."
            await db.commit()
            return
        
        team_result = await db.execute(select(Team).where(Team.id == memorial.team_id))
        team = team_result.scalar_one_or_none()
        side = team.side if team else "petitioner"
        
        ai_judge = AIJudgeService()
        analysis = ai_judge.analyze_argument(content, side)
        
        scores = analysis.get("scores", analysis.get("score_breakdown", {}))
        irac_score = scores.get("legal_accuracy", 3)
        citation_score = scores.get("citation", 3)
        structure_score = scores.get("etiquette", 3)
        overall = (irac_score + citation_score + structure_score) / 3.0
        
        badges = []
        behavior = analysis.get("behavior_data", {})
        if behavior.get("has_my_lord"):
            badges.append("Etiquette_Master")
        if behavior.get("valid_scc_citation"):
            badges.append("SCC_Format_Expert")
        if not behavior.get("needs_proportionality", True):
            badges.append("Proportionality_Pro")
        
        memorial.status = MemorialStatus.ACCEPTED
        memorial.ai_feedback = analysis.get("feedback", "Analysis complete")[:1000]
        memorial.score_irac = min(5, max(1, int(irac_score)))
        memorial.score_citation = min(5, max(1, int(citation_score)))
        memorial.score_structure = min(5, max(1, int(structure_score)))
        memorial.score_overall = round(overall, 2)
        memorial.badges_earned = ",".join(badges) if badges else None
        memorial.processed_at = datetime.now(timezone.utc)
        
        await db.commit()
        
    except Exception as e:
        if memorial:
            memorial.status = MemorialStatus.REJECTED
            memorial.ai_feedback = f"Analysis failed: {str(e)[:500]}"
            await db.commit()
