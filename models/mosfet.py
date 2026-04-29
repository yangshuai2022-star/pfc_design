"""MOSFET loss model for PFC boost switch.

Computes:
- Conduction loss (Rds-on with temperature)
- Switching loss (turn-on + turn-off)
- Coss (output capacitance) loss
- Gate drive loss
"""

import numpy as np

from ..core.spec import DesignSpec
from ..core.operating_point import OperatingPoint
from .base import LossResult


class MosfetLoss:
    """MOSFET total loss computation."""

    def compute(self, spec: DesignSpec, op: OperatingPoint,
                t_j: float = 80.0) -> LossResult:
        """Compute all MOSFET losses per switch.

        Args:
            spec: design specification
            op: operating point
            t_j: junction temperature in °C

        Returns:
            LossResult with conduction, switching, Coss, gate sub-losses
        """
        # Temperature-adjusted Rds_on
        rds_tj = spec.mosfet_rds_on * (1 + spec.mosfet_rds_alpha * (t_j - 25))

        # Conduction loss
        p_cond = self._conduction_loss(op, rds_tj)

        # Switching loss
        p_sw = self._switching_loss(spec, op)

        # Coss loss
        p_coss = self._coss_loss(spec)

        # Gate drive loss
        p_gate = self._gate_loss(spec)

        total = p_cond + p_sw + p_coss + p_gate

        return LossResult(
            component="MOSFET (per phase)",
            power_loss_W=total,
            sub_losses={
                "conduction": p_cond,
                "switching": p_sw,
                "Coss": p_coss,
                "gate_drive": p_gate,
            },
            metadata={
                "Rds_on_Tj": rds_tj,
                "T_j": t_j,
            }
        )

    def _conduction_loss(self, op: OperatingPoint, rds: float) -> float:
        """MOSFET conduction loss integrated over line half-cycle.

        I_ds_rms = sqrt(integral(Iin(t)² * D(t)) / T)
        P_cond = I_ds_rms² * Rds_on
        """
        i_ds_rms = op.rms(op.iin_t, op.duty_t)
        return float(i_ds_rms ** 2 * rds)

    def _switching_loss(self, spec: DesignSpec, op: OperatingPoint) -> float:
        """Hard-switching loss for CCM PFC.

        At each switching instant:
          Eon = 0.5 * Vds * Id * tr + Eoss (Coss already handled separately)
          Eoff = 0.5 * Vds * Id * tf

        Average over line cycle: use average Id over switching events
        I_avg_sw = (2/pi) * Iin_peak  (average of rectified sine)
        """
        i_avg_on = 2 / np.pi * op.iin_peak
        e_on = 0.5 * spec.vout * i_avg_on * spec.mosfet_tr
        e_off = 0.5 * spec.vout * i_avg_on * spec.mosfet_tf
        return float(spec.fsw * (e_on + e_off))

    def _coss_loss(self, spec: DesignSpec) -> float:
        """Output capacitance loss.

        Energy stored in Coss at Vout and dissipated at turn-on:
        P_coss = 0.5 * Coss_er * Vout² * fsw
        Uses energy-related effective Coss at Vds = Vout.
        """
        e_oss = 0.5 * spec.mosfet_coss_er * spec.vout ** 2
        return float(e_oss * spec.fsw)

    def _gate_loss(self, spec: DesignSpec) -> float:
        """Gate drive loss: P_gate = Qg * Vgs * fsw."""
        return float(spec.mosfet_qg * spec.mosfet_vgs * spec.fsw)
