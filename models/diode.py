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

    def compute(self, spec: DesignSpec, op: OperatingPoint,
                trace=None) -> LossResult:
        """Compute diode losses per phase.

        Returns:
            LossResult with forward and reverse-recovery sub-losses
        """
        if trace is not None:
            p_fwd = self._forward_loss_line_cycle(spec, trace)
            loss_model = "line_cycle"
            extra_meta = {}
        else:
            p_fwd = self._forward_loss_legacy(spec, op)
            loss_model = "legacy_single_point"
            extra_meta = {}

        p_rr = self._reverse_recovery(spec, op)

        metadata = {"type": spec.diode_type, "loss_model": loss_model}
        if spec.diode_type.upper() == "SIC" and p_rr == 0.0:
            metadata["SiC_note"] = "simplified model — Cj/Qc/Ec not accounted"
        metadata.update(extra_meta)

        return LossResult(
            component="Diode (per phase)",
            power_loss_W=p_fwd + p_rr,
            sub_losses={"forward": p_fwd, "reverse_recovery": p_rr},
            metadata=metadata,
        )

    # ── Legacy ──────────────────────────────────────────────────────

    def _forward_loss_legacy(self, spec: DesignSpec, op: OperatingPoint) -> float:
        diode_duty = 1.0 - op.duty_t
        i_d_rms = op.rms(op.iin_t, diode_duty)
        i_d_avg = op.avg(op.iin_t, diode_duty)
        return float(spec.diode_vf * i_d_avg + spec.diode_rd * i_d_rms ** 2)

    # ── Line-cycle forward loss (includes ripple RMS) ───────────────

    def _forward_loss_line_cycle(self, spec: DesignSpec, trace) -> float:
        """Pdiode_forward = Vf * avg((1-D)*i_avg) + Rd * avg((1-D)*[i_avg^2 + delta_i^2/12])."""
        from ..core.line_cycle import average_over_half_cycle
        off_duty = 1.0 - trace.duty
        i_d_avg = average_over_half_cycle(off_duty * trace.i_avg_phase, trace.theta)
        i_d_rms_sq = average_over_half_cycle(off_duty * trace.i_rms_local_sq, trace.theta)
        return float(spec.diode_vf * i_d_avg + spec.diode_rd * i_d_rms_sq)

    # ── Reverse recovery ────────────────────────────────────────────

    def _reverse_recovery(self, spec: DesignSpec, op: OperatingPoint) -> float:
        """Reverse recovery loss.

        SiC Schottky: traditional Qrr ≈ 0 (Cj/Ec not modeled yet).
        Si fast-recovery: Prr = Qrr * Vout * fsw.
        """
        if spec.diode_type.upper() == "SIC":
            return 0.0
        qrr = 2e-6
        return float(qrr * spec.vout * spec.fsw)
