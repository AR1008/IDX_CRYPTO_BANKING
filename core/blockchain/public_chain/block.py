"""
Public Blockchain Block - Proof of Work Mining
Purpose: Individual block in the public blockchain

Block Structure:
┌─────────────────────────────────────────┐
│ Block #1234                              │
├─────────────────────────────────────────┤
│ Previous Hash: 0000abc123def456...      │ ← Links to Block #1233
│ Timestamp: 2025-12-21 22:45:30.123      │
│ Transactions: [TX_ABC123, TX_DEF456]    │ ← Transaction hashes only!
│ Nonce: 47234                            │ ← Found by mining
│ Difficulty: 4                           │
│ Hash: 0000xyz789ghi012...               │ ← Starts with "0000"
└─────────────────────────────────────────┘

Privacy Model (Public Chain):
✅ Shows: Transaction hash (TX_ABC123)
✅ Shows: Session IDs are encrypted on private chain
❌ Hides: Real identities (no IDX, no names)
❌ Hides: Transaction amounts
❌ Hides: Which banks involved

Example:
    >>> # Create a new block
    >>> block = Block(
    ...     index=1,
    ...     transactions=["TX_ABC123", "TX_DEF456"],
    ...     previous_hash="0000abc123def456"
    ... )
    >>>
    >>> # Mine the block (find valid nonce)
    >>> block.mine_block(difficulty=4)
    >>>
    >>> # Verify it's valid
    >>> assert block.hash.startswith("0000")
    >>> print(f"Block mined! Nonce: {block.nonce}")
"""

# [DOC] hashlib provides SHA-256 — the hash function used both for block hashing and Proof of Work
import hashlib
# [DOC] json converts the block's Python dict to a deterministic string before hashing
import json
# [DOC] time provides time.time() (Unix timestamp) for recording when the block was created
import time
# [DOC] Type hints make function signatures self-documenting — List, Dict, Any are used below
from typing import List, Dict, Any
# [DOC] datetime is imported but not used directly in this file (may be used by callers of to_dict)
from datetime import datetime


