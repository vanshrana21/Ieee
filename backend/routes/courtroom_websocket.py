"""
Phase 0: Virtual Courtroom Infrastructure - Courtroom WebSocket Endpoint

WebSocket endpoint for real-time courtroom communication.
Handles authentication, message routing, and role-based access control.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException, status
from typing import Optional
import json
import logging
from datetime import datetime

from backend.websockets.courtroom import manager
from backend.schemas.courtroom_messages import (
    parse_message,
    TimerStartMessage,
    TimerPauseMessage,
    TimerResumeMessage,
    TimerResetMessage,
    ObjectionRaisedMessage,
    ObjectionRulingMessage,
    TranscriptUpdateMessage,
    ScoreUpdateMessage,
    SpeakerChangeMessage,
    RoundCompleteMessage,
    PingMessage,
    ErrorMessage,
    MessageType
)
from backend.orm.oral_round import OralRound
from backend.orm.database import SessionLocal

logger = logging.getLogger(__name__)
router = APIRouter()


async def validate_token(token: str) -> dict:
    """
    Validate JWT token and return user data.
    
    Args:
        token: JWT token string
    
    Returns:
        dict with user_id, role, and other claims
    
    Raises:
        HTTPException: If token is invalid or expired
    """
    # TODO: Implement actual JWT validation
    # For Phase 0, return mock data
    # In production, use: from backend.auth.jwt import decode_token
    
    if not token or token == "test_token":
        return {"user_id": 1, "role": "judge", "name": "Test Judge"}
    
    # Simple validation for testing
    if token.startswith("judge_"):
        return {"user_id": int(token.split("_")[1]), "role": "judge"}
    elif token.startswith("petitioner_"):
        return {"user_id": int(token.split("_")[1]), "role": "petitioner"}
    elif token.startswith("respondent_"):
        return {"user_id": int(token.split("_")[1]), "role": "respondent"}
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token"
    )


async def verify_round_access(user_data: dict, round_id: int) -> bool:
    """
    Verify user has access to the specified round.
    
    Args:
        user_data: Dict with user_id, role
        round_id: Round ID from path
    
    Returns:
        True if access granted, False otherwise
    """
    db = SessionLocal()
    try:
        round_obj = db.query(OralRound).filter(OralRound.id == round_id).first()
        if not round_obj:
            return False
        
        user_id = user_data.get("user_id")
        role = user_data.get("role")
        
        # Judges have access if they are presiding or co-judge
        if role == "judge":
            if round_obj.presiding_judge_id == user_id:
                return True
            co_judges = round_obj.get_co_judges_list()
            if user_id in co_judges:
                return True
            return False
        
        # Team members have access if on petitioner or respondent team
        if role == "petitioner":
            return round_obj.petitioner_team_id == user_data.get("team_id")
        if role == "respondent":
            return round_obj.respondent_team_id == user_data.get("team_id")
        
        return False
    finally:
        db.close()


@router.websocket("/ws/courtroom/{round_id}")
async def courtroom_websocket(
    websocket: WebSocket,
    round_id: int,
    token: str = Query(..., description="JWT authentication token")
):
    """
    WebSocket endpoint for real-time courtroom communication.
    
    Connection Flow:
    1. Extract token from query param: ?token=eyJ...
    2. Validate JWT → get user_id, role
    3. Verify user has access to round_id
    4. Reject if unauthorized (close code 4001)
    
    Message Routing:
    - timer_start, timer_pause, timer_resume, timer_reset
    - objection_raised, objection_ruling
    - speaker_change
    - score_update
    - transcript_update
    - round_complete
    
    Args:
        websocket: WebSocket connection
        round_id: Round identifier from path
        token: JWT token from query parameter
    """
    user_data = None
    
    try:
        # Authentication
        try:
            user_data = await validate_token(token)
        except HTTPException:
            await websocket.close(code=4001, reason="Invalid authentication token")
            return
        
        # Authorization
        has_access = await verify_round_access(user_data, round_id)
        if not has_access:
            await websocket.close(code=4001, reason="Access denied to this round")
            return
        
        user_id = user_data.get("user_id")
        role = user_data.get("role")
        room_id = f"courtroom_{round_id}"
        
        # Connect to room
        await manager.connect(websocket, room_id, user_id, role)
        
        # Main message loop
        while True:
            try:
                # Receive message
                data = await websocket.receive_text()
                message_data = json.loads(data)
                
                # Parse and validate message
                try:
                    message = parse_message(message_data)
                except ValueError as e:
                    logger.warning(f"Invalid message from user {user_id}: {e}")
                    await manager.send_to_user(room_id, user_id, {
                        "type": "error",
                        "error_code": "INVALID_MESSAGE",
                        "message": str(e),
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    continue
                
                # Route message based on type
                await route_message(room_id, user_id, role, message)
                
            except WebSocketDisconnect:
                break
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON from user {user_id}: {e}")
                await manager.send_to_user(room_id, user_id, {
                    "type": "error",
                    "error_code": "INVALID_JSON",
                    "message": "Message must be valid JSON",
                    "timestamp": datetime.utcnow().isoformat()
                })
            except Exception as e:
                logger.error(f"Error handling message from user {user_id}: {e}")
                await manager.send_to_user(room_id, user_id, {
                    "type": "error",
                    "error_code": "SERVER_ERROR",
                    "message": "Internal server error",
                    "timestamp": datetime.utcnow().isoformat()
                })
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for round {round_id}")
    except Exception as e:
        logger.error(f"WebSocket error for round {round_id}: {e}")
    finally:
        # Cleanup connection
        if user_data:
            room_id = f"courtroom_{round_id}"
            await manager.disconnect(websocket, room_id, user_data.get("user_id"))


async def route_message(room_id: str, user_id: int, role: str, message):
    """
    Route message to appropriate handler based on type.
    
    Args:
        room_id: Room identifier
        user_id: User ID of sender
        role: Role of sender (judge, petitioner, respondent)
        message: Parsed Pydantic message model
    """
    msg_type = message.type
    
    # Timer messages (judges only)
    if msg_type in (MessageType.TIMER_START, MessageType.TIMER_PAUSE, 
                    MessageType.TIMER_RESUME, MessageType.TIMER_RESET):
        if role != "judge":
            await send_permission_denied(room_id, user_id, "timer control")
            return
        await handle_timer_message(room_id, message)
    
    # Objection messages
    elif msg_type == MessageType.OBJECTION_RAISED:
        if role not in ("petitioner", "respondent"):
            await send_permission_denied(room_id, user_id, "raise objections")
            return
        await handle_objection_raised(room_id, user_id, role, message)
    
    elif msg_type == MessageType.OBJECTION_RULING:
        if role != "judge":
            await send_permission_denied(room_id, user_id, "rule on objections")
            return
        await handle_objection_ruling(room_id, user_id, message)
    
    # Transcript messages
    elif msg_type == MessageType.TRANSCRIPT_UPDATE:
        await handle_transcript_update(room_id, message)
    
    # Score messages (judges only)
    elif msg_type == MessageType.SCORE_UPDATE:
        if role != "judge":
            await send_permission_denied(room_id, user_id, "submit scores")
            return
        await handle_score_update(room_id, message)
    
    # Speaker change (judges only)
    elif msg_type == MessageType.SPEAKER_CHANGE:
        if role != "judge":
            await send_permission_denied(room_id, user_id, "change speaker")
            return
        await handle_speaker_change(room_id, message)
    
    # Round complete (judges only)
    elif msg_type == MessageType.ROUND_COMPLETE:
        if role != "judge":
            await send_permission_denied(room_id, user_id, "complete round")
            return
        await handle_round_complete(room_id, message)
    
    # Ping/pong
    elif msg_type == MessageType.PING:
        await manager.send_to_user(room_id, user_id, {"type": "pong", "timestamp": datetime.utcnow().isoformat()})
    
    else:
        logger.warning(f"Unhandled message type: {msg_type}")


async def send_permission_denied(room_id: str, user_id: int, action: str):
    """Send permission denied error to user."""
    await manager.send_to_user(room_id, user_id, {
        "type": "error",
        "error_code": "PERMISSION_DENIED",
        "message": f"You do not have permission to {action}",
        "timestamp": datetime.utcnow().isoformat()
    })


async def handle_timer_message(room_id: str, message):
    """Handle timer control messages."""
    # Broadcast timer update to all participants
    await manager.broadcast(room_id, {
        "type": "timer_update",
        "action": message.type.value,
        "time_remaining": getattr(message, 'time_remaining', None),
        "current_speaker": getattr(message, 'speaker_role', None),
        "timestamp": datetime.utcnow().isoformat()
    })
    
    # Update room state
    state_update = {}
    if hasattr(message, 'time_remaining'):
        state_update['time_remaining'] = message.time_remaining
    if hasattr(message, 'speaker_role'):
        state_update['current_speaker'] = message.speaker_role
    if message.type == MessageType.TIMER_START:
        state_update['timer_running'] = True
    elif message.type in (MessageType.TIMER_PAUSE, MessageType.TIMER_RESET):
        state_update['timer_running'] = False
    
    manager.update_room_state(room_id, state_update)


async def handle_objection_raised(room_id: str, user_id: int, role: str, message: ObjectionRaisedMessage):
    """Handle objection raised messages."""
    # Broadcast to all participants (judge needs to rule)
    await manager.broadcast(room_id, {
        "type": "objection_raised",
        "objection_type": message.objection_type.value,
        "raised_by": user_id,
        "raised_by_role": role,
        "reason": message.objection_text,
        "interrupted_speaker": message.interrupted_speaker.value,
        "time_remaining_before": message.time_remaining_before,
        "timestamp": datetime.utcnow().isoformat()
    })


async def handle_objection_ruling(room_id: str, judge_id: int, message: ObjectionRulingMessage):
    """Handle objection ruling messages."""
    # Broadcast ruling to all participants
    await manager.broadcast(room_id, {
        "type": "objection_ruling",
        "objection_id": message.objection_id,
        "ruling": message.ruling.value,
        "ruling_notes": message.ruling_notes,
        "judge_id": judge_id,
        "time_remaining_after": message.time_remaining_after,
        "timestamp": datetime.utcnow().isoformat()
    })


async def handle_transcript_update(room_id: str, message: TranscriptUpdateMessage):
    """Handle transcript segment updates."""
    # Broadcast to all participants
    await manager.broadcast(room_id, {
        "type": "transcript_update",
        "segment_id": message.segment_id,
        "speaker_role": message.speaker_role.value,
        "text": message.text,
        "confidence": message.confidence,
        "audio_chunk_id": message.audio_chunk_id,
        "timestamp": datetime.utcnow().isoformat()
    })


async def handle_score_update(room_id: str, message: ScoreUpdateMessage):
    """Handle score update messages."""
    # Broadcast to all participants
    await manager.broadcast(room_id, {
        "type": "score_update",
        "score_id": message.score_id,
        "team_id": message.team_id,
        "team_side": message.team_side.value,
        "judge_id": message.judge_id,
        "criteria": {
            "legal_reasoning": message.criteria.legal_reasoning,
            "citation_format": message.criteria.citation_format,
            "courtroom_etiquette": message.criteria.courtroom_etiquette,
            "responsiveness": message.criteria.responsiveness,
            "time_management": message.criteria.time_management
        },
        "total_score": message.total_score,
        "is_draft": message.is_draft,
        "timestamp": datetime.utcnow().isoformat()
    })


async def handle_speaker_change(room_id: str, message: SpeakerChangeMessage):
    """Handle speaker transition messages."""
    # Broadcast to all participants
    await manager.broadcast(room_id, {
        "type": "speaker_change",
        "previous_speaker": message.previous_speaker.value,
        "new_speaker": message.new_speaker.value,
        "new_time_remaining": message.new_time_remaining,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    # Update room state
    manager.update_room_state(room_id, {
        "current_speaker": message.new_speaker.value,
        "time_remaining": message.new_time_remaining
    })


async def handle_round_complete(room_id: str, message: RoundCompleteMessage):
    """Handle round completion messages."""
    # Broadcast to all participants
    await manager.broadcast(room_id, {
        "type": "round_complete",
        "final_scores": message.final_scores,
        "winner_team_id": message.winner_team_id,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    # Update room state
    manager.update_room_state(room_id, {"status": "completed"})
