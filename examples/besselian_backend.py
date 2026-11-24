"""Demonstrate the independent Besselian backend with NASA's 1999 elements."""

from pathlib import Path

from eclipsekit import BesselianElements, BesselianSolver, Observer, SolverConfig


ROOT = Path(__file__).resolve().parents[1]
ELEMENTS_PATH = ROOT / "data" / "validation" / "besselian_1999_aug11_nasa.json"


def main() -> None:
    elements = BesselianElements.from_json(ELEMENTS_PATH)
    solver = BesselianSolver(solver_config=SolverConfig(root_method="brent"))

    maximum_jd_tt = solver.find_global_maximum(elements)
    maximum_offset_s = (maximum_jd_tt - elements.epoch_tt_jd) * 86400.0
    print("NASA 1999-08-11 Besselian case")
    print(f"Geocentric closest approach: JD(TT) {maximum_jd_tt:.9f}")
    print(f"Offset from 11:00 TDT: {maximum_offset_s:.3f} s")

    ground_point = solver.central_line_point(
        elements, maximum_jd_tt, delta_t_seconds=63.7
    )
    if ground_point is not None:
        print(
            "Central line at closest approach: "
            f"{ground_point.latitude:.4f}°, {ground_point.longitude:.4f}°; "
            f"{ground_point.shadow_kind}; gamma={ground_point.gamma:.6f}"
        )

    observer = Observer(
        45.075, 24.30, name="Greatest-eclipse region", country="Romania"
    )
    local = solver.calculate_local(elements, observer, delta_t_seconds=63.7)
    print(f"Local classification: {local.eclipse_type}")
    for name in ("C1", "C2", "C3", "C4"):
        contact = local.contacts.get(name)
        if contact is not None:
            offset = (contact.jd_tt - elements.epoch_tt_jd) * 3600.0 * 24.0
            print(f"{name}: JD(TT) {contact.jd_tt:.9f} (offset {offset:+.2f} s)")
    print(f"Central duration: {local.central_phase_duration_seconds:.2f} s")
    print("Warnings:", list(local.warnings))
    print("\nThis example uses the published NASA ΔT=63.7 s for reproducibility.")


if __name__ == "__main__":
    main()
