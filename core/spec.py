"""Design specification dataclass for two-phase interleaved PFC."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DesignSpec:
    """All user-facing design inputs for a two-phase interleaved PFC.

    Uses UCC28070A average-current-mode control.
    """

    # Grid / output
    vin_min: float = 176.0        # Vrms
    vin_max: float = 264.0        # Vrms
    vin_nom: float = 220.0        # Vrms
    vout: float = 410.0           # Vdc
    pout_total: float = 7100.0    # W, total system (Mathcad default)
    n_phases: int = 2             # interleaved
    f_line: float = 50.0          # Hz

    # Switching
    fsw: float = 65_000.0         # Hz per phase
    ripple_ratio: float = 1.0     # delta_I_peak / I_peak (Mathcad default = 1)

    # Target efficiency (for initial current estimate)
    eta_target: float = 0.96

    # Inductor constraints
    L_target: Optional[float] = None   # uH; auto-size from ripple_ratio if None
    B_max_target: float = 0.25        # T, peak AC flux density target
    J_max: float = 6.0                # A/mm², current density (Mathcad default = 6)
    core_material_pref: str = "Sendust"

    # MOSFET (per-phase)
    mosfet_vds_max: float = 650.0
    mosfet_id_max: float = 47.0        # A at 25°C
    mosfet_rds_on: float = 0.100       # Ohm at 25°C
    mosfet_rds_alpha: float = 0.004    # 1/K temp coef
    mosfet_qg: float = 100e-9          # C, total gate charge
    mosfet_coss_er: float = 200e-12    # F, energy-related Coss at Vout
    mosfet_tr: float = 5e-9            # s, rise time
    mosfet_tf: float = 4.5e-9          # s, fall time
    mosfet_vgs: float = 14.0           # V, gate drive voltage

    # Diode
    diode_vf: float = 1.5              # V, forward voltage
    diode_rd: float = 0.1              # Ohm, differential resistance
    diode_type: str = "SiC"            # Si or SiC

    # Bridge rectifier
    bridge_vf: float = 1.0             # V per diode

    # Capacitor bank
    c_out_total: float = 1320e-6       # F, total (4 × 330uF)
    cap_esr: float = 0.15              # Ohm each
    cap_n_parallel: int = 4
    cap_tan_delta: float = 0.25
    cap_rated_ripple: float = 3.0      # Arms at rated temp
    cap_rated_temp: float = 105.0      # °C
    cap_rated_life: float = 5000.0     # hours
    cap_ambient: float = 45.0          # °C, ambient temperature
    cap_life_exponent: float = 3.0     # lifetime exponent (3-5)

    # Thermal
    t_ambient: float = 45.0            # °C

    @property
    def pout_per_phase(self) -> float:
        return self.pout_total / self.n_phases
