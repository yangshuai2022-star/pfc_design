"""Diode loss model for PFC boost diode.

- Forward voltage loss
- Reverse recovery loss (significant for Si, negligible for SiC)
"""

import numpy as np

from ..core.spec import DesignSpec
from ..core.operating_point import OperatingPoint
from .base import LossResult


class DiodeLoss:
    """Diode loss computation."""

    def compute(self, spec: DesignSpec, op: OperatingPoint) -> LossResult:
        """Compute diode losses per phase.

        Returns:
            LossResult with forward and reverse-recovery sub-losses
        """
        p_fwd = self._forward_loss(spec, op)
        p_rr = self._reverse_recovery(spec, op)

        return LossResult(
            component="Diode (per phase)",
            power_loss_W=p_fwd + p_rr,
            sub_losses={"forward": p_fwd, "reverse_recovery": p_rr},
            metadata={"type": spec.diode_type}
        )

    def _forward_loss(self, spec: DesignSpec, op: OperatingPoint) -> float:
        """Forward conduction loss.

        P_fwd = Vf * I_avg + Rd * I_rms²

        Diode conducts when MOSFET is off: duty cycle = 1 - D(t)
        """
        diode_duty = 1.0 - op.duty_t
        i_d_rms = op.rms(op.iin_t, diode_duty)
        i_d_avg = op.avg(op.iin_t, diode_duty)

        return float(spec.diode_vf * i_d_avg + spec.diode_rd * i_d_rms ** 2)

    def _reverse_recovery(self, spec: DesignSpec, op: OperatingPoint) -> float:
        """Reverse recovery loss.

        For SiC Schottky diodes, Qrr is negligible (≈ 0).
        For Si fast-recovery diodes:
        P_rr = Qrr * Vout * fsw

        Typical Qrr for 650V Si diode: 1-10 μC
        """
        if spec.diode_type.upper() == "SIC":
            return 0.0

        # Estimate Qrr from typical Si diode values
        qrr = 2e-6  # 2 μC typical for 600V/20A fast-recovery diode
        return float(qrr * spec.vout * spec.fsw)
