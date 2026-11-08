"""Named scoring axes and derived counts for the frozen XC recipe.

The packaged policy owns horizons and development seasons; the versioned
experiment owns the C grid.
Only the learned 100+/final-200+ outputs select the recipe; pooled 300+
is evaluated separately. Changing supported axes still requires a compatible
version of the model/input contracts, not merely changing a count.
"""

from itertools import product
from typing import get_args

from .experiment import CURRENT_EXPERIMENT_VERSION, regularization_values
from .policy import Stage, load_policy


def score_component_keys(
    validation_seasons, horizons, thresholds
) -> tuple[tuple[int, int, int], ...]:
    """One score component for every season/horizon/threshold combination."""
    return tuple(product(validation_seasons, horizons, thresholds))


_POLICY, _ = load_policy()
FORECAST_HORIZONS = _POLICY.horizons
VALIDATION_SEASONS = _POLICY.development_seasons[1:]
EVALUATED_THRESHOLDS_KM = (100, 200, 300)
SELECTION_THRESHOLDS_KM = (100, 200)
MODEL_STAGES = get_args(Stage)
REGULARIZATION_VALUES = regularization_values(CURRENT_EXPERIMENT_VERSION)
REGULARIZATION_CANDIDATE_COUNT = len(REGULARIZATION_VALUES) ** len(MODEL_STAGES)
TRIAL_FIT_COUNT = len(REGULARIZATION_VALUES) * len(MODEL_STAGES)
TRIAL_SCORE_COMPONENT_COUNT = len(FORECAST_HORIZONS) * len(SELECTION_THRESHOLDS_KM)
SELECTION_COMPONENT_KEYS = score_component_keys(
    VALIDATION_SEASONS, FORECAST_HORIZONS, SELECTION_THRESHOLDS_KM
)
SELECTION_SCORE_COMPONENT_COUNT = len(SELECTION_COMPONENT_KEYS)
