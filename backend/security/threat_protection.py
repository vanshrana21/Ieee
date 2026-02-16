"""
Phase 10 — Threat Protection System

Advanced threat detection and prevention.
Detects DDoS, brute force, injection attempts, and anomalous behavior.
"""
import time
from typing import Dict, Any, Optional, List, Set
from collections import defaultdict
from datetime import datetime, timedelta


class ThreatProtection:
    """
    Real-time threat detection and protection.
    
    Tracks:
    - Request rates per IP
    - Failed authentication attempts
    - Suspicious request patterns
    - Geographic anomalies (if GeoIP available)
    
    No external dependencies, deterministic detection.
    """
    
    # Rate limits
    MAX_REQUESTS_PER_MINUTE = 120
    MAX_REQUESTS_PER_SECOND = 10
    MAX_FAILED_AUTH_PER_MINUTE = 5
    
    # Block duration (seconds)
    BLOCK_DURATION = 300  # 5 minutes
    
    def __init__(self):
        # Request tracking: {ip: [(timestamp, path), ...]}
        self.request_history: Dict[str, List[tuple]] = defaultdict(list)
        
        # Failed auth tracking: {ip: [(timestamp, username), ...]}
        self.auth_failures: Dict[str, List[datetime]] = defaultdict(list)
        
        # Blocked IPs: {ip: unblock_timestamp}
        self.blocked_ips: Dict[str, float] = {}
        
        # Suspicious patterns detected: {ip: count}
        self.suspicious_counts: Dict[str, int] = defaultdict(int)
        
        # Known bad IPs (honeypot, threat intel)
        self.known_bad_ips: Set[str] = set()
    
    async def check_request(self, client_ip: str, path: str, method: str) -> Optional[str]:
        """
        Check if request should be blocked.
        
        Args:
            client_ip: Client IP address
            path: Request path
            method: HTTP method
        
        Returns:
            Block reason if blocked, None if allowed
        """
        now = time.time()
        
        # Check if IP is currently blocked
        if self._is_blocked(client_ip, now):
            return "IP_BLOCKED"
        
        # Clean old entries
        self._clean_old_entries(client_ip, now)
        
        # Record this request
        self.request_history[client_ip].append((now, path))
        
        # Check rate limits
        rate_violation = self._check_rate_limits(client_ip, now)
        if rate_violation:
            self._block_ip(client_ip, now)
            return f"RATE_LIMIT:{rate_violation}"
        
        # Check for suspicious patterns
        suspicious = self._check_suspicious_patterns(client_ip, path, method)
        if suspicious:
            self.suspicious_counts[client_ip] += 1
            
            if self.suspicious_counts[client_ip] >= 3:
                self._block_ip(client_ip, now)
                return f"SUSPICIOUS:{suspicious}"
        
        # Check known bad IPs
        if client_ip in self.known_bad_ips:
            return "KNOWN_BAD_IP"
        
        return None
    
    def _is_blocked(self, client_ip: str, now: float) -> bool:
        """Check if IP is currently blocked."""
        if client_ip not in self.blocked_ips:
            return False
        
        unblock_time = self.blocked_ips[client_ip]
        if now > unblock_time:
            # Unblock expired
            del self.blocked_ips[client_ip]
            return False
        
        return True
    
    def _block_ip(self, client_ip: str, now: float) -> None:
        """Block an IP address."""
        self.blocked_ips[client_ip] = now + self.BLOCK_DURATION
    
    def _clean_old_entries(self, client_ip: str, now: float) -> None:
        """Clean old entries from request history."""
        cutoff = now - 60  # Keep 60 seconds of history
        
        if client_ip in self.request_history:
            self.request_history[client_ip] = [
                (ts, path) for ts, path in self.request_history[client_ip]
                if ts > cutoff
            ]
        
        # Clean auth failures older than 5 minutes
        auth_cutoff = datetime.utcnow() - timedelta(minutes=5)
        if client_ip in self.auth_failures:
            self.auth_failures[client_ip] = [
                dt for dt in self.auth_failures[client_ip]
                if dt > auth_cutoff
            ]
    
    def _check_rate_limits(self, client_ip: str, now: float) -> Optional[str]:
        """
        Check if IP exceeds rate limits.
        
        Returns:
            Violation type if exceeded, None if OK
        """
        requests = self.request_history.get(client_ip, [])
        
        if not requests:
            return None
        
        # Check per-second rate
        second_ago = now - 1
        recent_requests = [ts for ts, _ in requests if ts > second_ago]
        if len(recent_requests) > self.MAX_REQUESTS_PER_SECOND:
            return "PER_SECOND"
        
        # Check per-minute rate
        if len(requests) > self.MAX_REQUESTS_PER_MINUTE:
            return "PER_MINUTE"
        
        return None
    
    def _check_suspicious_patterns(
        self,
        client_ip: str,
        path: str,
        method: str
    ) -> Optional[str]:
        """
        Check for suspicious request patterns.
        
        Returns:
            Pattern type if suspicious, None if OK
        """
        path_lower = path.lower()
        
        # Admin panel scanning
        admin_paths = ["/admin", "/wp-admin", "/phpmyadmin", "/.env", "/config"]
        for admin_path in admin_paths:
            if admin_path in path_lower:
                return "ADMIN_SCAN"
        
        # API enumeration
        if "/api/v" in path_lower and method == "GET":
            # Check if rapidly enumerating
            requests = self.request_history.get(client_ip, [])
            api_requests = [p for ts, p in requests if "/api/" in p.lower()]
            if len(api_requests) > 20:
                return "API_ENUMERATION"
        
        # SQL injection probes
        sql_patterns = ["union%20select", "'or'1'='1", "';drop", "--"]
        for pattern in sql_patterns:
            if pattern in path_lower:
                return "SQLI_PROBE"
        
        # Path traversal
        if "../" in path or "%2e%2e/" in path_lower:
            return "PATH_TRAVERSAL"
        
        return None
    
    def record_auth_failure(self, client_ip: str, username: str) -> bool:
        """
        Record failed authentication attempt.
        
        Returns:
            True if IP should be blocked
        """
        now = datetime.utcnow()
        
        # Clean old entries
        cutoff = now - timedelta(minutes=5)
        self.auth_failures[client_ip] = [
            dt for dt in self.auth_failures.get(client_ip, [])
            if dt > cutoff
        ]
        
        # Add this failure
        self.auth_failures[client_ip].append(now)
        
        # Check threshold
        if len(self.auth_failures[client_ip]) >= self.MAX_FAILED_AUTH_PER_MINUTE:
            return True
        
        return False
    
    def get_threat_report(self) -> Dict[str, Any]:
        """
        Get current threat status report.
        
        Returns:
            Dict with threat statistics
        """
        now = time.time()
        
        # Clean expired blocks
        expired = [ip for ip, unblock in self.blocked_ips.items() if now > unblock]
        for ip in expired:
            del self.blocked_ips[ip]
        
        return {
            "blocked_ips": len(self.blocked_ips),
            "monitored_ips": len(self.request_history),
            "suspicious_ips": len(self.suspicious_counts),
            "known_bad_ips": len(self.known_bad_ips),
            "max_requests_per_minute": self.MAX_REQUESTS_PER_MINUTE,
            "max_failed_auth_per_minute": self.MAX_FAILED_AUTH_PER_MINUTE,
            "block_duration_seconds": self.BLOCK_DURATION
        }
    
    def is_ip_blocked(self, client_ip: str) -> bool:
        """Check if IP is currently blocked."""
        return self._is_blocked(client_ip, time.time())


