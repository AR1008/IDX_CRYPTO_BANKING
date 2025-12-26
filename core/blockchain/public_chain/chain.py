"""
Public Blockchain Chain - Complete Blockchain Manager
Purpose: Manages the entire public blockchain

Responsibilities:
1. Maintain chain of blocks (linked list)
2. Add new blocks with mining
3. Validate entire chain integrity
4. Handle chain reorganization (if needed)
5. Provide chain statistics and queries

Privacy Model (Public Chain):
- Stores: Transaction hashes only
- Shows: Proof that transaction occurred
- Hides: Who sent to whom, amounts, banks
- Purpose: Immutable record + miner rewards

Example:
    >>> # Create new blockchain
    >>> chain = Blockchain()
    >>> 
    >>> # Add transactions
    >>> chain.add_block(["TX_ABC123", "TX_DEF456"])
    >>> 
    >>> # Validate
    >>> assert chain.is_valid()
"""

import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from core.blockchain.public_chain.block import Block
from config.settings import settings
import time

class Blockchain:
    """
    Manages the complete public blockchain
    
    Structure:
        Genesis Block (index 0, prev="0")
        ↓
        Block 1 (index 1, prev=genesis.hash)
        ↓
        Block 2 (index 2, prev=block1.hash)
        ↓
        ...
    
    Features:
    - Automatic genesis block creation
    - Mining with configurable difficulty
    - Chain validation
    - Block retrieval by index/hash
    - Chain statistics
    
    Example:
        >>> blockchain = Blockchain()
        >>> blockchain.add_block(["TX_123", "TX_456"])
        ✅ Block #1 mined!
        >>> 
        >>> print(f"Chain length: {blockchain.get_length()}")
        Chain length: 2  # Genesis + Block 1
    """
    
    def __init__(self, difficulty: int = None):
        """
        Initialize blockchain with genesis block
        
        Args:
            difficulty (int, optional): Mining difficulty
                                       Default: From settings (4)
        
        Example:
            >>> # Use default difficulty from settings
            >>> chain1 = Blockchain()
            >>> 
            >>> # Use custom difficulty
            >>> chain2 = Blockchain(difficulty=5)
        """
        self.chain: List[Block] = []
        self.difficulty = difficulty or settings.POW_DIFFICULTY
        
        # Create genesis block (first block in chain)
        self._create_genesis_block()
    
    
    def _create_genesis_block(self) -> None:
        """
        Create the genesis block (first block in blockchain)
        
        Genesis Block Properties:
        - Index: 0
        - Previous Hash: "0" (no previous block)
        - Transactions: [] (empty)
        - Mined with current difficulty
        
        This runs automatically when Blockchain is created
        """
        print("Creating genesis block...")
        
        genesis_block = Block(
            index=0,
            transactions=[],
            previous_hash="0",
            timestamp=time.time()  # Fixed timestamp
        )
        
        # Mine genesis block
        genesis_block.mine_block(difficulty=self.difficulty)
        
        # Add to chain
        self.chain.append(genesis_block)
        
        print(f"✅ Genesis block created: {genesis_block.hash[:40]}...\n")
    
    
    def get_latest_block(self) -> Block:
        """
        Get the most recent block in the chain
        
        Returns:
            Block: Latest block
        
        Example:
            >>> blockchain = Blockchain()
            >>> latest = blockchain.get_latest_block()
            >>> print(f"Latest block: #{latest.index}")
            Latest block: #0  # Genesis block
        """
        return self.chain[-1]
    
    
    def add_block(self, transactions: List[str]) -> Block:
        """
        Add a new block to the blockchain
        
        Process:
        1. Get latest block
        2. Create new block with:
           - Index: latest.index + 1
           - Previous hash: latest.hash
           - Transactions: provided list
        3. Mine the new block
        4. Validate it
        5. Add to chain
        
        Args:
            transactions (List[str]): Transaction hashes
                                     Example: ["TX_ABC123", "TX_DEF456"]
        
        Returns:
            Block: The newly added block
        
        Example:
            >>> blockchain = Blockchain()
            >>> 
            >>> # Add block with transactions
            >>> new_block = blockchain.add_block([
            ...     "TX_ABC123",
            ...     "TX_DEF456"
            ... ])
            ✅ Block #1 mined!
            >>> 
            >>> print(f"Block added: #{new_block.index}")
            Block added: #1
        """
        # Get latest block to link to
        latest_block = self.get_latest_block()
        
        # Create new block
        new_block = Block(
            index=latest_block.index + 1,
            transactions=transactions,
            previous_hash=latest_block.hash
        )
        
        # Mine the block (find valid nonce)
        new_block.mine_block(difficulty=self.difficulty)
        
        # Validate before adding
        if not new_block.is_valid(difficulty=self.difficulty):
            raise ValueError("Invalid block - validation failed!")
        
        # Verify it links to previous block
        if new_block.previous_hash != latest_block.hash:
            raise ValueError("Block doesn't link to previous block!")
        
        # Add to chain
        self.chain.append(new_block)
        
        return new_block
    
    
    def is_valid(self) -> bool:
        """
        Validate the entire blockchain
        
        Checks:
        1. Genesis block is valid
        2. Each block's hash is valid
        3. Each block links to previous block
        4. No tampering detected
        
        Returns:
            bool: True if entire chain is valid
        
        Example:
            >>> blockchain = Blockchain()
            >>> blockchain.add_block(["TX_123"])
            >>> 
            >>> # Validate chain
            >>> assert blockchain.is_valid()  # ✅
            >>> 
            >>> # Tamper with a block
            >>> blockchain.chain[0].transactions = ["FAKE"]
            >>> assert not blockchain.is_valid()  # ❌
        """
        # Check each block in the chain
        for i in range(len(self.chain)):
            current_block = self.chain[i]
            
            # Validate block itself
            if not current_block.is_valid(difficulty=self.difficulty):
                print(f"❌ Block #{i} is invalid!")
                return False
            
            # Check linkage (except genesis block)
            if i > 0:
                previous_block = self.chain[i - 1]
                
                if current_block.previous_hash != previous_block.hash:
                    print(f"❌ Block #{i} doesn't link to previous block!")
                    print(f"   Expected: {previous_block.hash}")
                    print(f"   Got: {current_block.previous_hash}")
                    return False
        
        # All checks passed!
        return True
    
    
    def get_block_by_index(self, index: int) -> Optional[Block]:
        """
        Get block by its index number
        
        Args:
            index (int): Block number (0 = genesis)
        
        Returns:
            Block or None: Block if found, None otherwise
        
        Example:
            >>> blockchain = Blockchain()
            >>> genesis = blockchain.get_block_by_index(0)
            >>> print(f"Genesis: {genesis.hash[:20]}...")
        """
        if 0 <= index < len(self.chain):
            return self.chain[index]
        return None
    
    
    def get_block_by_hash(self, block_hash: str) -> Optional[Block]:
        """
        Get block by its hash
        
        Args:
            block_hash (str): Block's hash
        
        Returns:
            Block or None: Block if found, None otherwise
        
        Example:
            >>> blockchain = Blockchain()
            >>> latest = blockchain.get_latest_block()
            >>> 
            >>> # Find by hash
            >>> found = blockchain.get_block_by_hash(latest.hash)
            >>> assert found.index == latest.index
        """
        for block in self.chain:
            if block.hash == block_hash:
                return block
        return None
    
    
    def get_length(self) -> int:
        """
        Get total number of blocks in chain
        
        Returns:
            int: Chain length (includes genesis)
        
        Example:
            >>> blockchain = Blockchain()
            >>> print(blockchain.get_length())
            1  # Just genesis
            >>> 
            >>> blockchain.add_block(["TX_123"])
            >>> print(blockchain.get_length())
            2  # Genesis + 1 block
        """
        return len(self.chain)
    
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get blockchain statistics
        
        Returns:
            Dict: Statistics including:
                - total_blocks: Number of blocks
                - total_transactions: Total transactions
                - genesis_hash: Genesis block hash
                - latest_hash: Latest block hash
                - difficulty: Current mining difficulty
        
        Example:
            >>> blockchain = Blockchain()
            >>> blockchain.add_block(["TX_1", "TX_2"])
            >>> stats = blockchain.get_statistics()
            >>> print(f"Blocks: {stats['total_blocks']}")
            Blocks: 2
        """
        total_transactions = sum(
            len(block.transactions) for block in self.chain
        )
        
        return {
            'total_blocks': len(self.chain),
            'total_transactions': total_transactions,
            'genesis_hash': self.chain[0].hash,
            'latest_hash': self.get_latest_block().hash,
            'difficulty': self.difficulty,
            'is_valid': self.is_valid()
        }
    
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert entire blockchain to dictionary
        
        Returns:
            Dict: Blockchain data for JSON serialization
        
        Example:
            >>> blockchain = Blockchain()
            >>> data = blockchain.to_dict()
            >>> 
            >>> import json
            >>> json_str = json.dumps(data, indent=2)
        """
        return {
            'chain': [block.to_dict() for block in self.chain],
            'difficulty': self.difficulty,
            'length': len(self.chain)
        }
    
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Blockchain':
        """
        Reconstruct blockchain from dictionary
        
        Args:
            data (Dict): Blockchain data
        
        Returns:
            Blockchain: Reconstructed blockchain
        
        Example:
            >>> # Save blockchain
            >>> blockchain = Blockchain()
            >>> data = blockchain.to_dict()
            >>> 
            >>> # Load blockchain
            >>> restored = Blockchain.from_dict(data)
            >>> assert restored.is_valid()
        """
        blockchain = Blockchain.__new__(Blockchain)
        blockchain.difficulty = data['difficulty']
        blockchain.chain = [
            Block.from_dict(block_data) 
            for block_data in data['chain']
        ]
        return blockchain
    
    
    def __repr__(self) -> str:
        """String representation of blockchain"""
        return (
            f"Blockchain(length={len(self.chain)}, "
            f"difficulty={self.difficulty}, "
            f"latest={self.get_latest_block().hash[:16]}...)"
        )


