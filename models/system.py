"""System-level loss aggregation and efficiency analysis."""

import numpy as np

from ..core.spec import DesignSpec, MosfetSpec, MosfetDatabase
from ..core.operating_point import OperatingPoint, compute_mathcad_operating_point
from ..magnetics.core_database import CoreDatabase
from ..magnetics.core_entry import CoreSpec
from .inductor import InductorDesigner, InductorLoss, InductorDesign
from .mosfet import MosfetLoss
from .diode import DiodeLoss
from .bridge_rectifier import BridgeRectifierLoss
from .capacitor import CapacitorBank
from .base import LossResult


class SystemAnalyzer:
    """Top-level system loss model."""

    def __init__(self, db: CoreDatabase | None = None):
        self.db = db or CoreDatabase()
        self.mosfet_db = MosfetDatabase()
        self.inductor_designer = InductorDesigner(self.db)
        self.inductor_loss = InductorLoss(self.db)
        self.mosfet_loss = MosfetLoss()
        self.diode_loss = DiodeLoss()
        self.bridge_loss = BridgeRectifierLoss()
        self.capacitor = CapacitorBank()

    def analyze(self, spec: DesignSpec,
                op: OperatingPoint | None = None,
                preferred_core: CoreSpec | None = None,
                mosfet: MosfetSpec | None = None,
                n_cores: int = 2) -> dict:
        """Run full system analysis.

        Args:
            spec: design specification
            op: operating point (default: low-line worst case)
            preferred_core: specific core to use
            mosfet: MosfetSpec from database (auto-selects if None)
            n_cores: number of stacked cores

        Returns:
            dict with all loss results, design data, breakdown
        """
        if op is None:
            op = compute_mathcad_operating_point(spec)

        # Auto-select MOSFET if not provided
        if mosfet is None:
            candidates = self.mosfet_db.query(
                vds_min=spec.vout * 1.3,
                technology="Si"
            )
            mosfet = candidates[0] if candidates else self.mosfet_db.get("C3M0065100K")

        # 1. Inductor
        design = self.inductor_designer.design(spec, op, preferred_core, n_cores)
        ind_loss = self.inductor_loss.compute(design, spec, op)

        # 2. MOSFET (with MosfetSpec)
        mos_loss = self.mosfet_loss.compute(spec, op, mosfet=mosfet)

        # 3. Diode
        dio_loss = self.diode_loss.compute(spec, op)

        # 4. Bridge rectifier (shared)
        br_loss = self.bridge_loss.compute(spec, op)

        # 5. Capacitor bank (shared)
        cap_loss = self.capacitor.compute(spec, op)

        # Aggregate
        per_phase_loss = ind_loss.power_loss_W + mos_loss.power_loss_W + dio_loss.power_loss_W
        total_loss = spec.n_phases * per_phase_loss + br_loss.power_loss_W + cap_loss.power_loss_W
        efficiency = spec.pout_total / (spec.pout_total + total_loss)

        # Breakdown
        n = spec.n_phases
        breakdown = {
            "Inductor Core": n * ind_loss.sub_losses["core"],
            "Inductor Copper": n * ind_loss.sub_losses["copper"],
            "MOSFET Conduction": n * mos_loss.sub_losses["conduction"],
            "MOSFET Switching": n * mos_loss.sub_losses["switching"],
            "MOSFET Coss": n * mos_loss.sub_losses.get("Coss", 0),
            "MOSFET Gate Drive": n * mos_loss.sub_losses.get("gate_drive", 0),
            "Diode Forward": n * dio_loss.sub_losses["forward"],
            "Diode RR": n * dio_loss.sub_losses.get("reverse_recovery", 0),
            "Bridge Rectifier": br_loss.power_loss_W,
            "Capacitor ESR": cap_loss.power_loss_W,
        }

        return {
            "spec": spec,
            "op": op,
            "mosfet": mosfet,
            "inductor_design": design,
            "losses": {
                "inductor": ind_loss,
                "mosfet": mos_loss,
                "diode": dio_loss,
                "bridge": br_loss,
                "capacitor": cap_loss,
            },
            "per_phase_loss": per_phase_loss,
            "total_loss": total_loss,
            "efficiency": efficiency,
            "breakdown": breakdown,
        }
