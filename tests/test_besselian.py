from __future__ import annotations

from dataclasses import replace
import math
from pathlib import Path

import pytest

from eclipsekit import (
    BesselianConfig,
    BesselianElements,
    BesselianPolynomial,
    BesselianSolver,
    EclipseConfig,
    Observer,
    SolverConfig,
)


ROOT = Path(__file__).resolve().parents[1]
NASA_1999 = ROOT / "data" / "validation" / "besselian_1999_aug11_nasa.json"


@pytest.fixture(scope="module")
def elements() -> BesselianElements:
    return BesselianElements.from_json(NASA_1999)


def test_besselian_polynomial_evaluates_values_and_derivative() -> None:
    polynomial = BesselianPolynomial((1.0, 2.0, 3.0, 4.0))
    assert polynomial.evaluate(2.0) == pytest.approx(49.0)
    assert polynomial.derivative(2.0) == pytest.approx(62.0)


def test_besselian_polynomial_rejects_invalid_coefficients() -> None:
    with pytest.raises(ValueError, match="1 to 4"):
        BesselianPolynomial(())
    with pytest.raises(ValueError, match="finite"):
        BesselianPolynomial((1.0, math.nan))


def test_besselian_elements_json_round_trip(elements: BesselianElements, tmp_path: Path) -> None:
    destination = tmp_path / "besselian.json"
    elements.to_json(destination)
    loaded = BesselianElements.from_json(destination)
    assert loaded.to_dict() == elements.to_dict()


def test_besselian_elements_enforce_published_validity(elements: BesselianElements) -> None:
    with pytest.raises(ValueError, match="validity"):
        elements.evaluate(elements.epoch_tt_jd + 3.1 / 24.0)


def test_besselian_evaluation_returns_units_and_rates(elements: BesselianElements) -> None:
    snapshot = elements.evaluate(elements.epoch_tt_jd)
    assert snapshot.x == pytest.approx(0.0700420)
    assert snapshot.y == pytest.approx(0.5028410)
    assert snapshot.d_deg == pytest.approx(15.3273401)
    assert snapshot.mu_deg == pytest.approx(343.687408)
    assert snapshot.rates_per_hour["x"] == pytest.approx(0.5443035)
    assert snapshot.gamma == pytest.approx(math.hypot(snapshot.x, snapshot.y))


def test_observer_projection_equator_and_delta_t_convention(elements: BesselianElements) -> None:
    solver = BesselianSolver()
    # At longitude = -mu(UT1), an equatorial observer has zero fundamental-plane xi.
    snapshot = elements.evaluate(elements.epoch_tt_jd)
    corrected_mu = snapshot.mu_deg - 63.7 * (1.002738 * 15.0 / 3600.0)
    observer = Observer(0.0, (-corrected_mu + 180.0) % 360.0 - 180.0, 0.0)
    state = solver.observer_state(
        elements, observer, elements.epoch_tt_jd, delta_t_seconds=63.7
    )
    expected_mu = snapshot.mu_deg - 63.7 * (1.002738 * 15.0 / 3600.0)
    assert state.mu_ut1_deg == pytest.approx(expected_mu)
    assert state.xi == pytest.approx(0.0, abs=1.0e-12)
    assert state.eta == pytest.approx(-math.sin(math.radians(snapshot.d_deg)), abs=2.0e-5)
    assert state.zeta == pytest.approx(math.cos(math.radians(snapshot.d_deg)), abs=2.0e-5)


def test_ut1_mu_convention_does_not_apply_delta_t(elements: BesselianElements) -> None:
    ut1_elements = replace(elements, mu_convention="ut1")
    state = BesselianSolver().observer_state(
        ut1_elements, Observer(0.0, 0.0), elements.epoch_tt_jd,
        delta_t_seconds=63.7,
    )
    assert state.mu_ut1_deg == pytest.approx(elements.mu.evaluate(0.0))


def test_nan_delta_t_is_rejected(elements: BesselianElements) -> None:
    with pytest.raises(ValueError, match="finite"):
        BesselianSolver().observer_state(
            elements, Observer(0.0, 0.0), elements.epoch_tt_jd,
            delta_t_seconds=math.nan,
        )


def test_nasa_1999_global_maximum_and_central_line_match_published_values(
    elements: BesselianElements,
) -> None:
    solver = BesselianSolver()
    maximum = solver.find_global_maximum(elements)
    offset_seconds = (maximum - elements.epoch_tt_jd) * 86400.0
    assert offset_seconds == pytest.approx(249.1, abs=0.5)

    point = solver.central_line_point(elements, maximum, delta_t_seconds=63.7)
    assert point is not None
    assert point.shadow_kind == "umbral"
    assert point.latitude == pytest.approx(45.1, abs=0.03)
    assert point.longitude == pytest.approx(24.3, abs=0.05)


def test_nasa_1999_local_circumstances_resolve_totality_and_contacts(
    elements: BesselianElements,
) -> None:
    solver = BesselianSolver(solver_config=SolverConfig(root_method="brent"))
    observer = Observer(45.075, 24.30, name="Greatest-eclipse region", country="Romania")
    result = solver.calculate_local(elements, observer, delta_t_seconds=63.7)
    assert result.eclipse_type == "total"
    assert set(result.contacts) == {"C1", "C2", "C3", "C4"}
    assert result.partial_phase_duration_seconds is not None
    assert result.partial_phase_duration_seconds > result.central_phase_duration_seconds
    assert result.central_phase_duration_seconds == pytest.approx(143.0, abs=2.0)
    assert all(contact.root_result.converged for contact in result.contacts.values())
    assert result.to_dict()["eclipse_type"] == "total"


def test_positive_signed_l2_is_annular(elements: BesselianElements) -> None:
    annular = replace(
        elements,
        l2=(0.0060000, 0.0001163, -0.0000116, 0.0),
    )
    result = BesselianSolver().calculate_local(
        annular, Observer(45.075, 24.30), delta_t_seconds=63.7
    )
    assert result.eclipse_type == "annular"
    maximum = BesselianSolver().find_global_maximum(annular)
    point = BesselianSolver().central_line_point(annular, maximum, delta_t_seconds=63.7)
    assert point is not None
    assert point.shadow_kind == "antumbral"


def test_no_eclipse_outside_the_path(elements: BesselianElements) -> None:
    result = BesselianSolver().calculate_local(
        elements, Observer(0.0, 0.0), delta_t_seconds=63.7
    )
    assert result.eclipse_type == "none"
    assert result.maximum_jd_tt is None
    assert not result.contacts


def test_global_central_line_samples_are_inside_element_validity(
    elements: BesselianElements,
) -> None:
    solver = BesselianSolver()
    start = elements.epoch_tt_jd - 1.0 / 24.0
    end = elements.epoch_tt_jd + 1.0 / 24.0
    path = solver.global_central_line(elements, start, end, samples=11, delta_t_seconds=63.7)
    assert path
    assert all(-90.0 <= item.latitude <= 90.0 for item in path)
    assert all(-180.0 <= item.longitude <= 180.0 for item in path)


def test_besselian_config_is_serialized_and_validated() -> None:
    config = EclipseConfig(besselian=BesselianConfig(root_scan_samples=151))
    assert config.to_dict()["besselian"]["root_scan_samples"] == 151
    with pytest.raises(ValueError, match="smaller than 1"):
        BesselianConfig(earth_flattening=1.0)
    with pytest.raises(ValueError, match="integer"):
        BesselianConfig(root_scan_samples=5.5)
