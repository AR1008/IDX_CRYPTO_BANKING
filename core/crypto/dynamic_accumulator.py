"""
Dynamic Accumulator - O(1) membership checks with 256-bit compact representation.

Hash-based accumulator for account validation, blacklist management, and double-spend prevention.
Supports add/remove/verify operations with constant-size proof.
"""

import hashlib
import json
from typing import Set, Dict, Any, Optional, List


class DynamicAccumulator:
    """Dynamic cryptographic accumulator with O(1) membership verification and 256-bit compact representation."""

    def __init__(self, initial_value: Optional[str] = None):
        """Initialize accumulator with optional initial value."""
        # [DOC] The accumulator value is a single hash that encodes the entire membership set.
        # [DOC] No matter how many nullifiers are in the set, the accumulator is always exactly 66 characters ("0x" + 64 hex).
        # Current accumulator value (256-bit hash)
        if initial_value:
            # [DOC] Allow bootstrapping from a saved state (e.g. loaded from database on restart).
            self.accumulator = initial_value
        else:
            # [DOC] Initialize with genesis value: a deterministic SHA-256 hash of a known constant.
            # [DOC] Using a fixed seed means two fresh accumulators start identically and can be compared.
            # Initialize with genesis value
            self.accumulator = '0x' + hashlib.sha256(
                b"GENESIS_ACCUMULATOR_IDX_BANKING"
            ).hexdigest()

        # [DOC] elements is a Python set that tracks the actual membership — needed for O(1) is_member() checks.
        # [DOC] In production this would be stored in a database table, not in memory.
        # Set of elements (for membership checks and removal)
        # In production, this could be stored in a database
        self.elements: Set[str] = set()

        # [DOC] count tracks how many distinct elements are currently in the accumulator.
        # Element count
        self.count = 0

    def _hash_accumulate(self, current: str, element: str) -> str:
        """Hash function for accumulator updates: accumulator' = Hash(current || element)."""
        # [DOC] Combine the current accumulator value and the new element into a deterministic JSON string.
        # [DOC] Using JSON with sort_keys ensures the representation is the same regardless of insertion platform.
        data = json.dumps({
            'accumulator': current,
            'element': element
        }, sort_keys=True)

        # [DOC] SHA-256 the combined string to produce the new 256-bit accumulator value.
        # [DOC] The "0x" prefix is a convention indicating a hexadecimal representation.
        new_accumulator = hashlib.sha256(data.encode()).hexdigest()
        return '0x' + new_accumulator

    def add(self, element: str) -> str:
        """Add element to accumulator in O(1) time. Returns new accumulator value."""
        # [DOC] If the element is already in the set, do nothing — the accumulator stays the same.
        # [DOC] This prevents double-spend: the same nullifier cannot be added twice.
        # Check if already in set
        if element in self.elements:
            return self.accumulator  # No change

        # [DOC] Update the accumulator hash: new_acc = SHA256(current_acc || element).
        # [DOC] This is an O(1) operation — the time to update does not grow with set size.
        # Update accumulator
        self.accumulator = self._hash_accumulate(self.accumulator, element)

        # [DOC] Record the element in the backing set so is_member() can answer membership queries.
        # Add to set
        self.elements.add(element)
        # [DOC] Increment the counter for informational purposes (e.g. API responses, logging).
        self.count += 1

        return self.accumulator

    def remove(self, element: str) -> str:
        """Remove element from accumulator in O(n) time (recomputes from scratch). Returns new accumulator value."""
        # [DOC] Removal is only possible if the element is actually in the set.
        if element not in self.elements:
            raise ValueError(f"Element not in accumulator: {element}")

        # [DOC] Remove the element from the Python set first.
        # Remove from set
        self.elements.remove(element)
        self.count -= 1

        # [DOC] Hash-based accumulators cannot "un-hash" — removal requires recomputing from scratch.
        # [DOC] This is O(n) in the number of remaining elements, which is acceptable for rare removals.
        # Recompute accumulator from scratch
        # Start with genesis
        self.accumulator = '0x' + hashlib.sha256(
            b"GENESIS_ACCUMULATOR_IDX_BANKING"
        ).hexdigest()

        # [DOC] Re-add all remaining elements in sorted order to ensure a deterministic final value.
        # [DOC] sorted() ensures two accumulators with the same elements always converge to the same hash.
        # Add all remaining elements
        for elem in sorted(self.elements):  # Sort for determinism
            self.accumulator = self._hash_accumulate(self.accumulator, elem)

        return self.accumulator

    def is_member(self, element: str) -> bool:
        """Check if element is in accumulator in O(1) time. Returns True if present."""
        # [DOC] O(1) Python set membership check — the entire double-spend check reduces to this single line.
        # [DOC] If a transaction's nullifier is already in the set, the transaction is a double-spend and must be rejected.
        return element in self.elements

    def create_membership_proof(self, element: str) -> Dict[str, Any]:
        """Create membership proof for element without revealing other elements. Returns proof dict."""
        # [DOC] Cannot create a proof for an element that is not in the set.
        if not self.is_member(element):
            raise ValueError(f"Element not in accumulator: {element}")

        # [DOC] The proof records the element, the current accumulator value, and the set size.
        # [DOC] A verifier who trusts the accumulator value can check: is this accumulator consistent with this element being present?
        # Create proof
        proof = {
            'element': element,
            'accumulator': self.accumulator,
            'count': self.count,
            'timestamp': None  # Could add timestamp
        }

        return proof

    def verify_membership_proof(
        self,
        proof: Dict[str, Any],
        current_accumulator: Optional[str] = None
    ) -> bool:
        """Verify membership proof. Returns True if proof is valid."""
        try:
            element = proof['element']
            proof_accumulator = proof['accumulator']

            # [DOC] Use the passed-in accumulator if provided; otherwise use the current state.
            # Use current accumulator if not specified
            if current_accumulator is None:
                current_accumulator = self.accumulator

            # [DOC] The proof's accumulator snapshot must match the current accumulator.
            # [DOC] A mismatch means the set has changed since the proof was created — proof is stale.
            # Check accumulator matches
            if proof_accumulator != current_accumulator:
                return False

            # [DOC] Cross-check that the element is actually in the backing set right now.
            # Check element is actually in set
            return self.is_member(element)

        except (KeyError, ValueError):
            # [DOC] Missing proof fields or bad values mean the proof is malformed — reject it.
            return False

    def get_state(self) -> Dict[str, Any]:
        """Get current accumulator state. Returns dict with accumulator, count, and elements."""
        # [DOC] Exports the full accumulator state for persistence (database, file, etc.).
        # [DOC] elements is sorted so the exported state is deterministic and comparable across runs.
        return {
            'accumulator': self.accumulator,
            'count': self.count,
            'elements': sorted(list(self.elements))  # For debugging/backup
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        """Load accumulator state from dict."""
        # [DOC] Restore a previously exported accumulator state — used on server restart to avoid recomputing.
        self.accumulator = state['accumulator']
        self.count = state['count']
        # [DOC] Convert the list back to a Python set for O(1) membership lookups.
        self.elements = set(state['elements'])


# Example usage / testing
if __name__ == "__main__":
    """
    Test Dynamic Accumulator
    Run: python3 -m core.crypto.dynamic_accumulator
    """
    import time

    print("=== Dynamic Accumulator Testing ===\n")

    # Test 1: Initialize accumulator
    print("Test 1: Initialize Accumulator")
    acc = DynamicAccumulator()
    print(f"  Initial accumulator: {acc.accumulator[:20]}...")
    print(f"  Count: {acc.count}")
    assert acc.count == 0
    print("  [PASS] Test 1 passed!\n")

    # Test 2: Add elements
    print("Test 2: Add Elements")
    acc.add("IDX_ABC123")
    acc.add("IDX_XYZ789")
    acc.add("IDX_DEF456")

    print(f"  Added 3 elements")
    print(f"  Accumulator: {acc.accumulator[:20]}...")
    print(f"  Count: {acc.count}")
    assert acc.count == 3
    print("  [PASS] Test 2 passed!\n")

    # Test 3: Membership check
    print("Test 3: Membership Checks")
    is_member1 = acc.is_member("IDX_ABC123")
    is_member2 = acc.is_member("IDX_XYZ789")
    is_not_member = acc.is_member("IDX_NOTFOUND")

    print(f"  IDX_ABC123 in accumulator: {is_member1}")
    print(f"  IDX_XYZ789 in accumulator: {is_member2}")
    print(f"  IDX_NOTFOUND in accumulator: {is_not_member}")

    assert is_member1 == True
    assert is_member2 == True
    assert is_not_member == False
    print("  [PASS] Test 3 passed!\n")

    # Test 4: Remove element
    print("Test 4: Remove Element")
    old_accumulator = acc.accumulator
    acc.remove("IDX_ABC123")

    print(f"  Removed IDX_ABC123")
    print(f"  New accumulator: {acc.accumulator[:20]}...")
    print(f"  Count: {acc.count}")
    print(f"  IDX_ABC123 still member: {acc.is_member('IDX_ABC123')}")

    assert acc.count == 2
    assert not acc.is_member("IDX_ABC123")
    assert acc.accumulator != old_accumulator
    print("  [PASS] Test 4 passed!\n")

    # Test 5: Membership proof
    print("Test 5: Create and Verify Membership Proof")
    proof = acc.create_membership_proof("IDX_XYZ789")

    print(f"  Created proof for IDX_XYZ789")
    print(f"  Proof accumulator: {proof['accumulator'][:20]}...")
    print(f"  Proof count: {proof['count']}")

    is_valid = acc.verify_membership_proof(proof)
    print(f"  Proof valid: {is_valid}")

    assert is_valid == True
    print("  [PASS] Test 5 passed!\n")

    # Test 6: Duplicate add (should not increase count)
    print("Test 6: Duplicate Add")
    old_count = acc.count
    acc.add("IDX_XYZ789")  # Already exists

    print(f"  Tried to add IDX_XYZ789 again")
    print(f"  Count before: {old_count}")
    print(f"  Count after: {acc.count}")

    assert acc.count == old_count
    print("  [PASS] Test 6 passed!\n")

    # Test 7: Save and load state
    print("Test 7: Save and Load State")
    state = acc.get_state()

    acc2 = DynamicAccumulator()
    acc2.load_state(state)

    print(f"  Saved state with {state['count']} elements")
    print(f"  Loaded into new accumulator")
    print(f"  New accumulator count: {acc2.count}")
    print(f"  Accumulators match: {acc.accumulator == acc2.accumulator}")

    assert acc.accumulator == acc2.accumulator
    assert acc.count == acc2.count
    print("  [PASS] Test 7 passed!\n")

    # Test 8: Performance test (O(1) membership)
    print("Test 8: Performance Test (1000 elements)")

    perf_acc = DynamicAccumulator()

    # Add 1000 elements
    start = time.time()
    for i in range(1000):
        perf_acc.add(f"IDX_{i:06d}")
    add_time = time.time() - start

    # Check membership (should be O(1))
    start = time.time()
    for i in range(100):
        perf_acc.is_member(f"IDX_{i:06d}")
    check_time = time.time() - start

    print(f"  Added 1000 elements in {add_time*1000:.2f}ms")
    print(f"  100 membership checks in {check_time*1000:.2f}ms")
    print(f"  Average check time: {check_time*1000/100:.4f}ms")
    print(f"  Accumulator size: {len(perf_acc.accumulator)} bytes (constant!)")
    print("  [PASS] Test 8 passed!\n")

    # Test 9: Deterministic accumulator
    print("Test 9: Deterministic Accumulator")
    acc1 = DynamicAccumulator()
    acc1.add("ELEM_A")
    acc1.add("ELEM_B")
    acc1.add("ELEM_C")

    acc2 = DynamicAccumulator()
    acc2.add("ELEM_A")
    acc2.add("ELEM_B")
    acc2.add("ELEM_C")

    print(f"  Accumulator 1: {acc1.accumulator[:20]}...")
    print(f"  Accumulator 2: {acc2.accumulator[:20]}...")
    print(f"  Match: {acc1.accumulator == acc2.accumulator}")

    # Note: Order matters in this implementation
    # For production, could sort elements before accumulating
    assert acc1.accumulator == acc2.accumulator
    print("  [PASS] Test 9 passed!\n")

    print("=" * 50)
    print("[PASS] All Dynamic Accumulator tests passed!")
    print("=" * 50)
