"""Fine-tuning optimization using scipy."""

import numpy as np
from scipy.optimize import minimize

from ..core.spec import DesignSpec
from ..core.operating_point import compute_mathcad_operating_point
from ..magnetics.core_database import CoreDatabase
from ..magnetics.core_entry import CoreSpec
from ..models.system import SystemAnalyzer


def optimize_loss(spec: DesignSpec, core: CoreSpec, db: CoreDatabase,
                  initial: tuple[float, float] = (45, 0.25),
                  bounds: tuple[tuple[float, float], tuple[float, float]] = ((30, 80), (0.1, 0.6))
                  ) -> dict:
    """Fine-tune turns and ripple ratio to minimize total loss.

    Args:
        spec: base design spec
        core: selected core
        db: core database
        initial: (turns_initial, ripple_initial)
        bounds: ((turns_min, turns_max), (ripple_min, ripple_max))

    Returns:
        Optimization result dict
    """
    analyzer = SystemAnalyzer(db)
    history = []

    def objective(x):
        turns, ripple = x
        turns = int(round(turns))
        spec.ripple_ratio = float(ripple)
        op = compute_mathcad_operating_point(spec)
        result = analyzer.analyze(spec, op, preferred_core=core)
        total_loss = result["total_loss"]
        history.append({"turns": turns, "ripple": ripple, "loss": total_loss,
                        "efficiency": result["efficiency"]})
        return total_loss

    res = minimize(
        objective, x0=list(initial),
        bounds=bounds,
        method='L-BFGS-B',
        options={'maxiter': 50, 'disp': False}
    )

    best_turns = int(round(res.x[0]))
    best_ripple = res.x[1]

    return {
        "best_turns": best_turns,
        "best_ripple": best_ripple,
        "best_loss": res.fun,
        "success": res.success,
        "history": history,
    }
