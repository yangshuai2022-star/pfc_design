"""Winding loss calculations: skin effect and proximity effect."""

import numpy as np
from ..core.constants import skin_depth


def skin_effect_factor(d_wire_m: float, delta_m: float) -> float:
    """Skin effect AC/DC resistance ratio for a single round conductor.

    Uses the exact Bessel-function solution approximated by:
    Fr = 1 + (d/δ)^4 / (48 + 0.8*(d/δ)^4)  (for d/δ < 4)
    Fr ≈ (d/δ + 1) / 4                    (for d/δ > 4)

    Args:
        d_wire_m: wire diameter in meters
        delta_m: skin depth in meters

    Returns:
        AC resistance factor Fr = Rac/Rdc
    """
    if d_wire_m <= 0 or delta_m <= 0:
        return 1.0
    x = d_wire_m / delta_m
    if x < 2.0:
        return 1.0 + x ** 4 / (48 + 0.8 * x ** 4)
    else:
        return (x + 1) / 4


def proximity_factor(layers: int, d_wire_m: float, delta_m: float,
                     porosity: float = 0.8) -> float:
    """Proximity effect loss factor using Dowell's model.

    For a toroid winding with single-layer turns, proximity effect
    is relatively small compared to transformer windings.

    Args:
        layers: number of winding layers
        d_wire_m: conductor thickness/diameter in meters
        delta_m: skin depth in meters
        porosity: winding porosity (conductor width / layer width)

    Returns:
        Proximity AC resistance factor multiplier
    """
    if layers <= 1:
        return 1.0  # single layer: negligible proximity effect
    phi = porosity * (d_wire_m / delta_m)
    # Dowell's proximity factor
    g1 = (np.sinh(2 * phi) + np.sin(2 * phi)) / (np.cosh(2 * phi) - np.cos(2 * phi))
    g2 = (np.sinh(phi) - np.sin(phi)) / (np.cosh(phi) + np.cos(phi))
    return (5 * layers ** 2 - 1) / 15 * g2 * phi


def dc_resistance(rho: float, length_m: float, area_m2: float) -> float:
    """DC resistance of a wire segment.

    Args:
        rho: resistivity in Ohm·m
        length_m: wire length in meters
        area_m2: cross-sectional area in m²

    Returns:
        Resistance in Ohms
    """
    return rho * length_m / area_m2


def winding_loss_factor(freq: float, d_wire_m: float, n_layers: int = 2,
                        temperature: float = 100.0) -> tuple[float, float, float]:
    """Compute total AC loss factors for a winding.

    Args:
        freq: switching frequency in Hz
        d_wire_m: wire diameter in meters
        n_layers: number of equivalent layers
        temperature: winding temperature in °C

    Returns:
        (F_skin, F_prox, F_total) where Rac = Rdc * F_total
    """
    delta = skin_depth(freq, temperature)
    f_skin = skin_effect_factor(d_wire_m, delta)
    f_prox = proximity_factor(n_layers, d_wire_m, delta)
    f_total = f_skin * f_prox
    return f_skin, f_prox, f_total
