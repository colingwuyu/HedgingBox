from typing import List, Union
from hb.instrument.instrument import Instrument
from hb.instrument.instrument_factory import InstrumentFactory
from hb.instrument.stock import Stock
from hb.instrument.european_option import EuropeanOption
from hb.instrument.variance_swap import VarianceSwap
from hb.utils.consts import *
from hb.utils.date import *
from hb.market_env.risk_limits import RiskLimits
import json
import os
import numpy as np
import tensorflow as tf

class Position():
    def __init__(self, instrument=None, holding=0., 
                 trading_limit=[MIN_FLT_VALUE/2., MAX_FLT_VALUE/2.-1.], 
                 holding_constraints=[MIN_FLT_VALUE, MAX_FLT_VALUE]):
        """A position in portfolio containing holding and instrument information

        Args:
            instrument (Instrument, optional): holding instrument. Defaults to None.
            holding (float, optional): initial holding. Defaults to 0..
            holding_constraints (List[float], optional): holding_constraints, first item is lower bound, second item is upper bound. Defaults to None.
        """
        self._instrument = instrument
        self._holding = holding
        self._init_holding = holding
        self._trading_limit = trading_limit
        self._scale_f = (self._trading_limit[1] - self._trading_limit[0])/2
        self._loc_f = (self._trading_limit[1] + self._trading_limit[0])/2
        self._holding_constraints = holding_constraints
       
    def reset(self):
        self._holding = self._init_holding
        self._instrument.reset()

    def get_instrument(self):
        return self._instrument

    def set_instrument(self, instrument):
        self._instrument = instrument

    def instrument(self, instrument):
        self._instrument = instrument
        return self

    def get_holding(self):
        return self._holding

    def set_holding(self, holding):
        self._holding = holding
        self._init_holding = holding
    
    def holding(self, holding):
        self._holding = holding
        self._init_holding = holding
        return self

    def get_initial_holding(self):
        return self._init_holding

    def get_holding_constraints(self):
        return self._holding_constraints

    def set_holding_constraints(self, holding_constraints):
        self._holding_constraints = holding_constraints

    def holding_constraints(self, holding_constraints):
        self._holding_constraints = holding_constraints
        return self

    def get_trading_limit(self):
        return self._trading_limit

    def set_trading_limit(self, trading_limit):
        self._trading_limit = trading_limit
        self._loc_f = (self._trading_limit[1] + self._trading_limit[0])/2
        self._scale_f = (self._trading_limit[1] - self._trading_limit[0])/2

    def trading_limit(self, trading_limit):
        self._trading_limit = trading_limit
        self._loc_f = (self._trading_limit[1] + self._trading_limit[0])/2
        self._scale_f = (self._trading_limit[1] - self._trading_limit[0])/2
        return self

    def get_init_holding(self):
        return self._init_holding

    def set_init_holding(self, init_holding):
        self._init_holding = init_holding

    def scale_up_action(self, action):
        """scale an action in range [-1, 1] to the range of trading limit

        Args:
            action (np.float32): action between [-1, 1]

        Returns:
            action scaled up: action between [trading_limit[0], trading_limit[1]]
        """
        return self._loc_f + action*self._scale_f
    
    def scale_down_action(self, action):
        """scale an action in range [trading_limit[0], trading_limit[1]] to the range [-1, 1]

        Args:
            action (np.float32): action between [trading_limit[0], trading_limit[1]]
        
        Returns:
            action scaled down: action between [-1, 1]
        """
        return (action-self._loc_f)/self._scale_f

    def buy(self, shares: float, ignore_constraint: bool=False):
        """buy shares

        Args:
            shares (float): if it is positive, then means to buy shares
                            if it is negative, then means to sell shares

        Returns:
            cashflow (float):   the proceed cash flow including transaction cost 
                                it is positive cashflow if sell shares
                                it is negative cashflow if buy shares
                                transaction cost is always negative cashflow
            transaction cost (float): the transaction cost for buying shares
        """
        prev_holding = self._holding
        # cutting off at holding constraint
        if not ignore_constraint:
            self._holding = max(self._holding_constraints[0], min(prev_holding+shares, self._holding_constraints[1]))
            # cutting off at trading limit
            shares = max(self._trading_limit[0], min(self._trading_limit[1], self._holding - prev_holding))
        else:
            self._holding = self._holding + shares
        trans_cost = self._instrument.get_execute_cost(shares)
        return - self._instrument.get_market_value(shares) - trans_cost, trans_cost, shares

    def get_breach_holding_constraint(self):
        """check if holding exceeds constraints

        Returns:
            bool: True if it exceeds constraints
        """
        return (abs(self._holding - self._holding_constraints[0]) < 1e-5) \
            or (abs(self._holding - self._holding_constraints[1]) < 1e-5) 

    def get_market_value(self):
        # if (abs(self._holding - self._holding_constraints[0]) < 1e-5) or \
        #     (abs(self._holding - self._holding_constraints[1]) < 1e-5):
        #     # 
        #     return np.nan
        # else:
        return self._instrument.get_market_value(self._holding)

    def get_delta(self):
        return self._instrument.get_delta()*self._holding

    def get_gamma(self):
        return self._instrument.get_gamma()*self._holding

    def get_vega(self):
        return self._instrument.get_vega()*self._holding

    @classmethod
    def load_json(cls, json_: Union[dict, str]):
        """Constructor of market environment
        example:
        {
            "holding": -1.30403,
            "trading_limit": [-5,5],
            "instrument": "SPX"
        }
        Args:
            json_ (Union[dict, str]): [description]

        Returns:
            Position: a position object
                      insturment is a string representing its name, 
                      instrument object needs be looked up from Market.get_instrument function
        """
        if isinstance(json_, str):
            dict_json = json.loads(json_)
        else:
            dict_json = json_
        ret_pos = cls().holding(dict_json["holding"]).instrument(dict_json["instrument"])
        if "holding_constraints" in dict_json:
            ret_pos.set_holding_constraints(dict_json["holding_constraints"])
        if "trading_limit" in dict_json:
            ret_pos.set_trading_limit(dict_json["trading_limit"])
        return ret_pos

    def jsonify_dict(self) -> dict:
        dict_json = dict()
        dict_json["holding"] = self._holding
        dict_json["instrument"] = self._instrument.get_name()
        if self._holding_constraints[0] > MIN_FLT_VALUE:
            dict_json["holding_constraints"] = self._holding_constraints
        if self._trading_limit[0] > MIN_FLT_VALUE/2.:
            dict_json["trading_limit"] = self._trading_limit
        return dict_json

    def __repr__(self):
        return json.dumps(self.jsonify_dict(), indent=4)

