"""MOSFET loss model for PFC boost switch.

Supports both fixed parameters (DesignSpec) and
database-driven MosfetSpec for optimization sweeps.
"""

import numpy as np

from ..core.spec import DesignSpec, MosfetSpec
from ..core.operating_point import OperatingPoint
from .base import LossResult


class MosfetLoss:
    """MOSFET total loss computation."""

    def compute(self, spec: DesignSpec, op: OperatingPoint,
                mosfet: MosfetSpec | None = None,
                t_j: float = 80.0) -> LossResult:
        """Compute all MOSFET losses per switch.

        Args:
            spec: design specification (or fallback if mosfet is None)
            op: operating point
            mosfet: MosfetSpec from database; uses spec defaults if None
            t_j: junction temperature in °C

        Returns:
            LossResult with sub-losses and part info in metadata
        """
        # Use MosfetSpec if provided, otherwise legacy spec fields
        if mosfet is not None:
            vds_max = mosfet.vds_max
            rds_25 = mosfet.rds_on_25c
            rds_alpha = mosfet.rds_alpha
            qg = mosfet.qg
            coss_er = mosfet.coss_er
            tr = mosfet.tr
            tf = mosfet.tf
            vgs = mosfet.vgs
            part = mosfet.part_number
            tech = mosfet.technology
        else:
            vds_max = spec.mosfet_vds_max
            rds_25 = spec.mosfet_rds_on
            rds_alpha = spec.mosfet_rds_alpha
            qg = spec.mosfet_qg
            coss_er = spec.mosfet_coss_er
            tr = spec.mosfet_tr
            tf = spec.mosfet_tf
            vgs = spec.mosfet_vgs
            part = "Mathcad-ref"
            tech = "SiC"

        # Temperature-adjusted Rds_on
        rds_tj = rds_25 * (1 + rds_alpha * (t_j - 25))

        p_cond = self._conduction_loss(op, rds_tj)
        p_sw = self._switching_loss(spec, op, tr, tf)
        p_coss = self._coss_loss(spec, coss_er)
        p_gate = self._gate_loss(spec, qg, vgs)

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
                "part_number": part,
                "technology": tech,
                "vds_max": vds_max,
                "Rds_on_Tj": rds_tj,
                "T_j": t_j,
            }
        )

    def _conduction_loss(self, op: OperatingPoint, rds: float) -> float:
        i_ds_rms = op.rms(op.iin_t, op.duty_t)
        return float(i_ds_rms ** 2 * rds)

    def _switching_loss(self, spec: DesignSpec, op: OperatingPoint,
                        tr: float, tf: float) -> float:
        i_avg_on = 2 / np.pi * op.iin_peak
        e_on = 0.5 * spec.vout * i_avg_on * tr
        e_off = 0.5 * spec.vout * i_avg_on * tf
        return float(spec.fsw * (e_on + e_off))

    def _coss_loss(self, spec: DesignSpec, coss_er: float) -> float:
        e_oss = 0.5 * coss_er * spec.vout ** 2
        return float(e_oss * spec.fsw)

    def _gate_loss(self, spec: DesignSpec, qg: float, vgs: float) -> float:
        return float(qg * vgs * spec.fsw)
