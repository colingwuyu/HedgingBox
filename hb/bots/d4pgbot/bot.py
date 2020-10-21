# python3
# Copyright 2018 DeepMind Technologies Limited. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""D4PG agent implementation."""

import copy

from acme import datasets
from acme import specs
from acme import types
from acme.adders import reverb as adders
from acme.agents import agent
from acme.agents.tf import actors
from acme.tf import networks
from acme.tf import savers as tf2_savers
from acme.tf import utils as tf2_utils
from acme.utils import counting
from acme.utils import loggers
import reverb
import sonnet as snt
import tensorflow as tf
import numpy as np

from hb.bots import bot
from hb.bots.d4pgbot import predictor as d4pg_predictor
from hb.bots.d4pgbot import learning
from hb.tf.networks.noise import ClipToSpecGaussian


# TODO(b/145531941): make the naming of this agent consistent.
class D4PGBot(bot.Bot):
    """D4PG Bot.

    """
    def __init__(self,
                environment_spec: specs.EnvironmentSpec,
                policy_network: snt.Module,
                critic_network: snt.Module,
                observation_network: types.TensorTransformation = tf.identity,
                discount: float = 1.0,
                pred_episode: int = 1_000,
                observation_per_pred: int = 10_000,
                pred_only: bool = False,
                batch_size: int = 256,
                prefetch_size: int = 4,
                target_update_period: int = 100,
                policy_optimizer: snt.Optimizer = None,
                critic_optimizer: snt.Optimizer = None,
                min_replay_size: int = 1000,
                max_replay_size: int = 1000000,
                samples_per_insert: float = 32.0,
                n_step: int = 5,
                sigma: float = 0.3,
                clipping: bool = True,
                risk_obj_func: bool = True,
                risk_obj_c: np.float32 = 1.5,
                logger: loggers.Logger = None,
                counter: counting.Counter = None,
                pred_dir: str = '~/acme/',
                checkpoint: bool = True,
                checkpoint_subpath: str = '~/acme/',
                checkpoint_per_min: float = 30.,
                replay_table_name: str = adders.DEFAULT_PRIORITY_TABLE):
        # Create a replay server to add data to. This uses no limiter behavior in
        # order to allow the Agent interface to handle it.
        replay_table = reverb.Table(
            name=replay_table_name,
            sampler=reverb.selectors.Uniform(),
            remover=reverb.selectors.Fifo(),
            max_size=max_replay_size,
            rate_limiter=reverb.rate_limiters.MinSize(1),
            signature=adders.NStepTransitionAdder.signature(environment_spec))
        self._server = reverb.Server([replay_table], port=None)

        # The adder is used to insert observations into replay.
        address = f'localhost:{self._server.port}'
        adder = adders.NStepTransitionAdder(
            priority_fns={replay_table_name: lambda x: 1.},
            client=reverb.Client(address),
            n_step=n_step,
            discount=discount)

        # The dataset provides an interface to sample from replay.
        dataset = datasets.make_reverb_dataset(
            table=replay_table_name,
            client=reverb.TFClient(address),
            batch_size=batch_size,
            prefetch_size=prefetch_size,
            environment_spec=environment_spec,
            transition_adder=True)

        # Make sure observation network is a Sonnet Module.
        observation_network = tf2_utils.to_sonnet_module(observation_network)

        # Create target networks.
        target_policy_network = copy.deepcopy(policy_network)
        target_critic_network = copy.deepcopy(critic_network)
        target_observation_network = copy.deepcopy(observation_network)

        # Get observation and action specs.
        act_spec = environment_spec.actions
        obs_spec = environment_spec.observations
        emb_spec = tf2_utils.create_variables(observation_network, [obs_spec])

        # Create the behavior policy.
        behavior_network = snt.Sequential([
            observation_network,
            policy_network,
            ClipToSpecGaussian(sigma, act_spec),
        ])

        # Create variables.
        tf2_utils.create_variables(policy_network, [emb_spec])  # pytype: disable=wrong-arg-types
        tf2_utils.create_variables(critic_network, [emb_spec, act_spec])
        tf2_utils.create_variables(target_policy_network, [emb_spec])  # pytype: disable=wrong-arg-types
        tf2_utils.create_variables(target_critic_network, [emb_spec, act_spec])
        tf2_utils.create_variables(target_observation_network, [obs_spec])

        # Create the actor which defines how we take actions.
        actor = actors.FeedForwardActor(behavior_network, adder=adder)

        # Create the predictor 
        pred_behavior_network = snt.Sequential([
            observation_network,
            policy_network,
            networks.ClipToSpec(act_spec),
        ])
        predictor = d4pg_predictor.D4PGPredictor(network=pred_behavior_network,
                                                action_spec=act_spec, 
                                                num_train_per_pred=observation_per_pred, 
                                                logger_dir=pred_dir,
                                                risk_obj=risk_obj_func,
                                                risk_obj_c=risk_obj_c)

        # Create optimizers.
        policy_optimizer = policy_optimizer or snt.optimizers.Adam(
            learning_rate=1e-4)
        critic_optimizer = critic_optimizer or snt.optimizers.Adam(
            learning_rate=1e-4)

        # The learner updates the parameters (and initializes them).
        learner = learning.D4PGLearner(
            policy_network=policy_network,
            critic_network=critic_network,
            observation_network=observation_network,
            target_policy_network=target_policy_network,
            target_critic_network=target_critic_network,
            target_observation_network=target_observation_network,
            policy_optimizer=policy_optimizer,
            critic_optimizer=critic_optimizer,
            risk_obj_c=risk_obj_c,
            risk_obj_func=risk_obj_func,
            clipping=clipping,
            discount=discount,
            target_update_period=target_update_period,
            dataset=dataset,
            counter=counter,
            logger=logger,
            checkpoint=checkpoint,
        )

        if checkpoint:
            self._checkpointer = tf2_savers.Checkpointer(
                directory=checkpoint_subpath,
                objects_to_save=learner.state,
                subdirectory='d4pg_learner',
                time_delta_minutes=checkpoint_per_min,
                add_uid=False)
        else:
            self._checkpointer = None
            
        super().__init__(
            actor=actor,
            learner=learner,
            predictor=predictor,
            min_observations=max(batch_size, min_replay_size),
            observations_per_step=float(batch_size) / samples_per_insert,
            pred_episods=pred_episode,
            observations_per_pred=observation_per_pred,
            pred_only=pred_only)

    def update(self):
        super().update()
        if (self._checkpointer is not None) and self._predictor.is_best_perf():
            self._checkpointer.save(force=True)
