"""Bridge rectifier loss model.

Always 2 diodes conducting in series.
"""

import numpy as np

from ..core.spec import DesignSpec
from ..core.operating_point import OperatingPoint
from .base import LossResult


class BridgeRectifierLoss:
    """Bridge rectifier loss (total, shared across phases)."""

    def compute(self, spec: DesignSpec, op: OperatingPoint) -> LossResult:
        """Compute bridge rectifier loss.

        Uses the minimum input voltage operating point (worst case).
        P_bridge = 2 * Vf * I_in_avg

        where I_in_avg = average current over half-cycle (2*sqrt(2)/pi * Iin_rms)
        """
        i_in_avg = 2 * np.sqrt(2) / np.pi * op.iin_rms
        p_loss = 2 * spec.bridge_vf * i_in_avg

        return LossResult(
            component="Bridge Rectifier",
            power_loss_W=float(p_loss),
            sub_losses={"forward": float(p_loss)},
            metadata={
                "I_in_avg": i_in_avg,
                "Vf_per_diode": spec.bridge_vf,
            }
        )
