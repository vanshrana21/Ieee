"""
Phase 15 — Hash Service

Deterministic hash generation and verification for AI evaluations.
All hash computations are deterministic and reproducible.
"""
import hashlib
import json
from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime


class HashService:
    """
    Service for generating and verifying deterministic hashes.
    Used for snapshot integrity and evaluation verification.
    """

    @staticmethod
    def generate_snapshot_hash(snapshot: Dict[str, Any]) -> str:
        """
        Generate deterministic SHA256 hash of a match snapshot.

        Args:
            snapshot: Match snapshot dictionary (must be JSON serializable)

        Returns:
            64-character hex SHA256 hash string
        """
        # Ensure deterministic serialization
        # Remove timestamps and non-deterministic fields
        clean_snapshot = HashService._prepare_for_hashing(snapshot)

        # Serialize with deterministic settings
        snapshot_str = json.dumps(
            clean_snapshot,
            sort_keys=True,
            separators=(',', ':'),  # No whitespace
            default=HashService._json_serializer
        )

        # Compute SHA256
        return hashlib.sha256(snapshot_str.encode('utf-8')).hexdigest()

    @staticmethod
    def generate_evaluation_hash(
        snapshot_hash: str,
        model_name: str,
        response_data: Dict[str, Any]
    ) -> str:
        """
        Generate evaluation hash from snapshot hash and AI response.

        Formula: sha256(snapshot_hash:model_name:sorted_json_response)

        Args:
            snapshot_hash: Hash of the match snapshot
            model_name: Name of the AI model used
            response_data: AI response JSON data

        Returns:
            64-character hex SHA256 hash string
        """
        # Clean and serialize response
        clean_response = HashService._prepare_for_hashing(response_data)

        response_str = json.dumps(
            clean_response,
            sort_keys=True,
            separators=(',', ':'),
            default=HashService._json_serializer
        )

        # Combine components
        hash_input = f"{snapshot_hash}:{model_name}:{response_str}"

        # Compute SHA256
        return hashlib.sha256(hash_input.encode('utf-8')).hexdigest()

    @staticmethod
    def verify_evaluation_integrity(
        snapshot_hash: str,
        model_name: str,
        response_data: Dict[str, Any],
        stored_evaluation_hash: str
    ) -> bool:
        """
        Verify that an evaluation hash matches the stored hash.

        Args:
            snapshot_hash: Hash of the match snapshot
            model_name: Name of the AI model used
            response_data: AI response JSON data
            stored_evaluation_hash: Hash stored in database

        Returns:
            True if hash matches, False otherwise
        """
        computed_hash = HashService.generate_evaluation_hash(
            snapshot_hash, model_name, response_data
        )
        return computed_hash == stored_evaluation_hash

    @staticmethod
    def verify_snapshot_integrity(
        snapshot: Dict[str, Any],
        stored_snapshot_hash: str
    ) -> bool:
        """
        Verify that a snapshot hash matches the stored hash.

        Args:
            snapshot: Match snapshot dictionary
            stored_snapshot_hash: Hash stored in database

        Returns:
            True if hash matches, False otherwise
        """
        computed_hash = HashService.generate_snapshot_hash(snapshot)
        return computed_hash == stored_snapshot_hash

    @staticmethod
    def _prepare_for_hashing(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove non-deterministic fields from data before hashing.

        Removes:
        - Timestamps (created_at, updated_at, frozen_at, etc.)
        - IDs that may vary between systems
        - Debug metadata
        - Null values
        """
        if not isinstance(data, dict):
            return data

        keys_to_remove = {
            # Timestamps
            'created_at', 'updated_at', 'frozen_at', 'started_at',
            'completed_at', 'timestamp', 'last_tick', 'recovered_at',
            'paused_at', 'resumed_at',

            # Debug metadata
            'debug_info', 'metadata', 'internal_notes', 'audit_log',

            # Database-specific
            '_sa_instance_state',
        }

        result = {}
        for key, value in data.items():
            # Skip null values and removed keys
            if key in keys_to_remove or value is None:
                continue

            # Recursively clean nested dictionaries
            if isinstance(value, dict):
                cleaned = HashService._prepare_for_hashing(value)
                if cleaned:  # Only add if not empty
                    result[key] = cleaned
            elif isinstance(value, list):
                # Clean list items
                cleaned_list = []
                for item in value:
                    if isinstance(item, dict):
                        cleaned_item = HashService._prepare_for_hashing(item)
                        if cleaned_item:
                            cleaned_list.append(cleaned_item)
                    elif item is not None:
                        cleaned_list.append(item)
                if cleaned_list:
                    result[key] = cleaned_list
            else:
                result[key] = value

        return result

    @staticmethod
    def _json_serializer(obj: Any) -> Any:
        """
        Custom JSON serializer for non-standard types.
        """
        if isinstance(obj, Decimal):
            return str(obj)  # Convert Decimal to string
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, uuid.UUID):
            return str(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    @staticmethod
    def generate_short_hash(full_hash: str, length: int = 16) -> str:
        """
        Generate a shortened hash for display purposes.

        Args:
            full_hash: Full 64-character hash
            length: Desired length (default 16)

        Returns:
            Shortened hash string
        """
        return full_hash[:length]

    @staticmethod
    def compare_hashes(hash1: str, hash2: str) -> bool:
        """
        Securely compare two hashes (constant-time comparison).

        Args:
            hash1: First hash string
            hash2: Second hash string

        Returns:
            True if hashes match, False otherwise
        """
        if len(hash1) != len(hash2):
            return False

        # Use constant-time comparison to prevent timing attacks
        result = 0
        for c1, c2 in zip(hash1, hash2):
            result |= ord(c1) ^ ord(c2)

        return result == 0


# Singleton instance
hash_service = HashService()
