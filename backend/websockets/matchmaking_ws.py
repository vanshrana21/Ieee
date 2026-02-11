"""
Matchmaking WebSocket Handler

WebSocket endpoint for Online 1v1 Mode real-time communication.
Room ID pattern: match:{match_id}
"""
import json
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from backend.websockets.protocol import (
    EventType, BaseEvent, UserJoinedEvent, UserLeftEvent,
    ConnectionEstablishedEvent, TimerStartEvent, TimerUpdateEvent,
    TimerExpiredEvent, MatchFoundEvent, MatchStartedEvent, MatchCompletedEvent,
    ArgumentSubmittedEvent, ObjectionRaisedEvent, ErrorEvent,
    parse_event, validate_event
)
from backend.state_machines.online_match import OnlineMatchStateMachine, OnlineMatchState


class MatchConnectionManager:
    """Manages WebSocket connections for online matches."""
    
    def __init__(self):
        # Room ID -> Set of WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # Room ID -> Match data
        self.room_data: Dict[str, dict] = {}
        # Room ID -> State machine
        self.state_machines: Dict[str, OnlineMatchStateMachine] = {}
    
    async def connect(self, websocket: WebSocket, room_id: str, user_id: str, match_id: str):
        """Accept connection and add to room."""
        await websocket.accept()
        
        if room_id not in self.active_connections:
            self.active_connections[room_id] = set()
            self.room_data[room_id] = {
                "participants": {},
                "match_id": match_id,
                "state": "searching",
                "timer": None
            }
            # Initialize state machine
            self.state_machines[room_id] = OnlineMatchStateMachine(match_id)
        
        self.active_connections[room_id].add(websocket)
        
        # Store participant info
        self.room_data[room_id]["participants"][websocket] = {
            "user_id": user_id,
            "role": None,  # Assigned when match starts
            "name": f"Player {user_id}",
            "is_ready": False
        }
        
        # Get state machine
        state_machine = self.state_machines[room_id]
        
        # Check which player this is
        if state_machine.player1_id == user_id:
            state_machine.set_player_connected(user_id, True)
            self.room_data[room_id]["participants"][websocket]["role"] = state_machine.player1_role
        elif state_machine.player2_id == user_id:
            state_machine.set_player_connected(user_id, True)
            self.room_data[room_id]["participants"][websocket]["role"] = state_machine.player2_role
        
        # Broadcast user joined
        event = UserJoinedEvent(
            room_id=room_id,
            user_id=user_id,
            role=self.room_data[room_id]["participants"][websocket]["role"] or "player",
            name=f"Player {user_id}"
        )
        await self.broadcast(room_id, event.dict())
        
        # Send connection established
        participants = [
            {"user_id": p["user_id"], "role": p["role"], "name": p["name"], "is_ready": p["is_ready"]}
            for p in self.room_data[room_id]["participants"].values()
        ]
        
        established = ConnectionEstablishedEvent(
            room_id=room_id,
            participants=participants
        )
        await websocket.send_json(established.dict())
    
    def disconnect(self, websocket: WebSocket, room_id: str):
        """Remove connection from room."""
        if room_id in self.active_connections:
            self.active_connections[room_id].discard(websocket)
            
            # Get user info before removing
            participant = self.room_data[room_id]["participants"].pop(websocket, None)
            
            # Update state machine
            if participant and room_id in self.state_machines:
                self.state_machines[room_id].set_player_connected(participant["user_id"], False)
            
            # Clean up empty rooms after 5 minutes
            if not self.active_connections[room_id]:
                # Schedule cleanup
                import asyncio
                asyncio.create_task(self._delayed_cleanup(room_id, 300))
            elif participant:
                # Return participant for broadcast
                return participant
        return None
    
    async def _delayed_cleanup(self, room_id: str, delay: int):
        """Delayed cleanup for empty rooms."""
        import asyncio
        await asyncio.sleep(delay)
        
        if room_id in self.active_connections and not self.active_connections[room_id]:
            del self.active_connections[room_id]
            del self.room_data[room_id]
            if room_id in self.state_machines:
                del self.state_machines[room_id]
    
    async def broadcast(self, room_id: str, message: dict):
        """Broadcast message to all connections in room."""
        if room_id not in self.active_connections:
            return
        
        disconnected = []
        for connection in self.active_connections[room_id]:
            try:
                await connection.send_json(message)
            except:
                disconnected.append(connection)
        
        # Clean up disconnected
        for conn in disconnected:
            self.active_connections[room_id].discard(conn)
    
    async def send_to_player(self, room_id: str, user_id: str, message: dict):
        """Send message to specific player."""
        if room_id not in self.room_data:
            return
        
        for websocket, participant in self.room_data[room_id]["participants"].items():
            if participant["user_id"] == user_id:
                try:
                    await websocket.send_json(message)
                except:
                    pass
                break
    
    async def send_personal(self, websocket: WebSocket, message: dict):
        """Send message to specific connection."""
        try:
            await websocket.send_json(message)
        except:
            pass
    
    def get_player_count(self, room_id: str) -> int:
        """Get number of players in room."""
        if room_id in self.room_data:
            return len(self.room_data[room_id]["participants"])
        return 0
    
    def set_player_ready(self, room_id: str, user_id: str, ready: bool = True):
        """Set player ready status."""
        if room_id not in self.room_data:
            return
        
        for websocket, participant in self.room_data[room_id]["participants"].items():
            if participant["user_id"] == user_id:
                participant["is_ready"] = ready
                break
        
        # Update state machine
        if room_id in self.state_machines:
            self.state_machines[room_id].set_player_ready(user_id, ready)


