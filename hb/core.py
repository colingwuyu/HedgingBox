from acme import core
from acme import types
from acme.utils import loggers
import dm_env
from hb.market_env.rewardrules import reward_rule
import abc
import numpy as np


class ActorAdapter(core.Actor):
    """Actor adapter to market environment reward, 
    which gives pnl in last position of timestep.observation
    """

    def __init__(self, actor: core.Actor):
        self._actor = actor

    def select_action(self, observation: types.NestedArray) -> types.NestedArray:
        return self._actor.select_action(observation[:-1])

    def observe_first(self, timestep: dm_env.TimeStep):
        new_timestep = dm_env.TimeStep(
            step_type=timestep.step_type,
            reward=timestep.reward,
            discount=timestep.discount,
            observation=timestep.observation[:-1]
        )
        self._actor.observe_first(new_timestep)

    def observe(
        self,
        action: types.NestedArray,
        next_timestep: dm_env.TimeStep,
    ):
        new_next_timestep = dm_env.TimeStep(
            step_type=next_timestep.step_type,
            reward=next_timestep.reward,
            discount=next_timestep.discount,
            observation=next_timestep.observation[:-1]
        )
        self._actor.observe(action, new_next_timestep)

    def update(self):
        self._actor.update()


class Predictor(core.Actor):
    """Predictor acts without exploration
       and records performance progress
    """

    def __init__(self,
                 actor: core.Actor,
                 num_train_per_pred: int,
                 logger: loggers.Logger = None,
                 label: str = 'predictor'):
        self._actor = actor
        self._episode_reward = 0.
        self._episode_pnl = 0.
        self._pred_rewards = np.array([])
        self._pred_pnls = np.array([])
        self._pred_actions = np.array([], dtype=np.int32)
        self._episode_pnl_path = np.array([])
        self._episode_stock_price = np.array([])
        self._episode_option_price = np.array([])
        self._episode_action = np.array([])
        self._last_pred_rewards = self._pred_rewards
        self._last_pred_pnls = self._pred_pnls
        self._last_pred_actions = self._pred_actions
        self._last_episode_pnl_path = self._episode_pnl_path
        self._last_episode_option_price = self._episode_option_price
        self._last_episode_stock_price = self._episode_stock_price
        self._last_episode_action = self._episode_action
        self._num_train_per_pred = num_train_per_pred
        self._logger = logger or loggers.make_default_logger(label)
        self._counter = 0

    def select_action(self, observation: types.NestedArray) -> types.NestedArray:
        return self._actor.select_action(observation[:-1])

    def observe_first(self, timestep: dm_env.TimeStep):
        pass

    def get_pred_pnls(self):
        return self._last_pred_pnls

    def get_pred_rewards(self):
        return self._last_pred_rewards

    def get_pred_actions(self):
        return self._last_pred_actions

    def get_episode_pnl_path(self):
        return self._last_episode_pnl_path

    def get_episode_stock_price(self):
        return self._last_episode_stock_price

    def get_episode_option_price(self):
        return self._last_episode_option_price

    def get_episode_action(self):
        return self._last_episode_action

    def observe(
        self,
        action: types.NestedArray,
        next_timestep: dm_env.TimeStep,
    ):
        # TODO observation[2] = stock price
        #      observation[8]
        self._episode_stock_price = np.append(
            self._episode_stock_price, next_timestep.observation[2])
        if len(next_timestep.observation) >= 9:
            self._episode_option_price = np.append(
                self._episode_option_price, next_timestep.observation[8])
        self._episode_action = np.append(self._episode_action, action[0])
        self._episode_pnl_path = np.append(
            self._episode_pnl_path, next_timestep.observation[-1])
        self._episode_pnl += next_timestep.observation[-1]
        self._episode_reward += next_timestep.reward
        self._pred_actions = np.append(self._pred_actions, action[0])
        if next_timestep.last():
            self._pred_pnls = np.append(self._pred_pnls, self._episode_pnl)
            self._pred_rewards = np.append(
                self._pred_rewards, int(round(self._episode_reward)))
            self._episode_pnl = 0.
            self._episode_reward = 0.
            self._last_episode_pnl_path = self._episode_pnl_path
            self._last_episode_stock_price = self._episode_stock_price
            self._last_episode_action = self._episode_action
            self._last_episode_option_price = self._episode_option_price
            self._episode_pnl_path = np.array([])
            self._episode_stock_price = np.array([])
            self._episode_action = np.array([])
            self._episode_option_price = np.array([])

    def log_pred_perf(self):
        measures = dict()
        # pnl
        measures['pnl_quantile_5'] = np.quantile(self._pred_pnls, 0.05)
        measures['pnl_quantile_10'] = np.quantile(self._pred_pnls, 0.1)
        measures['pnl_quantile_50'] = np.quantile(self._pred_pnls, 0.5)
        measures['pnl_quantile_90'] = np.quantile(self._pred_pnls, 0.9)
        measures['pnl_quantile_95'] = np.quantile(self._pred_pnls, 0.95)
        measures['pnl_mean'] = self._pred_pnls.mean()
        measures['pnl_std'] = self._pred_pnls.std()
        # reward
        measures['reward_mean'] = self._pred_rewards.mean()
        # action
        action_count = len(self._pred_actions)
        measures['sell-5'] = np.count_nonzero(
            self._pred_actions == -5) / action_count
        measures['sell-4'] = np.count_nonzero(
            self._pred_actions == -4) / action_count
        measures['sell-3'] = np.count_nonzero(
            self._pred_actions == -3) / action_count
        measures['sell-2'] = np.count_nonzero(
            self._pred_actions == -2) / action_count
        measures['sell-1'] = np.count_nonzero(
            self._pred_actions == -1) / action_count
        measures['hold'] = np.count_nonzero(
            self._pred_actions == 0) / action_count
        measures['buy-1'] = np.count_nonzero(
            self._pred_actions == 1) / action_count
        measures['buy-2'] = np.count_nonzero(
            self._pred_actions == 2) / action_count
        measures['buy-3'] = np.count_nonzero(
            self._pred_actions == 3) / action_count
        measures['buy-4'] = np.count_nonzero(
            self._pred_actions == 4) / action_count
        measures['buy-5'] = np.count_nonzero(
            self._pred_actions == 5) / action_count
        self._counter += 1
        measures['train_episodes'] = self._counter * self._num_train_per_pred
        self._logger.write(measures)
        self._last_pred_pnls = self._pred_pnls
        self._last_pred_rewards = self._pred_rewards
        self._last_pred_actions = self._pred_actions
        self._pred_pnls = np.array([])
        self._pred_rewards = np.array([])
        self._pred_actions = np.array([])

    def update(self):
        pass
