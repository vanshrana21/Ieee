"""
backend/services/audio_transcription.py
Speech-to-text service using OpenAI Whisper API with local fallback

Handles:
- Audio chunk processing (10-second segments)
- Whisper API integration with offline fallback
- Speaker role tracking
- Chunk management and cleanup
"""
import os
import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List
from pathlib import Path

import aiohttp
import aiofiles

logger = logging.getLogger(__name__)

# Configuration
CHUNK_DURATION_SECONDS = 10
MAX_CHUNK_SIZE_MB = 5
AUDIO_UPLOAD_DIR = "uploads/audio_chunks"
WHISPER_API_URL = "https://api.openai.com/v1/audio/transcriptions"
WHISPER_MODEL = "whisper-1"

# In-memory chunk storage for processing status
_chunk_status: Dict[str, dict] = {}


class AudioTranscriptionService:
    """
    Service for transcribing audio chunks using Whisper API or local fallback.
    """
    
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.use_api = bool(self.api_key)
        
        # Ensure upload directory exists
        Path(AUDIO_UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
        
        if self.use_api:
            logger.info("AudioTranscription: Using OpenAI Whisper API")
        else:
            logger.warning("AudioTranscription: No API key, will use offline fallback")
    
    async def process_audio_chunk(
        self,
        round_id: int,
        audio_data: bytes,
        speaker_role: str,
        chunk_index: int,
        timestamp: datetime
    ) -> dict:
        """
        Process a single audio chunk through Whisper.
        
        Args:
            round_id: Oral round ID
            audio_data: Raw audio bytes (WebM/Opus format)
            speaker_role: "petitioner", "respondent", or "judge"
            chunk_index: Sequential chunk number
            timestamp: Chunk start time
        
        Returns:
            Dict with chunk_id, status, transcript, confidence, word_timestamps
        """
        chunk_id = str(uuid.uuid4())
        chunk_path = None
        
        try:
            # Validate chunk size
            if len(audio_data) > MAX_CHUNK_SIZE_MB * 1024 * 1024:
                raise ValueError(f"Chunk exceeds {MAX_CHUNK_SIZE_MB}MB limit")
            
            # Create round-specific directory
            round_dir = Path(AUDIO_UPLOAD_DIR) / str(round_id)
            round_dir.mkdir(parents=True, exist_ok=True)
            
            # Save chunk to disk
            chunk_filename = f"{timestamp.strftime('%H%M%S')}_{chunk_index}_{chunk_id}.webm"
            chunk_path = round_dir / chunk_filename
            
            async with aiofiles.open(chunk_path, 'wb') as f:
                await f.write(audio_data)
            
            logger.info(f"Chunk saved: {chunk_path} ({len(audio_data)} bytes)")
            
            # Initialize status
            _chunk_status[chunk_id] = {
                "chunk_id": chunk_id,
                "round_id": round_id,
                "status": "processing",
                "speaker_role": speaker_role,
                "chunk_index": chunk_index,
                "file_path": str(chunk_path),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Transcribe using Whisper
            if self.use_api:
                result = await self._transcribe_with_api(chunk_path)
            else:
                result = await self._transcribe_offline(chunk_path)
            
            # Update status with results
            _chunk_status[chunk_id].update({
                "status": "completed",
                "transcript_text": result.get("text", ""),
                "confidence": result.get("confidence", 0.0),
                "word_timestamps": result.get("words", []),
                "language": result.get("language", "en"),
                "processed_at": datetime.now(timezone.utc).isoformat()
            })
            
            logger.info(f"Chunk {chunk_id} transcribed: {len(result.get('text', ''))} chars")
            
            return {
                "chunk_id": chunk_id,
                "status": "completed",
                "speaker_role": speaker_role,
                "transcript_text": result.get("text", ""),
                "confidence": result.get("confidence", 0.0),
                "word_timestamps": result.get("words", []),
                "chunk_index": chunk_index
            }
            
        except Exception as e:
            logger.error(f"Error processing chunk {chunk_id}: {e}")
            
            # Update status to failed
            if chunk_id in _chunk_status:
                _chunk_status[chunk_id].update({
                    "status": "failed",
                    "error": str(e),
                    "failed_at": datetime.now(timezone.utc).isoformat()
                })
            
            return {
                "chunk_id": chunk_id,
                "status": "failed",
                "speaker_role": speaker_role,
                "error": str(e),
                "chunk_index": chunk_index
            }
    
    async def _transcribe_with_api(self, audio_path: Path) -> dict:
        """Transcribe using OpenAI Whisper API."""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        
        data = aiohttp.FormData()
        data.add_field('file', open(audio_path, 'rb'), filename=audio_path.name)
        data.add_field('model', WHISPER_MODEL)
        data.add_field('language', 'en')  # Primary language
        data.add_field('response_format', 'verbose_json')
        data.add_field('timestamp_granularities[]', 'word')
        data.add_field('temperature', '0.0')  # Max accuracy
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                WHISPER_API_URL,
                headers=headers,
                data=data,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Whisper API error: {response.status} - {error_text}")
                
                result = await response.json()
                
                # Extract word-level timestamps if available
                words = []
                if 'words' in result:
                    words = [
                        {
                            "word": w.get("word", "").strip(),
                            "start": w.get("start", 0.0),
                            "end": w.get("end", 0.0)
                        }
                        for w in result['words']
                    ]
                
                # Calculate confidence (use segments avg if available)
                confidence = 0.9  # Default
                if 'segments' in result and result['segments']:
                    avg_conf = sum(s.get('avg_logprob', -0.5) for s in result['segments']) / len(result['segments'])
                    # Convert logprob to 0-1 scale (approximate)
                    confidence = min(1.0, max(0.0, 1.0 + avg_conf))
                
                return {
                    "text": result.get("text", ""),
                    "words": words,
                    "confidence": confidence,
                    "language": result.get("language", "en")
                }
    
    async def _transcribe_offline(self, audio_path: Path) -> dict:
        """
        Fallback transcription using local Whisper.
        Requires whisper package: pip install openai-whisper
        """
        try:
            import whisper
            
            # Load model (cached after first load)
            model = whisper.load_model("base")
            
            # Transcribe
            result = model.transcribe(
                str(audio_path),
                language="en",
                temperature=0.0,
                word_timestamps=True
            )
            
            # Extract word timestamps
            words = []
            if 'segments' in result:
                for segment in result['segments']:
                    if 'words' in segment:
                        words.extend([
                            {
                                "word": w.get("word", "").strip(),
                                "start": w.get("start", 0.0),
                                "end": w.get("end", 0.0)
                            }
                            for w in segment['words']
                        ])
            
            # Calculate confidence from segment scores
            confidence = 0.85  # Default for local model
            if 'segments' in result and result['segments']:
                avg_prob = sum(s.get('avg_logprob', -0.5) for s in result['segments']) / len(result['segments'])
                confidence = min(1.0, max(0.0, 1.0 + avg_prob))
            
            return {
                "text": result.get("text", ""),
                "words": words,
                "confidence": confidence,
                "language": result.get("language", "en"),
                "source": "local_whisper"
            }
            
        except ImportError:
            logger.error("openai-whisper package not installed. Run: pip install openai-whisper")
            return {
                "text": "[Transcription unavailable - Whisper not installed]",
                "words": [],
                "confidence": 0.0,
                "language": "en",
                "error": "Whisper not installed"
            }
        except Exception as e:
            logger.error(f"Offline transcription failed: {e}")
            return {
                "text": f"[Transcription failed: {str(e)}]",
                "words": [],
                "confidence": 0.0,
                "error": str(e)
            }
    
    def get_chunk_status(self, chunk_id: str) -> Optional[dict]:
        """Get processing status for a chunk."""
        return _chunk_status.get(chunk_id)
    
    def get_round_chunks(self, round_id: int) -> List[dict]:
        """Get all chunks for a round."""
        return [
            status for status in _chunk_status.values()
            if status.get("round_id") == round_id
        ]
    
    async def finalize_transcript(self, round_id: int) -> dict:
        """
        Concatenate all chunks for a round into final transcript.
        
        Returns:
            Dict with full transcript, segments, metadata
        """
        chunks = self.get_round_chunks(round_id)
        
        if not chunks:
            return {
                "round_id": round_id,
                "transcript_text": "",
                "segments": [],
                "word_count": 0,
                "duration_seconds": 0,
                "processing_status": "no_data"
            }
        
        # Sort by chunk index
        chunks.sort(key=lambda x: x.get("chunk_index", 0))
        
        # Build transcript segments
        segments = []
        full_text_parts = []
        total_duration = 0
        
        for chunk in chunks:
            if chunk.get("status") == "completed":
                segment = {
                    "timestamp": chunk.get("created_at"),
                    "speaker_role": chunk.get("speaker_role"),
                    "text": chunk.get("transcript_text", ""),
                    "confidence": chunk.get("confidence", 0.0),
                    "chunk_id": chunk.get("chunk_id"),
                    "word_timestamps": chunk.get("word_timestamps", [])
                }
                segments.append(segment)
                full_text_parts.append(f"[{chunk.get('speaker_role', 'unknown').upper()}] {chunk.get('transcript_text', '')}")
                total_duration += CHUNK_DURATION_SECONDS
        
        full_text = "\n\n".join(full_text_parts)
        word_count = len(full_text.split())
        
        return {
            "round_id": round_id,
            "transcript_text": full_text,
            "segments": segments,
            "word_count": word_count,
            "duration_seconds": total_duration,
            "processing_status": "completed",
            "chunk_count": len(chunks),
            "completed_chunks": len([c for c in chunks if c.get("status") == "completed"]),
            "failed_chunks": len([c for c in chunks if c.get("status") == "failed"])
        }
    
    async def cleanup_old_chunks(self, max_age_hours: int = 24):
        """
        Clean up audio chunks older than specified hours.
        Called periodically or on round end.
        """
        cutoff = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)
        deleted_count = 0
        
        for chunk_id, status in list(_chunk_status.items()):
            created_at = status.get("created_at")
            if created_at:
                try:
                    created_ts = datetime.fromisoformat(created_at).timestamp()
                    if created_ts < cutoff:
                        # Delete file if exists
                        file_path = status.get("file_path")
                        if file_path:
                            try:
                                Path(file_path).unlink(missing_ok=True)
                                deleted_count += 1
                            except Exception as e:
                                logger.warning(f"Failed to delete chunk file {file_path}: {e}")
                        
                        # Remove from status
                        del _chunk_status[chunk_id]
                except Exception as e:
                    logger.warning(f"Error parsing chunk timestamp: {e}")
        
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old audio chunks")
        
        return deleted_count


# Global service instance
transcription_service = AudioTranscriptionService()