class Portfolio():
    def __init__(self, 
                 positions: List[Position],
                 risk_limits: RiskLimits = RiskLimits()):
        """Portfolio contains holding positions and risk limits

        Args:
            positions (List[Position]): a list of positions
            risk_limits (RiskLimits, optional): [description]. Defaults to RiskLimits().
        """
        self._positions = positions
        self._risk_limits = risk_limits
        self._hedging_portfolio = []
        self._hedging_portfolio_map = dict()
        self._liability_portfolio = []
        self._liability_portfolio_map = dict()

    @classmethod
    def make_portfolio(cls,
                       instruments: Union[List[Instrument], List[str]],
                       holdings: List[float],
                       risk_limits: RiskLimits = RiskLimits()):
        positions = []
        for instrument, holding in zip(instruments, holdings):
            positions += [Position(instrument, holding)]
        return cls(positions, risk_limits)
    
    def classify_positions(self):
        """classify positions into hedging and liability positions 
        """
        for position in self._positions:
            if position.get_instrument().get_is_tradable():
                assert position.get_instrument().get_name() not in self._hedging_portfolio_map, "Duplicate instrument name: %s" % position.get_instrument().get_name()
                self._hedging_portfolio += [position]
                self._hedging_portfolio_map[position.get_instrument().get_name()] = position
            else:
                self._liability_portfolio += [position]
                self._liability_portfolio_map[position.get_instrument().get_name()] = position

    @classmethod
    def load_json(cls, json_: Union[dict, str]):
        if isinstance(json_, str):
            dict_json = json.loads(json_)
        else:
            dict_json = json_
        if "risk_limits" in dict_json:
            risk_limits = RiskLimits.load_json(dict_json["risk_limits"])
        else:
            risk_limits = RiskLimits()
        portfolio = cls(positions=[Position.load_json(pos) for pos in dict_json["positions"]],
                        risk_limits=risk_limits)
        return portfolio

    def jsonify_dict(self) -> dict:
        dict_json = dict()
        dict_json["risk_limits"] = self._risk_limits.jsonify_dict()
        dict_json["positions"] = [position.jsonify_dict() for position in self._positions]
        return dict_json

    def __repr__(self):
        return json.dumps(self.jsonify_dict(), indent=4)
    
    def get_all_liability_expired(self) -> bool:
        all_expired = True
        for derivative in self._liability_portfolio:
            if not derivative.get_instrument().get_is_expired():
                all_expired = False
        return all_expired

    def get_hedging_portfolio(self):
        return self._hedging_portfolio

    def get_liability_portfolio(self):
        return self._liability_portfolio

    def get_portfolio_positions(self):
        return self._positions

    def get_position(self, instrument_name: str):
        if instrument_name in self._hedging_portfolio_map:
            return self._hedging_portfolio_map[instrument_name]
        elif instrument_name in self._liability_portfolio_map:
            return self._liability_portfolio_map[instrument_name]

    def get_breach_holding_constraint(self):
        breach = False
        for pos in self._hedging_portfolio:
            breach = breach or pos.get_breach_holding_constraint()
        return breach

    def reset(self):
        for position in self._positions:
            position.reset()
            
    def get_nav(self):
        nav = 0.
        for position in self._positions:
            nav += position.get_market_value()
        return nav

    def get_delta(self):
        delta = 0.
        for position in self._positions:
            delta += position.get_delta()
        return delta

    def get_gamma(self):
        gamma = 0.
        for position in self._positions:
            gamma += position.get_gamma()
        return gamma
        
    def get_vega(self):
        vega = 0.
        for position in self._positions:
            vega += position.get_vega()
        return vega
        
    def scale_actions(self, actions):
        for action_i, position in enumerate(self._hedging_portfolio):
            actions[action_i] = position.scale_up_action(actions[action_i])
        
    def clip_actions(self, actions):
        for action_i, position in enumerate(self._hedging_portfolio):
            actions[action_i] = position.scale_down_action(actions[action_i])

    def rebalance(self, actions):
        """Rebalance portfolio with hedging actions
           Also deal with the expiry events
           When a derivative expires:
            reduce the hedging positions' transaction cost according to the exercise
                - if cash delivery: include the corresponding transaction costs for dumping the hedging positions
                - if physical delivery: no transaction costs for the hedging position delivery 

        Args:
            actions ([float]): hedging buy/sell action applied to hedging portfolio

        Returns:
            cashflow [float]: step cashflow (buy/sell proceeds, and option exercise payoff go to cash account)
            trans_cost [float]: transaction cost at the time step
        """
        cashflows = 0.
        trans_costs = 0.
        self._risk_limits.review_actions(actions, self)
        for i, action in enumerate(actions):
            # rebalance hedging positions
            proceeds, trans_cost, trunc_action = self._hedging_portfolio[i].buy(action)
            cashflows += proceeds if not np.isnan(proceeds) else LARGE_NEG_VALUE
            trans_costs += trans_cost
            actions[i] = trunc_action
        return cashflows, trans_costs
    
    def market_impact(self, actions) -> float:
        mi_cashflows = 0.
        for i, action in enumerate(actions):
            mi_cashflows += self._hedging_portfolio[i].get_instrument().market_impact()*(-action)
        return mi_cashflows

    def event_handler(self):
        cashflows = 0.
        trans_costs = 0.
        for derivative in self._positions:
            if abs(derivative.get_instrument().get_remaining_time()-0.0) < 1e-5:
                # position expired
                derivative_cash_flow, trans_cost = self.derivative_exercise_event(derivative)
                # derivative payoff is paid cashflow
                cashflows += derivative_cash_flow
                # the hedging action includes the delivery or dumping due to derivative gets exercised
                # if the derivative is physically delivered, the transaction cost should exclude the hedging_position delivery action
                # in such case rebate trans_costs to the delivery shares
                trans_costs += trans_cost
        return cashflows, trans_costs

    def derivative_exercise_event(self, derivative_position: Position):
        """Deal derivative exercise event
            When a derivative expires:
            reduce the hedging positions according to the delivery shares of exercise
                - if cash delivery: include the corresponding transaction costs for dumping the hedging positions
                - if physical delivery: no extra transaction costs 

        Returns:
            cashflow [float]: proceeds due to dumping hedging positions 
        """
        cf = 0.
        trans_cost = 0.
        # cashflow = derivative_position.get_market_value()
        # derivative position cleared and exercised
        shares = derivative_position.get_instrument().exercise()
        dump_shares = derivative_position.get_holding()*shares
        cashflow, _, _ = derivative_position.buy(-derivative_position.get_holding(), ignore_constraint=True)
        # trade or deliver the corresponding shares for option exercise
        hedging_position = self._hedging_portfolio_map[derivative_position.get_instrument().get_underlying_name()]
        proceeds, trans_cost, _ = hedging_position.buy(dump_shares, ignore_constraint=True)
        if derivative_position.get_instrument().get_is_physical_settle():
            # physical settle
            proceeds += trans_cost
            trans_cost = 0
        cashflow += proceeds
        return cashflow, trans_cost

    def dump_portfolio(self):
        """Dump portfolio at terminal step

        Returns:
            cashflow [float]: terminal cashflow (dump hedging portfolio proceeds, and derivative exercise payoff go to cash account)
            trans_cost [float]: transaction cost for dumping portfolio at terminal cashflow
        """
        cashflows = 0.
        trans_costs = 0.
        dump_actions = np.zeros(len(self._hedging_portfolio))
        for i, hedging_position in enumerate(self._hedging_portfolio):
            # rebalance hedging positions
            dump_actions[i] = -hedging_position.get_holding()
            proceeds, trans_cost, _ = hedging_position.buy(-hedging_position.get_holding(), ignore_constraint=True)
            cashflows += proceeds
            trans_costs += trans_cost
        return cashflows, trans_costs, dump_actions

    def action_constraint(self, action, observation):
        cs = action.shape.as_list()
        uh = np.zeros(cs)
        lh = np.zeros(cs)
        ua = np.zeros(cs)
        la = np.zeros(cs)
        ind = np.arange(0, len(self._hedging_portfolio))*2+1
        for i, position in enumerate(self._hedging_portfolio):
            uh[:, i] = position.get_holding_constraints()[1] 
            lh[:, i] = position.get_holding_constraints()[0] 
            ua[:, i] = position.get_trading_limit()[1]
            la[:, i] = position.get_trading_limit()[0]
        uh = tf.cast(uh, dtype=tf.float32) - tf.gather(observation, ind, axis=-1)
        lh = tf.cast(lh, dtype=tf.float32) - tf.gather(observation, ind, axis=-1)
        ua = tf.cast(ua, dtype=tf.float32)
        la = tf.cast(la, dtype=tf.float32)
        # leaky relu
        ac = tf.maximum(tf.minimum(ua - action/100, action), la + action/100)
        hc = tf.maximum(tf.minimum(uh - action/100, ac), lh + action/100)
        return hc


if __name__ == "__main__":
    with open('Markets/Market_Example/portfolio.json') as json_file:
        portfolio_dict = json.load(json_file)
        loaded_portfolio = Portfolio.load_json(portfolio_dict)
        print(loaded_portfolio)
    with open('Markets/Market_Example/varswap_portfolio.json') as json_file:
        portfolio_dict = json.load(json_file)
        loaded_portfolio = Portfolio.load_json(portfolio_dict)
        print(loaded_portfolio)