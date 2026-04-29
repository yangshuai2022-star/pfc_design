"""Verification tests against Mathcad reference values.

Cross-checks key computed values against the original Mathcad PDF.
Tolerances are set to account for model simplifications.

Run with: python -m pytest pfc_design/tests/verify_mathcad.py -v
"""

import pytest
import numpy as np

from ..core.spec import DesignSpec
from ..core.operating_point import compute_mathcad_operating_point
from ..magnetics.core_database import CoreDatabase
from ..models.system import SystemAnalyzer


@pytest.fixture
def mathcad_spec():
    """Create the Mathcad reference specification."""
    return DesignSpec(
        vin_min=176.0, vin_max=264.0, vin_nom=220.0,
        vout=410.0, pout_total=7100.0, n_phases=2,
        f_line=50.0, fsw=65_000.0, ripple_ratio=1.0,
        eta_target=0.96,
        core_material_pref="Sendust",
        mosfet_vds_max=650.0, mosfet_id_max=47.0,
        mosfet_rds_on=0.100, mosfet_qg=100e-9,
        mosfet_coss_er=200e-12, mosfet_tr=5e-9, mosfet_tf=4.5e-9,
        mosfet_vgs=14.0,
        diode_vf=1.5, diode_rd=0.1, diode_type="SiC",
        bridge_vf=1.0,
        c_out_total=1320e-6, cap_esr=0.15, cap_n_parallel=4,
        cap_tan_delta=0.25,
    )


@pytest.fixture
def db():
    return CoreDatabase()


@pytest.fixture
def mathcad_op(mathcad_spec):
    return compute_mathcad_operating_point(mathcad_spec)


class TestOperatingPoint:
    def test_iin_rms(self, mathcad_op):
        """Mathcad: Iin_max_rms = 21.011 A"""
        assert mathcad_op.iin_rms == pytest.approx(21.011, rel=0.02)

    def test_d_min(self, mathcad_op):
        """Mathcad: Dmin = 0.393 at low line peak"""
        assert mathcad_op.d_min == pytest.approx(0.393, rel=0.05)

    def test_iin_peak(self, mathcad_op):
        """Iin_peak = sqrt(2) * Iin_rms ≈ 29.71 A"""
        assert mathcad_op.iin_peak == pytest.approx(29.71, rel=0.02)


class TestInductorDesign:
    def test_L_target(self, mathcad_spec, mathcad_op, db):
        """Mathcad: L_pfc = 182.251 uH"""
        analyzer = SystemAnalyzer(db)
        result = analyzer.analyze(mathcad_spec, mathcad_op)
        design = result["inductor_design"]
        assert design.L_target_uh == pytest.approx(182.25, rel=0.05)

    def test_N_turns_reasonable(self, mathcad_spec, mathcad_op, db):
        """Mathcad: N = 60 turns"""
        analyzer = SystemAnalyzer(db)
        result = analyzer.analyze(mathcad_spec, mathcad_op)
        design = result["inductor_design"]
        # Within reasonable range
        assert 35 <= design.n_turns <= 80


class TestSystemEfficiency:
    def test_efficiency_reasonable(self, mathcad_spec, mathcad_op, db):
        """Mathcad: eta_test = 96.7%"""
        analyzer = SystemAnalyzer(db)
        result = analyzer.analyze(mathcad_spec, mathcad_op)
        eta = result["efficiency"]
        # Within reasonable range for PFC
        assert 0.90 <= eta <= 0.99

    def test_total_loss_reasonable(self, mathcad_spec, mathcad_op, db):
        """Total loss should be in a reasonable range for ~7kW system."""
        analyzer = SystemAnalyzer(db)
        result = analyzer.analyze(mathcad_spec, mathcad_op)
        # Between 50W and 300W for a ~7kW PFC
        assert 50 <= result["total_loss"] <= 300

    def test_bridge_loss(self, mathcad_spec, mathcad_op, db):
        """Mathcad: Pbridge = 37.833 W"""
        analyzer = SystemAnalyzer(db)
        result = analyzer.analyze(mathcad_spec, mathcad_op)
        bridge = result["losses"]["bridge"].power_loss_W
        assert bridge == pytest.approx(37.83, rel=0.10)