# Global connection manager
match_manager = MatchConnectionManager()


async def matchmaking_websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    match_id: str,
    db: Session,
    token: str = None
):
    """
    WebSocket endpoint for online 1v1 matches.
    
    URL: /ws/match/{room_id}?token={jwt}
    """
    # Validate token and get user info
    # TODO: Implement JWT validation
    user_id = "1"  # Placeholder
    
    # Connect to room
    await match_manager.connect(websocket, room_id, user_id, match_id)
    
    # Get state machine
    state_machine = match_manager.state_machines.get(room_id)
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                error = ErrorEvent(
                    room_id=room_id,
                    error_code="INVALID_JSON",
                    message="Invalid JSON format"
                )
                await match_manager.send_personal(websocket, error.dict())
                continue
            
            # Parse and validate event
            event = parse_event(message)
            if not event:
                error = ErrorEvent(
                    room_id=room_id,
                    error_code="INVALID_EVENT",
                    message="Unknown event type"
                )
                await match_manager.send_personal(websocket, error.dict())
                continue
            
            # Validate permissions
            if not validate_event(event, user_id, "player"):
                error = ErrorEvent(
                    room_id=room_id,
                    error_code="PERMISSION_DENIED",
                    message="Not authorized for this action"
                )
                await match_manager.send_personal(websocket, error.dict())
                continue
            
            # Handle event
            await handle_match_event(
                event, room_id, match_id, websocket, db, user_id, state_machine
            )
            
    except WebSocketDisconnect:
        participant = match_manager.disconnect(websocket, room_id)
        if participant:
            # Broadcast user left
            event = UserLeftEvent(
                room_id=room_id,
                user_id=participant["user_id"]
            )
            await match_manager.broadcast(room_id, event.dict())


async def handle_match_event(
    event: BaseEvent,
    room_id: str,
    match_id: str,
    websocket: WebSocket,
    db: Session,
    user_id: str,
    state_machine: OnlineMatchStateMachine
):
    """Handle match-specific events."""
    
    if event.type == EventType.ARGUMENT_SUBMITTED:
        # Validate and save argument
        if isinstance(event, ArgumentSubmittedEvent):
            # TODO: Save to database
            
            # Broadcast to opponent
            await match_manager.broadcast(room_id, event.dict())
    
    elif event.type == EventType.OBJECTION_RAISED:
        # Broadcast objection
        await match_manager.broadcast(room_id, event.dict())
    
    elif event.type == EventType.TIMER_START:
        # Server controls timers - ignore client requests
        pass
    
    elif event.type == EventType.TIMER_PAUSE:
        # Server controls timers - ignore client requests
        pass


async def start_match(room_id: str, match_data: dict):
    """Start match and broadcast to players."""
    state_machine = match_manager.state_machines.get(room_id)
    if not state_machine:
        return
    
    # Transition to PREP
    await state_machine.transition_to(OnlineMatchState.PREP)
    
    # Send match found event to each player
    for websocket, participant in match_manager.room_data[room_id]["participants"].items():
        is_player1 = participant["user_id"] == state_machine.player1_id
        opponent_id = state_machine.player2_id if is_player1 else state_machine.player1_id
        
        event = MatchFoundEvent(
            room_id=room_id,
            opponent_id=str(opponent_id),
            opponent_name=f"Player {opponent_id}",
            opponent_rating=1000,  # TODO: Get actual rating
            match_id=match_id
        )
        await match_manager.send_personal(websocket, event.dict())


async def broadcast_match_started(room_id: str, topic: str, problem_statement: str):
    """Broadcast match started to both players."""
    state_machine = match_manager.state_machines.get(room_id)
    if not state_machine:
        return
    
    for websocket, participant in match_manager.room_data[room_id]["participants"].items():
        is_player1 = participant["user_id"] == state_machine.player1_id
        role = state_machine.player1_role if is_player1 else state_machine.player2_role
        opponent_role = state_machine.player2_role if is_player1 else state_machine.player1_role
        
        event = MatchStartedEvent(
            room_id=room_id,
            topic=topic,
            problem_statement=problem_statement,
            your_role=role,
            opponent_role=opponent_role
        )
        await match_manager.send_personal(websocket, event.dict())


async def broadcast_timer_update(room_id: str, time_remaining: int, is_paused: bool = False):
    """Broadcast timer update to room."""
    event = TimerUpdateEvent(
        room_id=room_id,
        time_remaining=time_remaining,
        is_paused=is_paused
    )
    await match_manager.broadcast(room_id, event.dict())


async def handle_match_completed(room_id: str, winner_id: str, scores: dict, rating_changes: dict):
    """Broadcast match completion to both players."""
    state_machine = match_manager.state_machines.get(room_id)
    if not state_machine:
        return
    
    for websocket, participant in match_manager.room_data[room_id]["participants"].items():
        user_id = participant["user_id"]
        is_winner = user_id == winner_id
        
        opponent_id = state_machine.player2_id if user_id == state_machine.player1_id else state_machine.player1_id
        
        event = MatchCompletedEvent(
            room_id=room_id,
            winner_id=winner_id,
            your_score=scores.get(user_id, {}),
            opponent_score=scores.get(opponent_id, {}),
            rating_change=rating_changes.get(user_id, 0),
            new_rating=1000 + rating_changes.get(user_id, 0)  # TODO: Get actual new rating
        )
        await match_manager.send_personal(websocket, event.dict())
