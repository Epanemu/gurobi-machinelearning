# Copyright © 2022 Gurobi Optimization, LLC
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
# ==============================================================================

""" Module for embeding a :external+torch:py:class:`torch.nn.Sequential` model into a
:gurobipy:`model`.
"""

import torch
from torch import nn

from ..exceptions import NoModel, NoSolution
from ..modeling.neuralnet import BaseNNConstr


def add_sequential_constr(gp_model, sequential_model, input_vars, output_vars=None, **kwargs):
    """Embed sequential_model into gp_model

    Predict the values of output_vars using input_vars


    Parameters
    ----------
    gp_model: :gurobipy:`model`
        The gurobipy model where the sequential model should be inserted.
    sequential_model: :external+torch:py:class:`torch.nn.Sequential`
        The sequential model to insert as predictor.
    input_vars: :gurobipy:`mvar` or :gurobipy:`var` array like
        Decision variables used as input for logistic regression in model.
    output_vars: :gurobipy:`mvar` or :gurobipy:`var` array like, optional
        Decision variables used as output for logistic regression in model.

    Returns
    -------
    SequentialConstr
        Object containing information about what was added to model to insert the
        predictor in it

    Warning
    -------
    Only :external+torch:py:class:`torch.nn.Linear` layers and
    :external+torch:py:class:`torch.nn.ReLU` layers are supported.

    Raises
    ------
    NoModel
        If the translation for some of the Pytorch model structure
        (layer or activation) is not implemented.

    Note
    ----
    |VariablesDimensionsWarn|
    """
    return SequentialConstr(gp_model, sequential_model, input_vars, output_vars, **kwargs)


class SequentialConstr(BaseNNConstr):
    """Transform a pytorch Sequential Neural Network to Gurobi constraint with
    input and output as matrices of variables."""

    def __init__(self, gp_model, predictor, input_vars, output_vars=None, **kwargs):
        linear = None
        for step in predictor:
            if isinstance(step, nn.ReLU):
                pass
            elif isinstance(step, nn.Linear):
                pass
            else:
                raise NoModel(predictor, f"Unsupported layer {type(step).__name__}")
        super().__init__(
            gp_model, predictor, input_vars, output_vars, default_name="torchsequential"
        )

    def _mip_model(self):
        network = self.predictor
        _input = self._input
        output = None
        numlayers = len(network)

        for i, step in enumerate(network):
            if i == numlayers - 1:
                output = self._output
            if isinstance(step, nn.ReLU):
                layer = self.add_activation_layer(
                    _input,
                    self.actdict["relu"],
                    output,
                    name=f"{i}",
                )
                _input = layer.output
            elif isinstance(step, nn.Linear):
                for name, param in step.named_parameters():
                    if name == "weight":
                        layer_weight = param.detach().numpy().T
                    elif name == "bias":
                        layer_bias = param.detach().numpy()
                layer = self.add_dense_layer(
                    _input,
                    layer_weight,
                    layer_bias,
                    self.actdict["identity"],
                    output,
                    name=f"{i}",
                )
                _input = layer.output
        if self._output is None:
            self._output = layer.output

    def get_error(self):
        """Returns error in Gurobi's solution with respect to prediction from input

        Returns
        -------
        float
            Assuming that we have a solution for the input and output variables
            `x, y`. Returns the difference between `predict(x)` and
            `y`, where predict is the corresponding function for the Scikit-Learn
            object we are modeling.

        Raises
        ------
        NoSolution
            If the Gurobi model has no solution (either was not optimized or is infeasible).
        """
        if self._has_solution():
            t_in = torch.from_numpy(self.input.X).float()
            t_out = self.predictor.forward(t_in)
            return t_out.detach().numpy() - self.output.X
        raise NoSolution()
