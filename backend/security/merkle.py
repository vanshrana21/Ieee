"""
Phase 12 — Deterministic Merkle Root Engine

Builds tamper-evident hash trees from tournament data.
All operations are deterministic - no floats, no random, no datetime.now().
"""
import hashlib
from typing import List


def sha256(value: str) -> str:
    """
    Compute SHA256 hash of string value.
    
    Deterministic: Always returns same output for same input.
    """
    return hashlib.sha256(value.encode()).hexdigest()


def build_merkle_root(hashes: List[str]) -> str:
    """
    Build Merkle root from list of hashes.
    
    Deterministic requirements:
    - Input hashes sorted before processing
    - Tree built level by level
    - Each level sorted before next iteration
    
    Args:
        hashes: List of hex strings (64 chars each)
        
    Returns:
        Single 64-char hex Merkle root hash
    """
    if not hashes:
        # Empty tree hash - deterministic constant
        return sha256("EMPTY_MERKLE_TREE")
    
    if len(hashes) == 1:
        # Single leaf - hash of hash for consistency
        return sha256(hashes[0])
    
    # Sort input hashes for determinism
    level = sorted(hashes)
    
    # Build tree level by level
    while len(level) > 1:
        next_level = []
        
        # Process pairs
        for i in range(0, len(level), 2):
            left = level[i]
            # If odd number, duplicate last hash
            right = level[i + 1] if i + 1 < len(level) else left
            
            # Combine and hash (lexicographic order ensures determinism)
            combined = left + right if left <= right else right + left
            next_level.append(sha256(combined))
        
        # Sort next level for continued determinism
        level = sorted(next_level)
    
    return level[0]


def hash_tournament_data(
    tournament_id: int,
    pairing_checksum: str,
    panel_checksum: str,
    event_hashes: List[str],
    objection_hashes: List[str],
    exhibit_hashes: List[str],
    results_checksum: str
) -> str:
    """
    Compute Merkle root from all tournament component hashes.
    
    This creates a single tamper-evident root hash that can detect
    modification of any component: pairings, panels, events, objections,
    exhibits, or results.
    
    Args:
        tournament_id: Tournament identifier
        pairing_checksum: Phase 3 pairing_checksum
        panel_checksum: Phase 4 panel_checksum
        event_hashes: Phase 5 final event hashes
        objection_hashes: Phase 6 objection event hashes
        exhibit_hashes: Phase 7 exhibit hashes
        results_checksum: Phase 9 results_checksum
        
    Returns:
        64-char hex Merkle root hash
    """
    # Tournament ID as base anchor
    id_hash = sha256(f"tournament:{tournament_id}")
    
    # Collect all component hashes
    all_hashes = [
        id_hash,
        pairing_checksum if pairing_checksum else sha256("no_pairings"),
        panel_checksum if panel_checksum else sha256("no_panels"),
        results_checksum if results_checksum else sha256("no_results"),
    ]
    
    # Add event hashes
    for event_hash in sorted(event_hashes):
        all_hashes.append(sha256(f"event:{event_hash}"))
    
    # Add objection hashes
    for obj_hash in sorted(objection_hashes):
        all_hashes.append(sha256(f"objection:{obj_hash}"))
    
    # Add exhibit hashes
    for exh_hash in sorted(exhibit_hashes):
        all_hashes.append(sha256(f"exhibit:{exh_hash}"))
    
    # Build Merkle root
    return build_merkle_root(all_hashes)


def verify_component_inclusion(
    root_hash: str,
    component_hash: str,
    all_hashes: List[str]
) -> bool:
    """
    Verify that a component hash is included in the Merkle root.
    
    This is a simplified check that recomputes the root.
    Full Merkle proofs would require storing the tree structure.
    
    Args:
        root_hash: Stored Merkle root
        component_hash: Component to verify
        all_hashes: Complete list of component hashes
        
    Returns:
        True if component is in the root
    """
    recomputed = build_merkle_root(all_hashes)
    return recomputed == root_hash and component_hash in all_hashes


def serialize_hash_tree(
    tournament_id: int,
    component_hashes: dict
) -> str:
    """
    Create deterministic JSON string for hash tree.
    
    Args:
        tournament_id: Tournament identifier
        component_hashes: Dict of component name -> hash list
        
    Returns:
        Sorted JSON string
    """
    import json
    
    tree = {
        "tournament_id": tournament_id,
        "components": {}
    }
    
    for name, hashes in sorted(component_hashes.items()):
        tree["components"][name] = sorted(hashes)
    
    return json.dumps(tree, sort_keys=True, separators=(',', ':'))
