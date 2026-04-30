"""Design specification dataclass for two-phase interleaved PFC."""

from dataclasses import dataclass, field
from typing import Optional
import json
from pathlib import Path


@dataclass
class MosfetSpec:
    """MOSFET specification from database."""
    manufacturer: str
    part_number: str
    technology: str            # SiC, Si CoolMOS, Si SuperJunction, GaN
    vds_max: float
    id_25c: float
    id_100c: float
    rds_on_25c: float
    rds_on_150c: float
    rds_alpha: float
    qg_nc: float
    coss_er_pF: float
    tr_ns: float
    tf_ns: float
    vgs: float
    package: str = ""
    price_usd: float = 0.0

    @property
    def rds_on(self) -> float: return self.rds_on_25c
    @property
    def qg(self) -> float: return self.qg_nc * 1e-9
    @property
    def coss_er(self) -> float: return self.coss_er_pF * 1e-12
    @property
    def tr(self) -> float: return self.tr_ns * 1e-9
    @property
    def tf(self) -> float: return self.tf_ns * 1e-9


class MosfetDatabase:
    """Loadable database of MOSFET specifications."""

    def __init__(self, path: str | None = None):
        if path is None:
            path = str(Path(__file__).parent.parent / "data" / "mosfets.json")
        with open(path) as f:
            data = json.load(f)
        self._mosfets: list[MosfetSpec] = []
        for entry in data["mosfets"]:
            self._mosfets.append(MosfetSpec(**entry))

    @property
    def all(self) -> list[MosfetSpec]:
        return self._mosfets

    def get(self, part_number: str) -> Optional[MosfetSpec]:
        for m in self._mosfets:
            if m.part_number.lower() == part_number.lower():
                return m
        return None

    def query(self, vds_min: float = 0, vds_max: float = float('inf'),
              technology: str = "Si") -> list[MosfetSpec]:
        """Filter MOSFETs by voltage rating and technology.

        Use technology="" or "all" for no technology filter.
        Use technology="Si" to include Si CoolMOS and Si SuperJunction.
        """
        results = []
        tech = technology.strip().lower()
        for m in self._mosfets:
            if m.vds_max < vds_min or m.vds_max > vds_max:
                continue
            if tech and tech != "all":
                m_tech = m.technology.lower()
                if tech == "si":
                    if not m_tech.startswith("si ") or m_tech == "sic":
                        continue
                elif m_tech != tech:
                    continue
            results.append(m)
        return sorted(results, key=lambda x: x.rds_on_25c)


@dataclass
class DesignSpec:
    """All user-facing design inputs for a two-phase interleaved PFC.

    Uses UCC28070A average-current-mode control.
    """

    # Grid / output
    vin_min: float = 176.0
    vin_max: float = 264.0
    vin_nom: float = 220.0
    vout: float = 410.0
    pout_total: float = 7100.0
    n_phases: int = 2
    f_line: float = 50.0

    # Switching
    fsw: float = 65_000.0
    ripple_ratio: float = 0.3

    # Target efficiency
    eta_target: float = 0.96

    # Inductor constraints
    L_target: Optional[float] = None
    B_max_target: float = 0.25
    J_max: float = 6.0
    core_material_pref: str = "Sendust"

    # Diode
    diode_vf: float = 1.5
    diode_rd: float = 0.1
    diode_type: str = "SiC"

    # Bridge rectifier
    bridge_vf: float = 1.0
    bridge_rd: float = 0.0

    # Capacitor bank
    c_out_total: float = 1320e-6
    cap_esr: float = 0.15
    cap_n_parallel: int = 4
    cap_tan_delta: float = 0.25
    cap_rated_ripple: float = 3.0
    cap_rated_temp: float = 105.0
    cap_rated_life: float = 5000.0
    cap_ambient: float = 45.0
    cap_life_exponent: float = 3.0

    # Thermal
    t_ambient: float = 45.0

    @property
    def pout_per_phase(self) -> float:
        return self.pout_total / self.n_phases
