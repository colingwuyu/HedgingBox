from hb.market_env.rewardrules import pnl_reward
import dm_env
from acme import types
from typing import Dict


class PnLQMeasureReward(pnl_reward.PnLReward):
    def __init__(self, scale_k: float = 0.5):
        """Constructor of PnL with Squared PnL Penalty Reward
           $Reward = -|PnL-r*stock_holding| - k*(PnL)^2$

        Args:
            scale_k (float): scaling factor for squared PnL Penalty term
        """
        self._scale_k = scale_k
        super().__init__()

    def step_reward(self, step_type: dm_env.StepType,
                    next_step_obs: Dict, action: types.NestedArray) -> types.NestedArray:
        pnl = super().step_reward(step_type, next_step_obs, action)
        pnl_qmeasure = - \
            abs(pnl - next_step_obs['interest_rate'] *
                self._this_step_obs['stock_holding']) - self._scale_k*pnl**2
        return pnl_qmeasure