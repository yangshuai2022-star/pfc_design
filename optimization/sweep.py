"""Parameter sweep engine — 4D optimization over fsw × ripple × core × mosfet."""

import itertools
import numpy as np
import pandas as pd

from ..core.spec import DesignSpec, MosfetSpec, MosfetDatabase
from ..core.operating_point import compute_mathcad_operating_point
from ..magnetics.core_database import CoreDatabase
from ..magnetics.core_entry import CoreSpec
from ..models.system import SystemAnalyzer


class ParamSweep:
    """Grid sweep over design variables with constraint filtering."""

    def __init__(self, db: CoreDatabase | None = None):
        self.db = db or CoreDatabase()
        self.mosfet_db = MosfetDatabase()
        self.analyzer = SystemAnalyzer(self.db)

    def sweep(self, base_spec: DesignSpec,
              sweep_vars: dict[str, np.ndarray],
              n_cores: int = 2,
              cores: list[CoreSpec] | None = None,
              mosfets: list[MosfetSpec] | None = None) -> pd.DataFrame:
        """Run 4D grid sweep: fsw × ripple × core × mosfet.

        Args:
            base_spec: base design specification
            sweep_vars: {
                'fsw': array,           # Hz
                'ripple_ratio': array,  # 0-1
                'core_idx': array,      # indices into core list
                'mosfet_idx': array,    # indices into MOSFET list
            }
            n_cores: number of stacked cores
            cores: candidate core list, defaults to top Sendust PFC cores
            mosfets: candidate MOSFET list, defaults to all parts with enough Vds

        Returns:
            DataFrame with one row per design point
        """
        if cores is None:
            cores = self.db.top_for_pfc(ae_min_cm2=0.5, material_class="Sendust", n=10)
        if mosfets is None:
            mosfets = self.mosfet_db.query(vds_min=base_spec.vout * 1.25)

        if not cores:
            raise ValueError("No core candidates provided for sweep")
        if not mosfets:
            raise ValueError("No MOSFET candidates provided for sweep")

        results = []
        keys = list(sweep_vars.keys())
        values = list(sweep_vars.values())

        total = np.prod([len(v) for v in values])
        for idx, combo in enumerate(itertools.product(*values)):
            params = dict(zip(keys, combo))

            # Clone base spec
            spec = DesignSpec(**{k: v for k, v in base_spec.__dict__.items()
                                 if not k.startswith('_')})

            if "fsw" in params:
                spec.fsw = float(params["fsw"])
            if "ripple_ratio" in params:
                spec.ripple_ratio = float(params["ripple_ratio"])

            # Select core
            core_idx = int(params.get("core_idx", 0))
            core = cores[core_idx % len(cores)]

            # Select MOSFET
            mos_idx = int(params.get("mosfet_idx", 0))
            mosfet = mosfets[mos_idx % len(mosfets)]

            try:
                op = compute_mathcad_operating_point(spec)
                result = self.analyzer.analyze(
                    spec, op, preferred_core=core, mosfet=mosfet, n_cores=n_cores
                )
                design = result["inductor_design"]
                losses = result["losses"]
                ind_meta = losses["inductor"].metadata

                # Constraint checks
                feasible = True
                constraints = []

                b_max = ind_meta.get("B_max_T", 0)
                if b_max > core.bs_T * 0.7:
                    feasible = False
                    constraints.append(f"Bmax={b_max:.3f}T>{core.bs_T*0.7:.3f}T")

                if design.kw > 0.6:
                    feasible = False
                    constraints.append(f"kw={design.kw:.0%}>60%")

                sat_pct = ind_meta.get("saturation_pct", 100)
                if sat_pct < 20:
                    feasible = False
                    constraints.append(f"sat={sat_pct:.0f}%<20%")

                # Actual ripple metrics (report-only, not a hard constraint yet)
                im = result.get("inductor_metrics", {})
                actual_ripple_margin = round(im.get("actual_ripple_margin", 0.0), 4)
                actual_ripple_risk = im.get("actual_ripple_risk_level", "")

                results.append({
                    "fsw_kHz": spec.fsw / 1000,
                    "ripple_ratio": spec.ripple_ratio,
                    "core": core.part_number,
                    "core_material": core.material,
                    "mosfet": mosfet.part_number,
                    "mosfet_tech": mosfet.technology,
                    "mosfet_Rds25": mosfet.rds_on_25c * 1000,
                    "turns": design.n_turns,
                    "wire_d_mm": design.wire_d_mm,
                    "n_parallel": design.n_parallel,
                    "L_target_uH": design.L_target_uh,
                    "L_noload_uH": design.L_noload_uh,
                    "L_eff_uH": design.L_eff_at_ipeak_uh,
                    "B_max_T": b_max,
                    "sat_pct": sat_pct,
                    "kw": design.kw,
                    "P_ind_core_W": losses["inductor"].sub_losses.get("core", 0.0),
                    "P_ind_copper_W": losses["inductor"].sub_losses.get("copper", 0.0),
                    "P_ind_W": losses["inductor"].power_loss_W,
                    "P_mosfet_cond_W": losses["mosfet"].sub_losses.get("conduction", 0.0),
                    "P_mosfet_sw_W": losses["mosfet"].sub_losses.get("switching", 0.0),
                    "P_mosfet_coss_W": losses["mosfet"].sub_losses.get("Coss", 0.0),
                    "P_mosfet_gate_W": losses["mosfet"].sub_losses.get("gate_drive", 0.0),
                    "P_mosfet_W": losses["mosfet"].power_loss_W,
                    "P_diode_fwd_W": losses["diode"].sub_losses.get("forward", 0.0),
                    "P_diode_rr_W": losses["diode"].sub_losses.get("reverse_recovery", 0.0),
                    "P_diode_W": losses["diode"].power_loss_W,
                    "P_bridge_W": losses["bridge"].power_loss_W,
                    "P_cap_W": losses["capacitor"].power_loss_W,
                    "P_total_W": result["total_loss"],
                    "efficiency_pct": result["efficiency"] * 100,
                    "feasible": feasible,
                    "constraints": "; ".join(constraints),
                    "feasible_by_actual_ripple": True,       # reserved
                    "actual_ripple_limit": 2.0,              # reserved placeholder
                    "actual_ripple_margin": actual_ripple_margin,
                    "actual_ripple_risk_level": actual_ripple_risk,
                })
            except Exception as e:
                results.append({
                    "fsw_kHz": spec.fsw / 1000,
                    "ripple_ratio": spec.ripple_ratio,
                    "core": core.part_number,
                    "core_material": core.material,
                    "mosfet": mosfet.part_number,
                    "mosfet_tech": mosfet.technology,
                    "mosfet_Rds25": mosfet.rds_on_25c * 1000,
                    "turns": 0, "wire_d_mm": 0, "n_parallel": 0,
                    "L_target_uH": 0, "L_noload_uH": 0,
                    "L_eff_uH": 0, "B_max_T": 0,
                    "sat_pct": 0, "kw": 0,
                    "P_ind_core_W": 0, "P_ind_copper_W": 0, "P_ind_W": 0,
                    "P_mosfet_cond_W": 0, "P_mosfet_sw_W": 0,
                    "P_mosfet_coss_W": 0, "P_mosfet_gate_W": 0, "P_mosfet_W": 0,
                    "P_diode_fwd_W": 0, "P_diode_rr_W": 0, "P_diode_W": 0,
                    "P_bridge_W": 0, "P_cap_W": 0,
                    "P_total_W": np.nan, "efficiency_pct": np.nan,
                    "feasible": False, "constraints": f"Error: {str(e)[:80]}",
                    "feasible_by_actual_ripple": False,
                    "actual_ripple_limit": 2.0,
                    "actual_ripple_margin": 0.0,
                    "actual_ripple_risk_level": "",
                })

        return pd.DataFrame(results)

    def find_best(self, df: pd.DataFrame, n: int = 5,
                  objective: str = "P_total_W") -> pd.DataFrame:
        """Top-N feasible designs by loss."""
        feasible = df[df["feasible"]]
        if len(feasible) == 0:
            return df.iloc[:0]
        return feasible.nsmallest(min(n, len(feasible)), objective)