# ==========================================
# EXAMPLE USAGE & TESTING
# ==========================================

if __name__ == "__main__":
    """
    Test the Blockchain class
    Run: python3 -m core.blockchain.public_chain.chain
    """
    print("=== Public Blockchain Chain Testing ===\n")
    
    # Test 1: Create blockchain with genesis
    print("Test 1: Create Blockchain")
    blockchain = Blockchain()
    print(f"  Chain length: {blockchain.get_length()}")
    print(f"  Genesis hash: {blockchain.get_latest_block().hash[:40]}...")
    print(f"  ✅ Test 1 passed!\n")
    
    # Test 2: Add first block
    print("Test 2: Add First Block")
    block1 = blockchain.add_block(["TX_ABC123", "TX_DEF456"])
    print(f"  Block 1 added: #{block1.index}")
    print(f"  Transactions: {block1.transactions}")
    print(f"  Chain length: {blockchain.get_length()}")
    print(f"  ✅ Test 2 passed!\n")
    
    # Test 3: Add second block
    print("Test 3: Add Second Block")
    block2 = blockchain.add_block(["TX_GHI789", "TX_JKL012"])
    print(f"  Block 2 added: #{block2.index}")
    print(f"  Chain length: {blockchain.get_length()}")
    print(f"  ✅ Test 3 passed!\n")
    
    # Test 4: Validate chain
    print("Test 4: Validate Chain")
    is_valid = blockchain.is_valid()
    print(f"  Chain valid: {is_valid}")
    assert is_valid, "Chain should be valid!"
    print(f"  ✅ Test 4 passed!\n")
    
    # Test 5: Get blocks by index
    print("Test 5: Get Blocks by Index")
    genesis = blockchain.get_block_by_index(0)
    first = blockchain.get_block_by_index(1)
    print(f"  Genesis: Block #{genesis.index}")
    print(f"  First: Block #{first.index}")
    assert genesis.index == 0
    assert first.index == 1
    print(f"  ✅ Test 5 passed!\n")
    
    # Test 6: Get block by hash
    print("Test 6: Get Block by Hash")
    found_block = blockchain.get_block_by_hash(block1.hash)
    print(f"  Searching for: {block1.hash[:40]}...")
    print(f"  Found: Block #{found_block.index}")
    assert found_block.index == block1.index
    print(f"  ✅ Test 6 passed!\n")
    
    # Test 7: Chain statistics
    print("Test 7: Chain Statistics")
    stats = blockchain.get_statistics()
    print(f"  Total blocks: {stats['total_blocks']}")
    print(f"  Total transactions: {stats['total_transactions']}")
    print(f"  Difficulty: {stats['difficulty']}")
    print(f"  Valid: {stats['is_valid']}")
    print(f"  ✅ Test 7 passed!\n")
    
    # Test 8: Detect tampering
    print("Test 8: Detect Tampering")
    # Save original transaction
    original_tx = block1.transactions[0]
    
    # Tamper with block
    block1.transactions[0] = "TX_FAKE_HACKER"
    
    # Chain should now be invalid
    is_valid_after_tamper = blockchain.is_valid()
    print(f"  Tampered with Block 1")
    print(f"  Chain still valid? {is_valid_after_tamper}")
    assert not is_valid_after_tamper, "Should detect tampering!"
    
    # Restore
    block1.transactions[0] = original_tx
    block1.hash = block1.calculate_hash()  # Recalculate hash
    print(f"  ✅ Test 8 passed! Tampering detected!\n")
    
    # Test 9: Serialization
    print("Test 9: Serialize & Deserialize")
    data = blockchain.to_dict()
    restored = Blockchain.from_dict(data)
    
    print(f"  Original length: {blockchain.get_length()}")
    print(f"  Restored length: {restored.get_length()}")
    print(f"  Restored valid: {restored.is_valid()}")
    assert restored.get_length() == blockchain.get_length()
    assert restored.is_valid()
    print(f"  ✅ Test 9 passed!\n")
    
    print("=" * 50)
    print("✅ All Blockchain tests passed!")
    print("")
    print("Final Blockchain State:")
    for i, block in enumerate(blockchain.chain):
        print(f"  Block #{i}: {len(block.transactions)} transactions, "
              f"hash={block.hash[:20]}...")
    print("=" * 50)