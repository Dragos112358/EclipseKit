"""Phase 7.5 example: shadow-path and implicit contact-time uncertainty."""

from pathlib import Path

from eclipsekit import (
    UncertaintyBudget,
    altitude_uncertainty_to_time_seconds,
    estimate_contact_time_uncertainty,
    propagate_shadow_path_position_uncertainty,
    write_uncertainty_report,
)


def main() -> None:
    budget = UncertaintyBudget.from_standard_deviations(
        ("along_track_position_bias", "cross_track_position_bias"),
        (0.20, 0.40),
        units=("km", "km"),
        correlation=((1.0, 0.25), (0.25, 1.0)),
        source_descriptions=(
            "Synthetic demonstration values only; replace with documented source uncertainties.",
        ),
    )

    # The callback maps perturbed ephemeris/geometry inputs to local tangent-plane
    # east/north offsets around one nominal shadow-path point.
    propagated = propagate_shadow_path_position_uncertainty(
        lambda x: (0.8 * x[0] + 0.1 * x[1], -0.2 * x[0] + 1.1 * x[1]),
        (0.0, 0.0),
        budget,
        method="linear",
        confidence_level=0.95,
    )

    # Example contact equation g(t,p)=0. The coefficients have units s/km.
    # A production callback must return the actual signed geometric contact
    # residual, evaluated by the eclipse model for each perturbed parameter set.
    contact = estimate_contact_time_uncertainty(
        "C2",
        100.0,
        (0.0, 0.0),
        budget,
        lambda t, p: t - (100.0 + 1.5 * p[0] + 0.25 * p[1]),
    )

    # Requires a validated local contact altitude rate in metres/second.
    example_limb_time_sigma = altitude_uncertainty_to_time_seconds(80.0, 400.0)

    output_directory = Path("reports/phase7_5")
    report_paths = write_uncertainty_report(propagated, output_directory)
    print(f"Shadow-path east sigma: {propagated.standard_deviations[0]:.6f} km")
    print(f"Shadow-path north sigma: {propagated.standard_deviations[1]:.6f} km")
    print(f"Contact C2 one-sigma timing uncertainty: {contact.uncertainty_seconds:.6f} s")
    print(f"Contact C2 time sensitivity: {contact.time_sensitivity_seconds_per_unit}")
    print(f"Illustrative lunar-limb timing sigma: {example_limb_time_sigma:.6f} s")
    for kind, path in report_paths.items():
        print(f"{kind.upper()}: {path}")
    print("NOTE: Example input uncertainties are synthetic, not real-eclipse data.")


if __name__ == "__main__":
    main()
