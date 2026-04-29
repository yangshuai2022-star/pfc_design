"""CLI entry point for PFC Design Calculator."""

import click
import numpy as np

from .core.spec import DesignSpec
from .core.operating_point import compute_mathcad_operating_point
from .magnetics.core_database import CoreDatabase
from .models.system import SystemAnalyzer
from .optimization.sweep import ParamSweep
from .optimization.pareto import find_pareto


@click.group()
def cli():
    """PFC Design Calculator - Two-phase interleaved PFC design tool."""
    pass


@cli.command()
@click.option("--vin", default=176.0, help="Minimum input voltage (Vrms)")
@click.option("--vout", default=410.0, help="Output voltage (Vdc)")
@click.option("--pout", default=7100.0, help="Total output power (W)")
@click.option("--fsw", default=65000.0, help="Switching frequency (Hz)")
@click.option("--ripple", default=1.0, help="Current ripple ratio")
@click.option("--core", default=None, help="Preferred core part number")
@click.option("--n-cores", default=2, help="Number of stacked cores")
@click.option("--plot/--no-plot", default=True, help="Show loss pie chart & L vs I curve")
@click.option("--save-plot", default=None, help="Save plots to directory")
def run(vin, vout, pout, fsw, ripple, core, n_cores, plot, save_plot):
    """Run a single PFC design analysis with plots."""
    spec = DesignSpec(
        vin_min=vin, vout=vout, pout_total=pout,
        fsw=fsw, ripple_ratio=ripple,
    )
    db = CoreDatabase()
    op = compute_mathcad_operating_point(spec)

    preferred_core = None
    if core:
        preferred_core = db.get_by_part_number(core)
        if preferred_core is None:
            click.echo(f"Core '{core}' not found. Using auto-selection.")

    analyzer = SystemAnalyzer(db)
    result = analyzer.analyze(spec, op, preferred_core, n_cores)

    _print_summary(result)
    _print_loss_table(result)

    if plot:
        if save_plot is None:
            import tempfile, os
            save_plot = os.path.join(os.path.expanduser("~"), "pfc_design", "output")
        _show_plots(result, save_plot)


@cli.command()
@click.option("--vin", default=176.0, help="Minimum input voltage (Vrms)")
@click.option("--vout", default=410.0, help="Output voltage (Vdc)")
@click.option("--pout", default=7100.0, help="Total output power (W)")
@click.option("--fsw-start", default=40000.0, help="fsw sweep start (Hz)")
@click.option("--fsw-stop", default=120000.0, help="fsw sweep stop (Hz)")
@click.option("--fsw-step", default=10000.0, help="fsw sweep step (Hz)")
@click.option("--ripple-start", default=0.15, help="Ripple ratio start")
@click.option("--ripple-stop", default=0.50, help="Ripple ratio stop")
@click.option("--ripple-n", default=8, help="Ripple ratio points")
@click.option("--n-cores", default=2, help="Number of stacked cores")
def optimize(vin, vout, pout, fsw_start, fsw_stop, fsw_step,
             ripple_start, ripple_stop, ripple_n, n_cores):
    """Sweep design variables to find optimal parameters."""
    spec = DesignSpec(vin_min=vin, vout=vout, pout_total=pout)

    sweep_vars = {
        "fsw": np.arange(fsw_start, fsw_stop + fsw_step/2, fsw_step),
        "ripple_ratio": np.linspace(ripple_start, ripple_stop, int(ripple_n)),
    }

    click.echo("\nRunning parameter sweep...")
    sweeper = ParamSweep()
    df = sweeper.sweep(spec, sweep_vars, n_cores=n_cores)

    # Show results
    feasible = df[df["feasible"]]
    click.echo(f"\n=== Sweep Results ===")
    click.echo(f"Total designs: {len(df)}, Feasible: {len(feasible)}")

    if len(feasible) > 0:
        best = df[df["feasible"]].nsmallest(1, "P_total_W").iloc[0]
        click.echo(f"\n--- Best Design ---")
        click.echo(f"fsw: {best['fsw']/1000:.0f}kHz, ripple: {best['ripple_ratio']:.2f}")
        click.echo(f"Core: {best['core']}, Turns: {best['turns']}, L_eff: {best['L_eff_uH']:.0f}uH")
        click.echo(f"Total Loss: {best['P_total_W']:.1f}W, Efficiency: {best['efficiency_pct']:.2f}%")
        click.echo(f"  Inductor: {best['P_ind_W']:.1f}W")
        click.echo(f"  MOSFET: {best['P_mosfet_W']:.1f}W")
        click.echo(f"  Diode: {best['P_diode_W']:.1f}W")
        click.echo(f"  Bridge: {best['P_bridge_W']:.1f}W")
        click.echo(f"  Capacitor: {best['P_cap_W']:.1f}W")

        # Show efficiency plateau
        click.echo(f"\n--- Top 5 Designs ---")
        top5 = feasible.nsmallest(5, "P_total_W")
        for i, (_, row) in enumerate(top5.iterrows()):
            click.echo(f"  #{i+1}: fsw={row['fsw']/1000:.0f}kHz r={row['ripple_ratio']:.2f} "
                       f"core={row['core']} loss={row['P_total_W']:.1f}W η={row['efficiency_pct']:.2f}%")

    click.echo(f"\nFull results saved to console above.")


@cli.command()
@click.option("--material", default="Sendust", help="Material class filter (Sendust/Ferrite/MPP/HighFlux)")
def cores(material):
    """List available magnetic cores."""
    db = CoreDatabase()
    results = db.query(material_class=material, max_results=50)
    click.echo(f"\n{'Part Number':<25} {'Material':<20} {'OD':>6} {'Ae':>6} {'AL':>7} {'Aw':>6}")
    click.echo("-" * 78)
    for c in results:
        click.echo(f"{c.part_number:<25} {c.material:<20} {c.od_mm:>4.1f}mm "
                   f"{c.ae_cm2:>4.2f}cm² {c.al_nH_per_t2:>5.0f}  {c.aw_cm2:>4.2f}cm²")


