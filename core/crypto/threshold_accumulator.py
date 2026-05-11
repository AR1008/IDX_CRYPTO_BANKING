"""
Threshold Accumulator - Distributed control of account freeze/unfreeze with K-of-N voting.

Combines Dynamic Accumulator with threshold voting (8-of-12 banks) for distributed freeze operations.
Provides O(1) frozen status checks with full audit trail and distributed control.
"""

import hashlib
import secrets
import json
from typing import Dict, List, Any, Optional, Set
from enum import Enum
from datetime import datetime

# [DOC] Import the underlying O(1) hash-based accumulator that actually tracks the frozen set.
# [DOC] ThresholdAccumulatorManager wraps it with a voting layer so no single bank can freeze an account alone.
from core.crypto.dynamic_accumulator import DynamicAccumulator


class ProposalStatus(Enum):
    """Status of accumulator change proposal"""
    # [DOC] PENDING: the proposal exists but has not yet received enough votes to be approved or definitively rejected.
    PENDING = "pending"
    # [DOC] APPROVED: enough banks voted yes (>= threshold) — the proposal is ready to be executed.
    APPROVED = "approved"
    # [DOC] REJECTED: too many banks voted no — it is now mathematically impossible to reach the threshold.
    REJECTED = "rejected"
    # [DOC] EXECUTED: the approved proposal has been applied — the accumulator has actually been updated.
    EXECUTED = "executed"


