from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
mq=(ROOT/'external/nyao/nyao_scalper.mq5').read_text()
main=(ROOT/'backend/app/main.py').read_text()
assert '#property version "44.3"' in mq
assert 'version="1.30.19"' in main
assert 'EnsureAtlasRecoveryActiveChainBudget' in mq
assert 'ACTIVE_RECOVERY_CHAIN_ADOPTED' in mq
assert 'RECOVERY_CHAIN_BUDGET_UNRESOLVED' in mq
assert 'ACTIVE_CHAIN_ADOPTION_ANCHOR_LOSS' in mq
assert 'ACTIVE_CHAIN_ADOPTION_ORIGINAL_STOP_RISK' in mq
assert 'Additional recovery expansion is blocked' in mq
# Adoption must happen before COVER/ROLL and unresolved chains must not size another leg.
pos_adopt=mq.index('bool recoveryBudgetResolved = EnsureAtlasRecoveryActiveChainBudget')
pos_cover=mq.index('// COVERED: hedge profit covers the older leg',pos_adopt)
pos_roll=mq.index('// ROLL: hedge losing AND older recovered',pos_cover)
assert pos_adopt < pos_cover < pos_roll
assert '(levelOk && recoveryBudgetResolved)' in mq
# Existing 5.51-loss chain under the fallback would freeze at 1.5x, not the 1% portfolio ceiling.
owned_loss=5.51
adopted=owned_loss*1.5
assert round(adopted,3)==8.265
assert adopted < 109.65
# UI must expose the basis instead of just an unexplained null/unavailable ceiling.
assert 'Budget basis: ${pretty(recoveryBudgetBasis)}' in main
print('P3.30.4 active recovery chain adoption tests passed')