@cli.command()
def version():
    """Show version."""
    from . import __version__
    click.echo(f"pfc_design v{__version__}")


def _print_summary(result):
    """Compact design summary."""
    spec = result["spec"]
    design = result["inductor_design"]
    click.echo(f"\n=== PFC Design Summary ===")
    click.echo(f"Input: {spec.vin_min}-{spec.vin_max}Vrms  |  Output: {spec.vout}Vdc  |  "
               f"Power: {spec.pout_total/1000:.1f}kW  |  fsw: {spec.fsw/1000:.0f}kHz")
    click.echo(f"\n--- Inductor ---")
    click.echo(f"Core: {design.core.part_number} ({design.core.material}) x{design.n_cores}")
    click.echo(f"N={design.n_turns}  |  L_target={design.L_target_uh:.0f}uH  |  "
               f"L_noload={design.L_noload_uh:.0f}uH  |  L_eff={design.L_eff_at_ipeak_uh:.0f}uH")
    click.echo(f"Wire: {design.wire_d_mm}mm x{design.n_parallel}  |  Window fill: {design.kw*100:.1f}%")


def _print_loss_table(result):
    """Formatted loss table."""
    click.echo(f"\n--- Loss Breakdown ---")
    click.echo(f"{'Component':<25} {'Loss (W)':>8}  {'%':>6}")
    click.echo("-" * 42)
    total = result["total_loss"]
    for name, val in result["breakdown"].items():
        if val > 0.3:
            pct = val / total * 100 if total > 0 else 0
            click.echo(f"{name:<25} {val:>7.1f}W {pct:>5.1f}%")
    click.echo("-" * 42)
    click.echo(f"{'TOTAL':<25} {total:>7.1f}W {'100.0%':>6}")
    click.echo(f"{'Efficiency':<25} {result['efficiency']*100:>7.2f}%")


def _show_plots(result, save_dir=None):
    """Generate and display plots."""
    import matplotlib
    matplotlib.use('Agg')  # headless backend for WSL/macOS
    import matplotlib.pyplot as plt

    spec = result["spec"]
    op = result["op"]
    design = result["inductor_design"]
    core = design.core

    # Ensure save directory exists
    if save_dir:
        import os
        os.makedirs(save_dir, exist_ok=True)

    # 1. Loss pie chart
    fig, ax = plt.subplots(figsize=(10, 7))
    items = {k: v for k, v in result["breakdown"].items() if v > result["total_loss"] * 0.005}
    colors = plt.cm.Set3(np.linspace(0, 1, len(items)))
    wedges, texts, autotexts = ax.pie(
        list(items.values()), labels=None, autopct='%1.1f%%',
        startangle=90, pctdistance=0.82, colors=colors,
        wedgeprops=dict(width=0.35, edgecolor='w')
    )
    # Improve autotext readability
    for t in autotexts:
        t.set_fontsize(9)
        t.set_fontweight('bold')

    legend_labels = [f"{l}: {s:.1f}W" for l, s in items.items()]
    ax.legend(wedges, legend_labels, title="Components",
              loc="center left", bbox_to_anchor=(1, 0, 0.5, 1), fontsize=9)
    ax.text(0, 0, f"η = {result['efficiency']*100:.1f}%\nTotal Loss\n{result['total_loss']:.1f}W",
            ha='center', va='center', fontsize=14, fontweight='bold')
    ax.set_title("PFC Loss Breakdown", fontsize=14, fontweight='bold')
    plt.tight_layout()
    if save_dir:
        plt.savefig(f"{save_dir}/loss_pie.png", dpi=150, bbox_inches='tight')
        click.echo(f"Pie chart saved to {save_dir}/loss_pie.png")
    plt.close(fig)

    # 2. L vs I saturation curve
    from .magnetics.saturation import generate_L_vs_I
    i_max = design.n_turns * spec.ripple_ratio * 5 + 10
    i_arr, L_arr = generate_L_vs_I(
        design.L_noload_uh, design.n_turns, core.le_cm,
        core.dc_bias_coeffs, max(i_max, op.iin_peak * 2)
    )

    fig2, ax2 = plt.subplots(figsize=(8, 5))
    ax2.plot(i_arr, L_arr, 'b-', linewidth=2)
    ax2.axvline(x=op.iin_rms, color='g', linestyle='--', label=f'Irms = {op.iin_rms:.1f}A')
    ax2.axvline(x=op.iin_peak, color='r', linestyle='--', label=f'Ipeak = {op.iin_peak:.1f}A')
    ax2.axhline(y=design.L_target_uh, color='orange', linestyle=':', label=f'L_target = {design.L_target_uh:.0f}uH')
    ax2.set_xlabel("DC Current (A)")
    ax2.set_ylabel("Inductance (μH)")
    ax2.set_title(f"Inductance vs DC Bias (L₀={design.L_noload_uh:.0f}μH, N={design.n_turns})")
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    plt.tight_layout()
    if save_dir:
        plt.savefig(f"{save_dir}/L_vs_I.png", dpi=150, bbox_inches='tight')
        click.echo(f"L vs I curve saved to {save_dir}/L_vs_I.png")
    plt.show()
    plt.close(fig2)

    # Auto-open in Windows file explorer
    if save_dir:
        import subprocess
        win_path = save_dir.replace("/home/yangs", "\\\\wsl$\\Ubuntu\\home\\yangs")
        subprocess.run(["explorer.exe", win_path], capture_output=True)


if __name__ == "__main__":
    cli()
