from genesis.devlab.iterative import IterativeGenesisDevLab


def test_iterative_devlab_keeps_reasoning_retries_bounded():
    assert IterativeGenesisDevLab.MAX_INNER_REVISIONS == 2
    assert IterativeGenesisDevLab.MAX_DEVLAB_PROPOSAL_ATTEMPTS == 2