class Block:
    """
    Represents a single block in the public blockchain

    Each block contains:
    - index: Block number (0, 1, 2, 3...)
    - timestamp: When block was created
    - transactions: List of transaction hashes
    - previous_hash: Hash of previous block (creates chain)
    - nonce: Number found by mining (proof of work)
    - hash: SHA-256 hash of entire block

    Security Properties:
    - Immutable: Changing data requires re-mining
    - Linked: Each block references previous block
    - Verified: Hash must start with required zeros
    - Timestamped: Cannot backdate or future-date

    Example:
        >>> # Genesis block (first block)
        >>> genesis = Block(
        ...     index=0,
        ...     transactions=[],
        ...     previous_hash="0"
        ... )
        >>> genesis.mine_block(difficulty=4)
        >>>
        >>> # Second block
        >>> block2 = Block(
        ...     index=1,
        ...     transactions=["TX_ABC123"],
        ...     previous_hash=genesis.hash
        ... )
        >>> block2.mine_block(difficulty=4)
    """

    def __init__(
        self,
        index: int,
        transactions: List[str],
        previous_hash: str,
        timestamp: float = None,
        nonce: int = 0
    ):
        """
        Initialize a new block

        Args:
            index (int): Block number in the chain
                        Genesis block = 0, next = 1, etc.

            transactions (List[str]): List of transaction hashes
                                     Format: ["TX_ABC123", "TX_DEF456"]
                                     Privacy: Only hashes, no actual data!

            previous_hash (str): Hash of previous block
                                Genesis block uses "0"
                                Others use actual hash

            timestamp (float, optional): Unix timestamp
                                        Auto-generated if not provided

            nonce (int, optional): Proof of work number
                                  Set to 0 initially, found by mining

        Example:
            >>> block = Block(
            ...     index=1,
            ...     transactions=["TX_ABC123"],
            ...     previous_hash="0000abc123def456"
            ... )
            >>> print(f"Block {block.index} created")
            Block 1 created
        """
        # [DOC] Store the block number — blocks are numbered sequentially starting from 0 (genesis)
        self.index = index
        # [DOC] Use the provided timestamp or call time.time() to record the current Unix time (seconds since 1970)
        self.timestamp = timestamp if timestamp is not None else time.time()
        # [DOC] transactions contains ONLY SHA-256 hashes of transactions — no amounts, no identities (public chain privacy model)
        self.transactions = transactions  # List of transaction hashes
        # [DOC] previous_hash links this block to the one before it — changing any earlier block breaks all subsequent hashes
        self.previous_hash = previous_hash
        # [DOC] nonce starts at 0 and is incremented during mining until the block hash meets the difficulty target
        self.nonce = nonce  # Will be found by mining

        # [DOC] Compute the initial hash from all fields above — at this point the hash likely does NOT meet the PoW target yet
        # Hash is calculated after all other fields are set
        # Initially calculated without mining (won't have leading zeros)
        self.hash = self.calculate_hash()


    def calculate_hash(self) -> str:
        """
        Calculate SHA-256 hash of the block

        Process:
        1. Create dictionary with all block data
        2. Convert to JSON string (deterministic ordering)
        3. Encode to bytes
        4. Hash with SHA-256
        5. Return hex string

        Returns:
            str: 64-character hexadecimal hash

        Important:
            - Same data → Always same hash (deterministic)
            - Different nonce → Different hash
            - This is called multiple times during mining

        Example:
            >>> block = Block(0, [], "0")
            >>> hash1 = block.calculate_hash()
            >>> hash2 = block.calculate_hash()
            >>> assert hash1 == hash2  # Deterministic!
            >>>
            >>> block.nonce = 1  # Change nonce
            >>> hash3 = block.calculate_hash()
            >>> assert hash1 != hash3  # Different hash!
        """
        # [DOC] Assemble all block fields into a dict — every field must be included so the hash covers the entire block
        # Create dictionary with all block data
        # Order matters for deterministic hashing
        block_dict = {
            'index': self.index,
            'timestamp': self.timestamp,
            'transactions': self.transactions,
            'previous_hash': self.previous_hash,
            'nonce': self.nonce
        }

        # [DOC] sort_keys=True ensures the JSON string is identical regardless of Python dict insertion order (deterministic)
        # Convert to JSON string with sorted keys (deterministic)
        # sort_keys=True ensures same order every time
        block_string = json.dumps(block_dict, sort_keys=True)

        # [DOC] SHA-256 operates on raw bytes, not strings — encode() converts the JSON string to UTF-8 bytes
        # Encode to bytes (required for hashing)
        block_bytes = block_string.encode('utf-8')

        # [DOC] hashlib.sha256() creates a SHA-256 hash object and digests all the input bytes
        # Calculate SHA-256 hash
        hash_object = hashlib.sha256(block_bytes)

        # [DOC] hexdigest() returns the 256-bit hash as a 64-character lowercase hex string (e.g. "0000abc123...")
        # Return as hexadecimal string (64 characters)
        return hash_object.hexdigest()


    def mine_block(self, difficulty: int = 4) -> None:
        """
        Mine the block using Proof of Work

        Mining Process:
        1. Set target: "0000..." (number of zeros = difficulty)
        2. Try nonce = 0, calculate hash
        3. If hash starts with target → SUCCESS!
        4. Else, increment nonce and try again
        5. Repeat until valid hash found

        Args:
            difficulty (int): Number of leading zeros required
                             Default: 4 (= "0000")
                             Higher = harder mining

        Performance:
            - Difficulty 3: ~8,000 attempts, ~1 second
            - Difficulty 4: ~47,000 attempts, ~3-5 seconds
            - Difficulty 5: ~1,000,000 attempts, ~60 seconds
            - Difficulty 6: ~16,000,000 attempts, ~15 minutes

        Example:
            >>> block = Block(1, ["TX_ABC123"], "0000abc123")
            >>> print(f"Mining with difficulty {4}...")
            Mining with difficulty 4...
            >>>
            >>> block.mine_block(difficulty=4)
            >>> print(f"Block mined! Nonce: {block.nonce}")
            Block mined! Nonce: 47234
            >>>
            >>> print(f"Hash: {block.hash}")
            Hash: 0000xyz789abc...
        """
        # [DOC] target is a string of 'difficulty' zero characters — the hash must begin with this prefix to be valid
        # Create target string: "0000..." (difficulty zeros)
        target = "0" * difficulty

        # [DOC] Initialise attempt counter and start timer — used only for the statistics printout after mining
        # Mining loop: Try nonces until hash starts with target
        # This is computationally expensive (by design!)
        attempt = 0
        start_time = time.time()

        # [DOC] Keep looping as long as the current hash does NOT start with the required zeros
        while not self.hash.startswith(target):
            # [DOC] Increment nonce by 1 — this changes a field in the block dict, which will change the hash completely
            # Increment nonce
            self.nonce += 1

            # [DOC] Recompute the hash with the new nonce value — this is the core inner loop of Proof of Work
            # Recalculate hash with new nonce
            self.hash = self.calculate_hash()

            # [DOC] Count attempts purely for the statistics message printed after mining completes
            # Track attempts (for performance monitoring)
            attempt += 1

            # Optional: Print progress every 10,000 attempts
            # Uncomment for debugging
            # if attempt % 10000 == 0:
            #     print(f"  Attempt {attempt}: {self.hash[:10]}...")

        # [DOC] Record elapsed wall-clock time once a valid hash is found
        # Mining complete!
        elapsed = time.time() - start_time

        # Print mining statistics
        print(f"✅ Block #{self.index} mined!")
        print(f"   Nonce: {self.nonce:,}")
        print(f"   Attempts: {attempt:,}")
        print(f"   Time: {elapsed:.2f} seconds")
        print(f"   Hash: {self.hash[:40]}...")


    def is_valid(self, difficulty: int = 4) -> bool:
        """
        Validate block integrity

        Checks:
        1. Hash starts with required zeros (proof of work)
        2. Hash is correctly calculated (not tampered)
        3. Timestamp is reasonable (not too far in past/future)

        Args:
            difficulty (int): Number of leading zeros required

        Returns:
            bool: True if block is valid, False otherwise

        Example:
            >>> # Valid block
            >>> block = Block(1, ["TX_ABC123"], "0000abc123")
            >>> block.mine_block(difficulty=4)
            >>> assert block.is_valid(difficulty=4)  # ✅
            >>>
            >>> # Tampered block
            >>> block.transactions.append("TX_FAKE")  # Modify data
            >>> assert not block.is_valid(difficulty=4)  # ❌
        """
        # [DOC] Check 1: Proof of Work — the stored hash must begin with 'difficulty' zero digits
        # Check 1: Proof of work (hash starts with zeros)
        target = "0" * difficulty
        if not self.hash.startswith(target):
            print(f"❌ Invalid PoW: Hash doesn't start with {target}")
            return False

        # [DOC] Check 2: Integrity — recompute the hash from the block's current data and compare to the stored hash
        # [DOC] If any field was tampered with after mining, the recomputed hash will differ from the stored hash
        # Check 2: Hash integrity (recalculate and compare)
        calculated_hash = self.calculate_hash()
        if self.hash != calculated_hash:
            print(f"❌ Invalid hash: Stored != Calculated")
            print(f"   Stored: {self.hash}")
            print(f"   Calculated: {calculated_hash}")
            return False

        # [DOC] Check 3: Timestamp sanity — blocks more than 2 hours away from the current time are suspicious
        # [DOC] This prevents blocks with far-future timestamps from being accepted (time-warp attack mitigation)
        # Check 3: Reasonable timestamp (within 2 hours of now)
        current_time = time.time()
        time_diff = abs(current_time - self.timestamp)
        max_time_diff = 2 * 60 * 60  # 2 hours in seconds

        if time_diff > max_time_diff:
            print(f"❌ Invalid timestamp: {time_diff/3600:.1f} hours off")
            return False

        # [DOC] All three checks passed — the block is structurally valid
        # All checks passed!
        return True


    def to_dict(self) -> Dict[str, Any]:
        """
        Convert block to dictionary (for JSON serialization)

        Returns:
            Dict: Block data as dictionary

        Example:
            >>> block = Block(1, ["TX_ABC123"], "0000abc123")
            >>> block.mine_block(difficulty=4)
            >>> block_dict = block.to_dict()
            >>>
            >>> import json
            >>> json_string = json.dumps(block_dict, indent=2)
            >>> print(json_string)
            {
              "index": 1,
              "timestamp": 1734821450.123,
              "transactions": ["TX_ABC123"],
              "previous_hash": "0000abc123",
              "nonce": 47234,
              "hash": "0000xyz789..."
            }
        """
        # [DOC] Return all block fields as a plain Python dict — suitable for JSON serialisation or database storage
        return {
            'index': self.index,
            'timestamp': self.timestamp,
            'transactions': self.transactions,
            'previous_hash': self.previous_hash,
            'nonce': self.nonce,
            'hash': self.hash
        }


    @staticmethod
    def from_dict(block_dict: Dict[str, Any]) -> 'Block':
        """
        Create block from dictionary (for loading from database)

        Args:
            block_dict (Dict): Block data as dictionary

        Returns:
            Block: Reconstructed block object

        Example:
            >>> block_dict = {
            ...     'index': 1,
            ...     'timestamp': 1734821450.123,
            ...     'transactions': ["TX_ABC123"],
            ...     'previous_hash': "0000abc123",
            ...     'nonce': 47234,
            ...     'hash': "0000xyz789..."
            ... }
            >>>
            >>> block = Block.from_dict(block_dict)
            >>> print(f"Block {block.index} loaded")
            Block 1 loaded
        """
        # [DOC] Reconstruct the Block by passing all stored fields to __init__; timestamp and nonce restore the exact original state
        block = Block(
            index=block_dict['index'],
            transactions=block_dict['transactions'],
            previous_hash=block_dict['previous_hash'],
            timestamp=block_dict['timestamp'],
            nonce=block_dict['nonce']
        )

        # [DOC] Override the hash with the stored value — this avoids recomputing (and the result would match anyway for a valid block)
        # Set hash from dictionary (already mined)
        block.hash = block_dict['hash']

        return block


    def __repr__(self) -> str:
        """String representation of block"""
        # [DOC] __repr__ gives a concise summary useful in Python's interactive REPL and in log messages
        return (
            f"Block(index={self.index}, "
            f"hash={self.hash[:16]}..., "
            f"transactions={len(self.transactions)})"
        )


