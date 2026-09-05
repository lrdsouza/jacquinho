"""Budget arithmetic and the conditional block, without a database."""

import pytest

from app.domain.catalogue import BlockReason


@pytest.mark.parametrize(
    'reason', [BlockReason.MISSING_EQUIPMENT, BlockReason.MISSING_TECHNIQUE,
               BlockReason.OVER_BUDGET, BlockReason.TOO_EXPENSIVE],
)
def test_capability_blocks_can_be_lifted(reason):
    assert BlockReason.is_conditional(reason)


@pytest.mark.parametrize('reason', [BlockReason.DISLIKED, BlockReason.IMPEDIMENT])
def test_taste_is_not_a_problem_waiting_to_be_solved(reason):
    """She is allowed to simply not want to cook something."""
    assert not BlockReason.is_conditional(reason)


def test_every_reason_is_declared():
    assert len(BlockReason.ALL) == 6
    assert BlockReason.CONDITIONAL <= set(BlockReason.ALL)