class ThresholdAccumulatorManager:
    """Manage threshold accumulator for distributed freeze/unfreeze with K-of-N bank approval."""

    def __init__(
        self,
        num_banks: int = 12,
        threshold: int = 8
    ):
        """
        Initialize threshold accumulator manager

        Args:
            num_banks: Total number of banks
            threshold: Number of approvals needed
        """
        # [DOC] num_banks is the total consortium size N (default 12).
        # [DOC] No bank ID outside [1, num_banks] is considered valid.
        self.num_banks = num_banks
        # [DOC] threshold is the minimum number of approving banks needed for a proposal to pass (default 8).
        # [DOC] With N=12 and threshold=8, an attacker needs to compromise at least 8 banks to freeze an account.
        self.threshold = threshold

        # [DOC] freeze_accumulator holds the set of currently-frozen account IDXes using the DynamicAccumulator.
        # [DOC] is_frozen() reduces to a single O(1) set membership check in the underlying accumulator.
        # Freeze accumulator (contains frozen accounts)
        self.freeze_accumulator = DynamicAccumulator()

        # [DOC] proposals is an in-memory dict mapping proposal_id strings to proposal state dicts.
        # [DOC] In production this would be persisted to a database table for durability across restarts.
        # Proposals for accumulator changes
        self.proposals: Dict[str, Dict[str, Any]] = {}

        # [DOC] proposal_count is a simple integer counter used to generate sequential, unique proposal IDs.
        # Proposal counter
        self.proposal_count = 0

    def create_proposal(
        self,
        operation: str,
        target: str,
        reason: str,
        proposer_bank_id: int
    ) -> str:
        """
        Create proposal to change accumulator

        Args:
            operation: "FREEZE" or "UNFREEZE"
            target: Account IDX to freeze/unfreeze
            reason: Reason for operation
            proposer_bank_id: Bank proposing the change

        Returns:
            str: Proposal ID

        Example:
            >>> manager = ThresholdAccumulatorManager()
            >>> proposal_id = manager.create_proposal(
            ...     operation="FREEZE",
            ...     target="IDX_FRAUD_123",
            ...     reason="Suspected fraud",
            ...     proposer_bank_id=1
            ... )
        """
        # [DOC] Only "FREEZE" and "UNFREEZE" are valid operations — anything else is rejected immediately.
        # Validate operation
        if operation not in ["FREEZE", "UNFREEZE"]:
            raise ValueError(f"Invalid operation: {operation}")

        # [DOC] The proposing bank must be a valid consortium member (ID in [1, num_banks]).
        # Validate proposer
        if proposer_bank_id < 1 or proposer_bank_id > self.num_banks:
            raise ValueError(f"Invalid proposer bank ID: {proposer_bank_id}")

        # [DOC] Increment the counter first, then format it as a zero-padded 6-digit string.
        # [DOC] Example: first proposal gets PROP_000001, second gets PROP_000002, etc.
        # Create proposal ID
        self.proposal_count += 1
        proposal_id = f"PROP_{self.proposal_count:06d}"

        # [DOC] Build the proposal dict — this is the complete audit record for this freeze/unfreeze request.
        # [DOC] votes stores {bank_id: True/False} so each bank can only vote once.
        # [DOC] approvals and rejections are cached counts derived from votes for quick threshold comparison.
        # Create proposal
        proposal = {
            'proposal_id': proposal_id,
            'operation': operation,
            'target': target,
            'reason': reason,
            'proposer_bank_id': proposer_bank_id,
            'status': ProposalStatus.PENDING.value,
            'votes': {},  # bank_id -> approve/reject
            'approvals': 0,
            'rejections': 0,
            'created_at': datetime.now().isoformat(),
            'executed_at': None
        }

        # [DOC] Store the proposal in the in-memory dict keyed by its ID.
        self.proposals[proposal_id] = proposal

        return proposal_id

    def vote(
        self,
        proposal_id: str,
        bank_id: int,
        approve: bool
    ) -> Dict[str, Any]:
        """
        Bank votes on proposal

        Args:
            proposal_id: Proposal to vote on
            bank_id: Bank casting vote
            approve: True to approve, False to reject

        Returns:
            dict: Updated proposal

        Raises:
            ValueError: If proposal not found or bank already voted

        Example:
            >>> manager = ThresholdAccumulatorManager()
            >>> proposal_id = manager.create_proposal(
            ...     "FREEZE", "IDX_TEST", "Test", 1
            ... )
            >>> manager.vote(proposal_id, 2, approve=True)
        """
        # [DOC] Look up the proposal; raise if it doesn't exist to prevent voting on phantom proposals.
        # Validate proposal exists
        if proposal_id not in self.proposals:
            raise ValueError(f"Proposal not found: {proposal_id}")

        proposal = self.proposals[proposal_id]

        # [DOC] Prevent voting on a proposal that has already been resolved or executed.
        # [DOC] Once approved/rejected/executed, the vote tally is final — no re-voting allowed.
        # Check if already executed
        if proposal['status'] != ProposalStatus.PENDING.value:
            raise ValueError(
                f"Proposal {proposal_id} already {proposal['status']}"
            )

        # [DOC] Validate that the voting bank is a registered consortium member.
        # Validate bank ID
        if bank_id < 1 or bank_id > self.num_banks:
            raise ValueError(f"Invalid bank ID: {bank_id}")

        # [DOC] Each bank gets exactly one vote — check for duplicates and reject them.
        # [DOC] This prevents a compromised bank from voting multiple times to skew the result.
        # Check if bank already voted
        if bank_id in proposal['votes']:
            raise ValueError(
                f"Bank {bank_id} already voted on {proposal_id}"
            )

        # [DOC] Record this bank's vote as True (approve) or False (reject) in the votes dict.
        # Record vote
        proposal['votes'][bank_id] = approve

        # [DOC] Increment the appropriate running counter.
        # Update counts
        if approve:
            proposal['approvals'] += 1
        else:
            proposal['rejections'] += 1

        # [DOC] Check if the approval threshold has been reached — if so, mark the proposal APPROVED.
        # Check if threshold met
        if proposal['approvals'] >= self.threshold:
            proposal['status'] = ProposalStatus.APPROVED.value
        elif proposal['rejections'] > (self.num_banks - self.threshold):
            # [DOC] If the number of rejections exceeds (N - threshold), it is now impossible to collect enough approvals.
            # [DOC] Example: N=12, threshold=8. If 5 banks reject, at most 7 can approve — less than 8 — so reject immediately.
            # More rejections than possible to reach threshold
            proposal['status'] = ProposalStatus.REJECTED.value

        return proposal

    def execute_proposal(self, proposal_id: str) -> bool:
        """
        Execute approved proposal

        Args:
            proposal_id: Proposal to execute

        Returns:
            bool: True if executed successfully

        Raises:
            ValueError: If proposal not approved

        Example:
            >>> manager = ThresholdAccumulatorManager()
            >>> proposal_id = manager.create_proposal(
            ...     "FREEZE", "IDX_TEST", "Test", 1
            ... )
            >>> # Get 8 approvals
            >>> for i in range(1, 9):
            ...     manager.vote(proposal_id, i, approve=True)
            >>> manager.execute_proposal(proposal_id)
            True
        """
        # [DOC] Reject execution if the proposal doesn't exist in the registry.
        # Validate proposal exists
        if proposal_id not in self.proposals:
            raise ValueError(f"Proposal not found: {proposal_id}")

        proposal = self.proposals[proposal_id]

        # [DOC] Only APPROVED proposals can be executed — PENDING and REJECTED proposals are blocked.
        # Check if approved
        if proposal['status'] != ProposalStatus.APPROVED.value:
            raise ValueError(
                f"Proposal {proposal_id} not approved (status: {proposal['status']})"
            )

        # [DOC] Read the operation and target from the proposal and apply them to the accumulator.
        # Execute operation
        operation = proposal['operation']
        target = proposal['target']

        if operation == "FREEZE":
            # [DOC] Add the target IDX to the freeze accumulator — from this point is_frozen(target) returns True.
            self.freeze_accumulator.add(target)
        elif operation == "UNFREEZE":
            # [DOC] Remove the target IDX from the freeze accumulator — is_frozen(target) will return False again.
            self.freeze_accumulator.remove(target)
        else:
            raise ValueError(f"Unknown operation: {operation}")

        # [DOC] Mark the proposal as EXECUTED and record the execution timestamp for the audit trail.
        # Mark as executed
        proposal['status'] = ProposalStatus.EXECUTED.value
        proposal['executed_at'] = datetime.now().isoformat()

        return True

    def is_frozen(self, account_idx: str) -> bool:
        """
        Check if account is frozen

        O(1) operation

        Args:
            account_idx: Account IDX to check

        Returns:
            bool: True if account is frozen

        Example:
            >>> manager = ThresholdAccumulatorManager()
            >>> manager.is_frozen("IDX_TEST")
            False
        """
        # [DOC] Delegates directly to the underlying DynamicAccumulator's O(1) set membership check.
        # [DOC] This single line is the payoff for all the voting machinery above — checking freeze status is instant.
        return self.freeze_accumulator.is_member(account_idx)

    def get_frozen_accounts(self) -> List[str]:
        """
        Get list of all frozen accounts

        Returns:
            list: Frozen account IDXs

        Example:
            >>> manager = ThresholdAccumulatorManager()
            >>> manager.get_frozen_accounts()
            []
        """
        # [DOC] Return a sorted list of all IDXes currently in the freeze accumulator.
        # [DOC] sorted() ensures a deterministic order for display and testing — the set itself is unordered.
        return sorted(list(self.freeze_accumulator.elements))

    def get_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """
        Get proposal details

        Args:
            proposal_id: Proposal ID

        Returns:
            dict: Proposal details, or None if not found

        Example:
            >>> manager = ThresholdAccumulatorManager()
            >>> proposal_id = manager.create_proposal(
            ...     "FREEZE", "IDX_TEST", "Test", 1
            ... )
            >>> proposal = manager.get_proposal(proposal_id)
            >>> proposal['operation']
            'FREEZE'
        """
        # [DOC] dict.get() returns None if the proposal_id is not found — avoids a KeyError.
        return self.proposals.get(proposal_id)

    def get_all_proposals(self) -> List[Dict[str, Any]]:
        """
        Get all proposals

        Returns:
            list: All proposals

        Example:
            >>> manager = ThresholdAccumulatorManager()
            >>> manager.get_all_proposals()
            []
        """
        # [DOC] Return every proposal as a list — used for audit log display and administrative review.
        return list(self.proposals.values())