# ==========================================
# EXAMPLE USAGE & TESTING
# ==========================================

if __name__ == "__main__":
    """
    Test the Block class
    Run: python3 -m core.blockchain.public_chain.block
    """
    print("=== Public Blockchain Block Testing ===\n")

    # Test 1: Create genesis block (first block)
    print("Test 1: Create Genesis Block")
    genesis = Block(
        index=0,
        transactions=[],  # No transactions in genesis
        previous_hash="0"  # Genesis has no previous block
    )

    print(f"  Genesis block created")
    print(f"  Index: {genesis.index}")
    print(f"  Previous Hash: {genesis.previous_hash}")
    print(f"  Hash (before mining): {genesis.hash[:40]}...")
    print(f"  ✅ Test 1 passed!\n")

    # Test 2: Mine genesis block
    print("Test 2: Mine Genesis Block (Difficulty 4)")
    genesis.mine_block(difficulty=4)
    print(f"  Final hash: {genesis.hash}")
    assert genesis.hash.startswith("0000"), "Hash must start with 0000!"
    print(f"  ✅ Test 2 passed!\n")

    # Test 3: Create second block (links to genesis)
    print("Test 3: Create Second Block")
    block2 = Block(
        index=1,
        transactions=["TX_ABC123", "TX_DEF456"],
        previous_hash=genesis.hash  # Links to genesis!
    )

    print(f"  Block 2 created")
    print(f"  Index: {block2.index}")
    print(f"  Transactions: {block2.transactions}")
    print(f"  Previous Hash: {block2.previous_hash[:40]}...")
    print(f"  ✅ Test 3 passed!\n")

    # Test 4: Mine second block
    print("Test 4: Mine Second Block (Difficulty 4)")
    block2.mine_block(difficulty=4)
    assert block2.hash.startswith("0000"), "Hash must start with 0000!"
    print(f"  ✅ Test 4 passed!\n")

    # Test 5: Validate blocks
    print("Test 5: Validate Blocks")
    assert genesis.is_valid(difficulty=4), "Genesis should be valid!"
    assert block2.is_valid(difficulty=4), "Block 2 should be valid!"
    print(f"  Genesis block: Valid ✅")
    print(f"  Block 2: Valid ✅")
    print(f"  ✅ Test 5 passed!\n")

    # Test 6: Detect tampering
    print("Test 6: Detect Tampering")
    # Try to modify a transaction after mining
    original_hash = block2.hash
    block2.transactions.append("TX_FAKE_HACKER")

    is_still_valid = block2.is_valid(difficulty=4)
    print(f"  Added fake transaction")
    print(f"  Block still valid? {is_still_valid}")
    assert not is_still_valid, "Tampered block should be invalid!"

    # Restore original state
    block2.transactions.remove("TX_FAKE_HACKER")
    block2.hash = original_hash
    print(f"  ✅ Test 6 passed! Tampering detected!\n")

    # Test 7: Serialization (to/from dict)
    print("Test 7: Serialization")
    block_dict = block2.to_dict()
    reconstructed = Block.from_dict(block_dict)

    assert reconstructed.index == block2.index
    assert reconstructed.hash == block2.hash
    assert reconstructed.nonce == block2.nonce

    print(f"  Original: {block2}")
    print(f"  Reconstructed: {reconstructed}")
    print(f"  ✅ Test 7 passed!\n")

    # Test 8: Chain linkage
    print("Test 8: Verify Chain Linkage")
    print(f"  Genesis hash: {genesis.hash[:40]}...")
    print(f"  Block 2 previous: {block2.previous_hash[:40]}...")
    print(f"  Match: {genesis.hash == block2.previous_hash}")
    assert genesis.hash == block2.previous_hash, "Chain must be linked!"
    print(f"  ✅ Test 8 passed!\n")

    print("=" * 50)
    print("✅ All Block tests passed!")
    print("")
    print("Blockchain Summary:")
    print(f"  Genesis: Block #{genesis.index} ({genesis.hash[:20]}...)")
    print(f"  Block 2: Block #{block2.index} ({block2.hash[:20]}...)")
    print(f"  Chain linked: ✅")
    print(f"  Both validated: ✅")
    print("=" * 50)