class AnomalyDetector:
    """
    Behavioral anomaly detection.
    
    Detects unusual patterns in user behavior.
    """
    
    def __init__(self):
        # User behavior profiles: {user_id: {feature: value}}
        self.behavior_profiles: Dict[int, Dict[str, Any]] = {}
        
        # Anomaly scores: {user_id: score}
        self.anomaly_scores: Dict[int, float] = {}
    
    def record_user_action(self, user_id: int, action: str, metadata: Dict[str, Any]) -> float:
        """
        Record user action and compute anomaly score.
        
        Args:
            user_id: User ID
            action: Action type
            metadata: Action metadata
        
        Returns:
            Anomaly score (0 = normal, >1 = suspicious)
        """
        if user_id not in self.behavior_profiles:
            self.behavior_profiles[user_id] = {
                "actions": [],
                "action_counts": defaultdict(int),
                "typical_hours": set()
            }
        
        profile = self.behavior_profiles[user_id]
        
        # Update profile
        profile["actions"].append((action, metadata.get("timestamp", time.time())))
        profile["action_counts"][action] += 1
        
        # Compute anomaly score (simplified)
        score = 0.0
        
        # Check action velocity
        if len(profile["actions"]) > 100:
            recent_actions = profile["actions"][-100:]
            time_span = recent_actions[-1][1] - recent_actions[0][1]
            if time_span < 60:  # 100 actions in 60 seconds
                score += 0.5
        
        # Check unusual action types
        total_actions = sum(profile["action_counts"].values())
        if total_actions > 10:
            action_ratio = profile["action_counts"][action] / total_actions
            if action_ratio > 0.8 and action in ("delete", "modify"):
                score += 0.3
        
        self.anomaly_scores[user_id] = score
        
        return score
    
    def is_user_suspicious(self, user_id: int, threshold: float = 0.8) -> bool:
        """
        Check if user is showing suspicious behavior.
        
        Args:
            user_id: User ID
            threshold: Anomaly score threshold
        
        Returns:
            True if suspicious
        """
        score = self.anomaly_scores.get(user_id, 0.0)
        return score >= threshold