# Example usage / testing
if __name__ == "__main__":
    """
    Test Threshold Accumulator
    Run: python3 -m core.crypto.threshold_accumulator
    """
    print("=== Threshold Accumulator Testing ===\n")

    manager = ThresholdAccumulatorManager(num_banks=12, threshold=8)

    # Test 1: Create freeze proposal
    print("Test 1: Create Freeze Proposal")
    proposal_id = manager.create_proposal(
        operation="FREEZE",
        target="IDX_SUSPICIOUS_ABC123",
        reason="Suspected fraudulent activity",
        proposer_bank_id=1
    )

    print(f"  Created proposal: {proposal_id}")
    proposal = manager.get_proposal(proposal_id)
    print(f"  Target: {proposal['target']}")
    print(f"  Reason: {proposal['reason']}")
    print(f"  Status: {proposal['status']}")
    assert proposal['status'] == ProposalStatus.PENDING.value
    print("  [PASS] Test 1 passed!\n")

    # Test 2: Banks vote on proposal
    print("Test 2: Banks Vote on Proposal")
    # 8 banks approve (meets threshold)
    for bank_id in range(1, 9):
        manager.vote(proposal_id, bank_id, approve=True)
        print(f"  Bank {bank_id} approved")

    proposal = manager.get_proposal(proposal_id)
    print(f"  Approvals: {proposal['approvals']}")
    print(f"  Status: {proposal['status']}")
    assert proposal['approvals'] == 8
    assert proposal['status'] == ProposalStatus.APPROVED.value
    print("  [PASS] Test 2 passed!\n")

    # Test 3: Execute proposal
    print("Test 3: Execute Approved Proposal")
    success = manager.execute_proposal(proposal_id)

    print(f"  Execution success: {success}")
    print(f"  Account frozen: {manager.is_frozen('IDX_SUSPICIOUS_ABC123')}")

    proposal = manager.get_proposal(proposal_id)
    print(f"  Status: {proposal['status']}")

    assert success == True
    assert manager.is_frozen("IDX_SUSPICIOUS_ABC123") == True
    assert proposal['status'] == ProposalStatus.EXECUTED.value
    print("  [PASS] Test 3 passed!\n")

    # Test 4: Unfreeze proposal
    print("Test 4: Create and Execute Unfreeze Proposal")
    unfreeze_id = manager.create_proposal(
        operation="UNFREEZE",
        target="IDX_SUSPICIOUS_ABC123",
        reason="Investigation cleared, account safe",
        proposer_bank_id=2
    )

    # Get 8 approvals
    for bank_id in range(1, 9):
        manager.vote(unfreeze_id, bank_id, approve=True)

    manager.execute_proposal(unfreeze_id)

    print(f"  Created unfreeze proposal: {unfreeze_id}")
    print(f"  Account frozen: {manager.is_frozen('IDX_SUSPICIOUS_ABC123')}")

    assert manager.is_frozen("IDX_SUSPICIOUS_ABC123") == False
    print("  [PASS] Test 4 passed!\n")

    # Test 5: Rejected proposal (not enough votes)
    print("Test 5: Rejected Proposal (Insufficient Votes)")
    reject_id = manager.create_proposal(
        operation="FREEZE",
        target="IDX_INNOCENT_XYZ789",
        reason="Testing rejection",
        proposer_bank_id=3
    )

    # Only 3 banks approve (less than threshold of 8)
    for bank_id in range(1, 4):
        manager.vote(reject_id, bank_id, approve=True)

    # Enough banks reject to make threshold impossible
    # threshold=8, so need max 4 rejections to prevent reaching 8
    # After 5 rejections, it's automatically rejected
    for bank_id in range(4, 10):  # 6 rejections
        proposal = manager.get_proposal(reject_id)
        if proposal['status'] == ProposalStatus.REJECTED.value:
            break  # Already rejected, stop voting
        manager.vote(reject_id, bank_id, approve=False)

    proposal = manager.get_proposal(reject_id)
    print(f"  Approvals: {proposal['approvals']}")
    print(f"  Rejections: {proposal['rejections']}")
    print(f"  Status: {proposal['status']}")

    assert proposal['status'] == ProposalStatus.REJECTED.value

    # Should fail to execute
    try:
        manager.execute_proposal(reject_id)
        print("  ❌ Should have raised ValueError!")
        assert False
    except ValueError as e:
        print(f"  Correctly prevented execution: {e}")

    print("  [PASS] Test 5 passed!\n")

    # Test 6: Cannot vote twice
    print("Test 6: Cannot Vote Twice")
    double_vote_id = manager.create_proposal(
        operation="FREEZE",
        target="IDX_TEST_DOUBLE",
        reason="Test double voting",
        proposer_bank_id=1
    )

    manager.vote(double_vote_id, 1, approve=True)

    try:
        manager.vote(double_vote_id, 1, approve=True)
        print("  ❌ Should have raised ValueError!")
        assert False
    except ValueError as e:
        print(f"  Correctly prevented double voting: {e}")

    print("  [PASS] Test 6 passed!\n")

    # Test 7: Get frozen accounts list
    print("Test 7: Get Frozen Accounts List")
    # Freeze a few accounts
    for i in range(3):
        freeze_id = manager.create_proposal(
            operation="FREEZE",
            target=f"IDX_FROZEN_{i}",
            reason=f"Test freeze {i}",
            proposer_bank_id=1
        )

        for bank_id in range(1, 9):
            manager.vote(freeze_id, bank_id, approve=True)

        manager.execute_proposal(freeze_id)

    frozen = manager.get_frozen_accounts()
    print(f"  Frozen accounts: {frozen}")
    print(f"  Count: {len(frozen)}")

    assert len(frozen) == 3
    print("  [PASS] Test 7 passed!\n")

    # Test 8: Audit trail
    print("Test 8: Audit Trail")
    all_proposals = manager.get_all_proposals()

    print(f"  Total proposals: {len(all_proposals)}")

    executed_count = sum(
        1 for p in all_proposals
        if p['status'] == ProposalStatus.EXECUTED.value
    )
    rejected_count = sum(
        1 for p in all_proposals
        if p['status'] == ProposalStatus.REJECTED.value
    )

    print(f"  Executed: {executed_count}")
    print(f"  Rejected: {rejected_count}")

    assert len(all_proposals) > 0
    print("  [PASS] Test 8 passed!\n")

    print("=" * 50)
    print("[PASS] All Threshold Accumulator tests passed!")
    print("=" * 50)
    print()
    print("Key Features Demonstrated:")
    print("  • Distributed freeze/unfreeze control")
    print("  • Threshold voting (8 of 12 banks)")
    print("  • Proposal creation and execution")
    print("  • O(1) frozen status checks")
    print("  • Double voting prevention")
    print("  • Rejection when threshold not met")
    print("  • Complete audit trail")
    print()
    print("Use Cases:")
    print("  • Account freeze (fraud/sanctions)")
    print("  • Account unfreeze (investigation cleared)")
    print("  • Emergency controls")
    print("  • Regulatory compliance")
    print()
