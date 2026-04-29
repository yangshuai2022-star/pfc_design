"""Parameter sweep engine for PFC design optimization."""

import itertools
import numpy as np
import pandas as pd

from ..core.spec import DesignSpec
from ..core.operating_point import compute_mathcad_operating_point
from ..magnetics.core_database import CoreDatabase
from ..magnetics.core_entry import CoreSpec
from ..models.system import SystemAnalyzer


class ParamSweep:
    """Brute-force grid sweep over design variables."""

    def __init__(self, db: CoreDatabase | None = None):
        self.db = db or CoreDatabase()
        self.analyzer = SystemAnalyzer(self.db)

    def sweep(self, base_spec: DesignSpec,
              sweep_vars: dict[str, np.ndarray],
              n_cores: int = 2) -> pd.DataFrame:
        """Run a grid sweep over specified variables.

        Args:
            base_spec: base design specification
            sweep_vars: {'var_name': array_of_values}
            n_cores: number of stacked cores

        Returns:
            DataFrame with one row per design point
        """
        cores = self.db.top_for_pfc(ae_min_cm2=0.5, material_class="Sendust", n=10)
        results = []

        keys = list(sweep_vars.keys())
        values = list(sweep_vars.values())

        for combo in itertools.product(*values):
            params = dict(zip(keys, combo))
            spec = DesignSpec(**{k: v for k, v in base_spec.__dict__.items()
                                 if not k.startswith('_')})

            # Apply sweep variables
            if "fsw" in params:
                spec.fsw = float(params["fsw"])
            if "ripple_ratio" in params:
                spec.ripple_ratio = float(params["ripple_ratio"])

            # Select core
            core_idx = int(params.get("core_idx", 0))
            core = cores[core_idx % len(cores)]

            try:
                op = compute_mathcad_operating_point(spec)
                result = self.analyzer.analyze(spec, op, preferred_core=core,
                                                n_cores=n_cores)
                design = result["inductor_design"]

                # Check constraints
                feasible = True
                constraints = {}
                b_max = design.n_turns * result["losses"]["inductor"].metadata["B_max_T"]
                if b_max > core.bs_T * 0.7:
                    feasible = False
                    constraints["B_max"] = f"{b_max:.3f}T > {core.bs_T*0.7:.3f}T"

                if design.kw > 0.4:
                    feasible = False
                    constraints["window_fill"] = f"{design.kw:.3f} > 0.4"

                sat_pct = result["losses"]["inductor"].metadata["saturation_pct"]
                if sat_pct < 20:
                    feasible = False
                    constraints["saturation"] = f"{sat_pct:.0f}% < 20%"

                results.append({
                    "fsw": spec.fsw,
                    "ripple_ratio": spec.ripple_ratio,
                    "core": core.part_number,
                    "turns": design.n_turns,
                    "L_noload_uH": design.L_noload_uh,
                    "L_eff_uH": design.L_eff_at_ipeak_uh,
                    "P_total_W": result["total_loss"],
                    "efficiency_pct": result["efficiency"] * 100,
                    "P_ind_W": result["losses"]["inductor"].power_loss_W,
                    "P_mosfet_W": result["losses"]["mosfet"].power_loss_W,
                    "P_diode_W": result["losses"]["diode"].power_loss_W,
                    "P_bridge_W": result["losses"]["bridge"].power_loss_W,
                    "P_cap_W": result["losses"]["capacitor"].power_loss_W,
                    "feasible": feasible,
                    "constraints": str(constraints) if constraints else "",
                })

            except Exception as e:
                results.append({
                    "fsw": spec.fsw,
                    "ripple_ratio": spec.ripple_ratio,
                    "core": core.part_number,
                    "turns": 0,
                    "L_noload_uH": 0,
                    "L_eff_uH": 0,
                    "P_total_W": np.nan,
                    "efficiency_pct": np.nan,
                    "P_ind_W": np.nan,
                    "P_mosfet_W": np.nan,
                    "P_diode_W": np.nan,
                    "P_bridge_W": np.nan,
                    "P_cap_W": np.nan,
                    "feasible": False,
                    "constraints": f"Error: {e}",
                })

        return pd.DataFrame(results)

    def find_best(self, df: pd.DataFrame, n: int = 5,
                  objective: str = "P_total_W") -> pd.DataFrame:
        """Find top-N feasible designs by objective."""
        feasible = df[df["feasible"]]
        return feasible.nsmallest(n, objective)
