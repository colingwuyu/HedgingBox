from acme.utils import loggers
from acme import types
import dm_env
from hb import core
from hb.bots.qtablebot.actor import QTableActor


class QTablePredictor(core.Predictor):
    def __init__(
        self,
        actor: QTableActor,
        num_train_per_pred: int,
        logger: loggers.Logger = None,
        lable: str = 'qtable_predictor'
    ):
        pred_actor = QTableActor(qtable=actor._qtable, epsilon=0.)
        super().__init__(pred_actor, num_train_per_pred, logger, lable)

