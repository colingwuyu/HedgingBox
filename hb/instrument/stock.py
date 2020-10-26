import QuantLib as ql
from hb.instrument.instrument import Instrument
from hb.transaction_cost.transaction_cost import TransactionCost
from hb.utils.date import *
from hb.utils.process import *
from typing import Union
import numpy as np
import os
from os.path import join as pjoin


class Stock(Instrument):
    def __init__(self, name: str, 
                 annual_yield: float,
                 dividend_yield: float,
                 transaction_cost: TransactionCost):
        """Stock

        Args:
            name (str): stock name (ticker)
            annual_yield (float): annual return
            dividend_yield (float): annual dividend yield
            transaction_cost (TransactionCost): transaction_cost calculator
        """
        self._dividend_yield = dividend_yield
        self._annual_yield = annual_yield
        super().__init__(name=name, tradable=True, transaction_cost=transaction_cost)
        
    def get_dividend_yield(self) -> float:
        return self._dividend_yield

    def set_dividend_yield(self, dividend_yield):
        self._dividend_yield = dividend_yield

    def dividend_yield(self, dividend_yield):
        self._dividend_yield = dividend_yield
        return self
    
    def get_annual_yield(self) -> float:
        return self._annual_yield

    def set_annual_yield(self, annual_yield):
        self._annual_yield = annual_yield

    def annual_yield(self, annual_yield):
        self._annual_yield = annual_yield
        return self

    def _get_price(self, path_i: int, step_i: int) -> float:
        """price of the instrument at current time

        Returns:
            float: price
        """
        return self._simulator_handler.get_obj().get_spot(self._name, path_i, step_i).numpy()

    def __repr__(self):
        return "Stock {name} {annual_yield:.2f} {dividend_yield:.2f} {transaction_cost:.2f}" \
                    .format(name=self._name, 
                            annual_yield=self._annual_yield*100,
                            dividend_yield=self._dividend_yield*100,
                            transaction_cost=self._transaction_cost.get_percentage_cost()*100)

if __name__ == "__main__":
    from hb.transaction_cost.percentage_transaction_cost import PercentageTransactionCost
    from hb.utils.date import *
    from hb.utils.consts import *
    from hb.utils.process import *
    spx = Stock(name='AMZN', 
                quote=3400, 
                annual_yield=0.25,
                dividend_yield=0.0,
                transaction_cost = PercentageTransactionCost(0.001))
    print(spx)
    heston_param = HestonProcessParam(
            risk_free_rate=0.015,
            spot=spx.get_quote(), 
            drift=spx.get_annual_yield(), 
            dividend=spx.get_dividend_yield(),
            spot_var=0.096024, kappa=6.288453, theta=0.397888, 
            rho=-0.696611, vov=0.753137, use_risk_free=False
        )
    bsm_param = GBMProcessParam(
            risk_free_rate = 0.015,
            spot=spx.get_quote(), 
            drift=spx.get_annual_yield(), 
            dividend=spx.get_dividend_yield(), 
            vol=0.5, use_risk_free=False
        )
    num_path = 1_000
    num_step = 90    
    step_days = 1
    step_size = time_from_days(step_days)
    spx.set_pricing_engine(step_size, num_step, heston_param)
    spx.set_pred_episodes(2)
    heston_prices = np.zeros([num_path, num_step])
    heston_vars = np.zeros([num_path, num_step])
    times = np.zeros([num_step])
    for i in range(num_path):
        for j in range(num_step):
            times[j] = get_cur_days()
            # print(get_cur_days())
            price, vol = spx.get_price()
            heston_prices[i][j] = price
            heston_vars[i][j] = vol
            # print(spx.get_name(), spx.get_price())
            move_days(step_days)
        reset_date()

    # spx.set_pred_mode(pred_mode=True)
    # for i in range(num_path):
    #     for j in range(num_step):
    #         # print(get_cur_days())
    #         # print(spx.get_name(), spx.get_price())
    #         move_days(step_days)
    #     reset_date()
    # spx.set_pred_mode(pred_mode=False)

    spx.set_pricing_engine(step_size, num_step, bsm_param)
    gbm_prices = np.zeros([num_path, num_step])
    for i in range(num_path):
        for j in range(num_step):
            # print(get_cur_days())
            # print(spx.get_name(), spx.get_price())
            price, vol = spx.get_price()
            gbm_prices[i][j] = price
            move_days(step_days)
        reset_date()

    import matplotlib.pyplot as plt

    for i in range(num_path):
        plt.plot(times, heston_prices[i, :], lw=0.8, alpha=0.6)
    plt.title("Heston Simulation Spot")
    plt.show()
    for i in range(num_path):
        plt.plot(times, heston_vars[i, :], lw=0.8, alpha=0.6)
    plt.title("Heston Simulation Var")
    plt.show()
    print(heston_vars[:,-1].mean())
    print(heston_prices[:,-1].mean())
    for i in range(num_path):
        plt.plot(times, gbm_prices[i, :], lw=0.8, alpha=0.6)
    plt.title("GBM Simulation")
    plt.show()
    print(gbm_prices[:,-1].mean())
