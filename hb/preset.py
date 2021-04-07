from typing import Union
import json
from hb.market_env.market import Market
from hb.utils.loggers.default import make_default_logger
import hb.bots.d4pgbot as d4pg
import hb.bots.greekbot as greek
import acme
import pandas as pd
import numpy as np


class Preset:
    def __init__(self) -> None:
        self._market = None
        self._agent = None
        self._agent_type = None
        self._log_path = None

    @classmethod
    def load_json(cls, json_: Union[dict, str]):
        """Constructor of market environment
        example:
        {
            "name": "BSM_AMZN_SPX",
            "valuation_date": "2020-02-03" (yyyy-mm-dd),
            "reward_rule": "PnLReward",
            "hedging_step_in_days": 1,
            "validation_rng_seed": 1234,
            "training_episodes": 10000,
            "validation_episodes": 1000,
            "riskfactorsimulator": {
                "ir": 0.015,
                "equity": [
                    {
                        "name": "AMZN",
                        "riskfactors": ["Spot", 
                                        "Vol 3Mx100",
                                        "Vol 2Mx100", 
                                        "Vol 4Wx100"],
                        "process_param": {
                            "process_type": "Heston",
                            "param": {
                                "spot": 100,
                                "spot_var": 0.096024,
                                "drift": 0.25,
                                "dividend": 0.0,
                                "kappa": 6.288453,
                                "theta": 0.397888,
                                "epsilon": 0.753137,
                                "rho": -0.696611
                            } 
                        }
                    },
                    {
                        "name": "SPX",
                        "riskfactors": ["Spot", "Vol 3Mx100"],
                        "process_param": {
                            "process_type": "GBM",
                            "param": {
                                "spot": 100,
                                "drift": 0.10,
                                "dividend": 0.01933,
                                "vol": 0.25
                            } 
                        }
                    }
                ],
                "correlation": [
                    {
                        "equity1": "AMZN",
                        "equity2": "SPX",
                        "corr": 0.8
                    }
                ]
            }
        }
        Args:
            json_ (Union[dict, str]): market environment in json
        """
        if isinstance(json_, str):
            dict_json = json.loads(json_)
        else:
            dict_json = json_
        preset = cls()
        market = Market.load_json(dict_json["market"])
        preset._log_path = dict_json["log_path"]
        for agent in dict_json["agents"]:
            if agent["agent_type"] == "D4PG":
                if agent["name"] == dict_json["trainable_agent"]:
                    agent_obj = d4pg.load_json(agent, market, preset._log_path, True)
                else:
                    agent_obj = d4pg.load_json(agent, market, preset._log_path, False)
            elif agent["agent_type"] == "Greek":
                agent_obj = greek.load_json(agent, market, preset._log_path)
            else:
                raise NotImplementedError()
            market.add_agent(agent_obj, agent["name"])
            if agent["name"] == dict_json["trainable_agent"]:
                market.set_trainable_agent(agent["name"])
                preset._agent = market.get_agent(dict_json["trainable_agent"])
                preset._agent_type = agent["agent_type"]
        preset._market = market
        return preset

    @staticmethod
    def load_file(preset_file):
        preset_json = open(preset_file)
        preset_dict = json.load(preset_json)
        preset_json.close()
        return Preset.load_json(preset_dict)

    def dist_stat_save(self):
        for agent in self._market._agents.values():
            predictor = agent.get_predictor()
            bot_name = agent.get_name()
            predictor._update_progress_figures()
            status = predictor._progress_measures
            print(f"{bot_name} Bot PnL mean-var %s" % str(status['mean-var']))
            print(f"{bot_name} Bot PnL mean %s" % str(status['pnl_mean']))
            print(f"{bot_name} Bot PnL std %s" % str(status['pnl_std']))
            print(f"{bot_name} Bot 95VaR %s" % status['pnl_95VaR'])
            print(f"{bot_name} Bot 99VaR %s" % status['pnl_99VaR'])
            print(f"{bot_name} Bot 95CVaR %s" % status['pnl_95CVaR'])
            print(f"{bot_name} Bot 99CVaR %s" % status['pnl_99CVaR'])
            status_dic = {}

            for k in status.keys():
                status_dic[k] = [status[k]]

            pd.DataFrame.from_dict(status_dic, orient="index", columns=[bot_name]).to_csv(f'{self._log_path}{bot_name}_pnl_stat.csv')

    def train(self, num_check_points):
        if self._agent_type == "Greek":
            print("Greek agent is not trainable.")
            return
        else:
            self._agent.set_pred_only(False)
            
            # Try running the environment loop. We have no assertions here because all
            # we care about is that the agent runs without raising any errors.

            loop = acme.EnvironmentLoop(self._market, self._agent,
                                        logger=make_default_logger(
                                            directory=self._log_path+'environment_loop',
                                            label="environment_loop"))
            num_prediction_episodes = self._market.get_validation_episodes()
            num_train_episodes = self._market.get_train_episodes()
            num_episodes =  num_train_episodes + num_prediction_episodes
            if num_episodes > 0:
                for i in range(num_check_points):
                    print(f"Check Point {i}")
                    # train
                    self._market.set_mode("training",continue_counter=True)
                    loop.run(num_episodes=num_train_episodes)
                    # prediction
                    self._market.set_mode("validation")
                    loop.run(num_episodes=num_prediction_episodes)
                    self._agent.checkpoint_save()    

    def validation(self):
        self._market.set_mode("validation")
        for agent in self._market._agents.values():
            agent.set_pred_only(True)
        loop = acme.EnvironmentLoop(self._market, self._agent)
        loop.run(num_episodes=self._market.get_validation_episodes())

        self.dist_stat_save()

        for agent in self._market._agents.values():
            hedge_perf = pd.read_csv(f'{self._log_path}logs/{agent.get_name()}/performance/logs.csv')
            hedge_pnl_list = hedge_perf[hedge_perf.type=='pnl'].drop(['path_num','type'], axis=1).sum(axis=1).values
            np.save(f'{self._log_path}{agent}hedge_pnl_measures.npy', hedge_pnl_list)