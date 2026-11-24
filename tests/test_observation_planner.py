from __future__ import annotations

from types import SimpleNamespace

import pytest

from eclipsekit import (
    EclipseEngine,
    Observer,
    ObservationScoreWeights,
)


class FakeTime:
    tt = 2461265.5
    utc = (2026, 8, 12, 12, 0, 0.0)

    def utc_iso(self, delimiter="T", places=3):
        return "2026-08-12T12:00:00.000Z"


class FakeResult:
    def __init__(self, obscuration, altitude, duration, *, eclipse_type="partial"):
        self.eclipse_type = eclipse_type
        self.obscuration_percent = obscuration
        self.sun_altitude_deg = altitude
        self.sun_azimuth_deg = 180.0
        self.partial_phase_duration_seconds = duration
        self.central_phase_duration_seconds = 90.0 if eclipse_type in {"total", "annular"} else None
        self.magnitude = 0.8
        self.maximum = FakeTime()
        self.contacts = SimpleNamespace(as_dict=lambda: {"C1": None, "C2": None, "C3": None, "C4": None})

    def to_dict(self):
        return {"eclipse_type": self.eclipse_type}


class FakeEngine:
    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.calls = []

    def time(self, value):
        return FakeTime()

    def calculate_local(self, observer, when, **kwargs):
        self.calls.append((observer, when, kwargs))
        outcome = self.outcomes.get(observer.name, "missing")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _observers():
    return [
        Observer(40.0, -4.0, name="Alpha", country="Spain"),
        Observer(42.0, -3.0, name="Bravo", country="Spain"),
        Observer(43.0, -2.0, name="Charlie", country="Spain"),
        Observer(44.0, -1.0, name="Delta", country="Spain"),
    ]


def test_score_weights_normalize_without_mutating_relative_values():
    weights = ObservationScoreWeights(5, 3, 2)
    assert weights.normalized() == {"obscuration": 0.5, "solar_altitude": 0.3, "partial_duration": 0.2}
    assert weights.to_dict() == {"obscuration": 5.0, "solar_altitude": 3.0, "partial_duration": 2.0}


@pytest.mark.parametrize("values", [(0, 0, 0), (-1, 1, 1), (True, 1, 1), (float("nan"), 1, 1)])
def test_score_weights_reject_invalid_values(values):
    with pytest.raises(ValueError):
        ObservationScoreWeights(*values)


def test_plan_ranks_sites_by_weighted_score_and_uses_horizon_filter():
    observers = _observers()
    engine = FakeEngine({
        "Alpha": FakeResult(80, 40, 1800, eclipse_type="total"),
        "Bravo": FakeResult(100, 5, 3600, eclipse_type="partial"),
        "Charlie": FakeResult(55, 30, 2400),
        "Delta": None,
    })

    plan = EclipseEngine.plan_observations(
        engine, observers, "2026-08-12", minimum_sun_altitude_deg=10.0
    )

    assert [site.observer.name for site in plan.recommended_sites] == ["Alpha", "Charlie"]
    assert [site.rank for site in plan.recommended_sites] == [1, 2]
    below = next(site for site in plan.sites if site.observer.name == "Bravo")
    assert below.status == "below_minimum_sun_altitude"
    assert below.visibility_class == "very_low"
    assert len(plan.no_eclipse_sites) == 1
    assert [call[2]["find_next_if_none"] for call in engine.calls] == [False] * 4
    assert all(call[2]["include_sunrise_sunset"] is False for call in engine.calls)
    assert all(call[2]["include_planets"] is False for call in engine.calls)
    assert all(call[2]["include_shadow_metrics"] is False for call in engine.calls)


def test_plan_retains_errors_and_can_be_configured_to_raise():
    observers = _observers()
    engine = FakeEngine({"Alpha": RuntimeError("bad observer"), "Bravo": None,
                         "Charlie": None, "Delta": None})
    plan = EclipseEngine.plan_observations(engine, observers, "2026-08-12")
    assert len(plan.error_sites) == 1
    assert "bad observer" in plan.error_sites[0].message

    engine = FakeEngine({"Alpha": RuntimeError("bad observer")})
    with pytest.raises(RuntimeError, match="bad observer"):
        EclipseEngine.plan_observations(
            engine, observers[:1], "2026-08-12", continue_on_error=False
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"search_window_hours": 0},
        {"search_window_hours": 37},
        {"minimum_sun_altitude_deg": 91},
        {"full_sun_altitude_score_deg": 0},
        {"full_sun_altitude_score_deg": 91},
        {"maximum_partial_duration_seconds": 0},
        {"continue_on_error": 1},
    ],
)
def test_plan_rejects_invalid_options(kwargs):
    with pytest.raises(ValueError):
        EclipseEngine.plan_observations(FakeEngine({}), _observers()[:1], "2026-08-12", **kwargs)


def test_plan_rejects_empty_or_invalid_observers():
    with pytest.raises(ValueError, match="at least one observer"):
        EclipseEngine.plan_observations(FakeEngine({}), [], "2026-08-12")
    with pytest.raises(TypeError, match="Observer"):
        EclipseEngine.plan_observations(FakeEngine({}), [object()], "2026-08-12")


def test_plan_markdown_and_json_include_score_model_and_limitations():
    observer = _observers()[0]
    engine = FakeEngine({"Alpha": FakeResult(80, 40, 1800, eclipse_type="total")})
    plan = EclipseEngine.plan_observations(engine, [observer], "2026-08-12")

    markdown = plan.to_markdown()
    assert "weather-agnostic heuristic" in markdown
    assert "Alpha" in markdown
    data = plan.to_dict()
    assert data["score_model"] == "weather_agnostic_weighted_heuristic_v1"
    assert data["counts"]["recommended"] == 1
    assert data["sites"][0]["local_result"]["eclipse_type"] == "total"


def test_observation_plan_accepts_custom_weights():
    observer = _observers()[0]
    engine = FakeEngine({"Alpha": FakeResult(60, 20, 1800)})
    plan = EclipseEngine.plan_observations(
        engine, [observer], "2026-08-12", weights=ObservationScoreWeights(1, 0, 0)
    )
    assert plan.recommended_sites[0].score == 60.0


def test_observation_plan_csv_contains_ranked_metrics_and_empty_sites(tmp_path):
    from eclipsekit import write_observation_plan_csv

    observers = _observers()[:2]
    engine = FakeEngine({
        "Alpha": FakeResult(80, 40, 1800, eclipse_type="total"),
        "Bravo": None,
    })
    plan = EclipseEngine.plan_observations(engine, observers, "2026-08-12")
    destination = write_observation_plan_csv(plan, tmp_path / "reports" / "plan.csv")

    rows = destination.read_text(encoding="utf-8-sig").splitlines()
    assert "rank,site_name,country" in rows[0]
    assert any(",Alpha,Spain," in row and ",recommended," in row for row in rows[1:])
    assert any(",Bravo,Spain," in row and ",no_eclipse," in row for row in rows[1:])


def test_weights_normalize_without_overflow_for_large_finite_values():
    weights = ObservationScoreWeights(1e308, 1e308, 1e308)
    assert weights.normalized() == pytest.approx({
        "obscuration": 1 / 3,
        "solar_altitude": 1 / 3,
        "partial_duration": 1 / 3,
    })


def test_plan_records_below_minimum_sites_separately_and_reports_count():
    engine = FakeEngine({"Alpha": FakeResult(90, -2, 1200)})
    plan = EclipseEngine.plan_observations(
        engine, _observers()[:1], "2026-08-12", minimum_sun_altitude_deg=5
    )
    assert not plan.recommended_sites
    assert len(plan.below_minimum_sites) == 1
    assert plan.to_dict()["counts"]["below_minimum_sun_altitude"] == 1
    assert "Below minimum Sun altitude: 1" in plan.to_markdown()


def test_plan_forwards_search_and_limb_options_and_accepts_generator():
    observers = _observers()[:1]
    engine = FakeEngine({"Alpha": FakeResult(70, 25, 900)})
    limb = object()
    plan = EclipseEngine.plan_observations(
        engine, (site for site in observers), "2026-08-12",
        search_window_hours=8, limb_model=limb,
    )
    assert len(plan.recommended_sites) == 1
    kwargs = engine.calls[0][2]
    assert kwargs["search_window_hours"] == 8.0
    assert kwargs["limb_model"] is limb
    assert kwargs["find_next_if_none"] is False


@pytest.mark.parametrize(
    "outcome",
    [
        FakeResult(float("nan"), 20, 100),
        FakeResult(101, 20, 100),
        FakeResult(50, float("inf"), 100),
        FakeResult(50, 91, 100),
        FakeResult(50, 20, -1),
        SimpleNamespace(obscuration_percent=50, sun_altitude_deg=20),
    ],
)
def test_invalid_local_result_becomes_structured_calculation_error(outcome):
    engine = FakeEngine({"Alpha": outcome})
    plan = EclipseEngine.plan_observations(engine, _observers()[:1], "2026-08-12")
    assert len(plan.error_sites) == 1
    assert plan.error_sites[0].message


def test_missing_partial_duration_is_a_zero_duration_component():
    engine = FakeEngine({"Alpha": FakeResult(50, 20, None)})
    plan = EclipseEngine.plan_observations(
        engine, _observers()[:1], "2026-08-12",
        weights=ObservationScoreWeights(0, 0, 1),
    )
    assert plan.recommended_sites[0].partial_duration_score == 0.0
    assert plan.recommended_sites[0].score == 0.0


def test_recommended_ties_are_deterministic_by_site_label():
    observers = [
        Observer(40, -4, name="Zulu", country="Spain"),
        Observer(41, -3, name="Alpha", country="Spain"),
    ]
    engine = FakeEngine({
        "Zulu": FakeResult(70, 30, 1200),
        "Alpha": FakeResult(70, 30, 1200),
    })
    plan = EclipseEngine.plan_observations(engine, observers, "2026-08-12")
    assert [site.observer.name for site in plan.recommended_sites] == ["Alpha", "Zulu"]


def test_plan_and_site_models_reject_inconsistent_status_rank_and_notes():
    from eclipsekit import ObservationPlan, ObservationSitePlan

    observer = _observers()[0]
    result = FakeResult(80, 30, 1200)
    with pytest.raises(ValueError, match="positive integer"):
        ObservationSitePlan(observer, "recommended", result, score=50, rank=0)
    with pytest.raises(ValueError, match="cannot include local_result"):
        ObservationSitePlan(observer, "no_eclipse", result)
    with pytest.raises(ValueError, match="calculation_error sites require"):
        ObservationSitePlan(observer, "calculation_error")
    with pytest.raises(ValueError, match="at least one site"):
        ObservationPlan(FakeTime(), (), ObservationScoreWeights(), 0, 45, 3600)

    site = ObservationSitePlan(observer, "recommended", result, score=50, rank=1)
    with pytest.raises(ValueError, match="contiguous ranks"):
        ObservationPlan(FakeTime(), (site, ObservationSitePlan(
            _observers()[1], "recommended", result, score=40, rank=3
        )), ObservationScoreWeights(), 0, 45, 3600)
    with pytest.raises(ValueError, match="non-empty strings"):
        ObservationPlan(FakeTime(), (site,), ObservationScoreWeights(), 0, 45, 3600, notes=("",))


def test_plan_json_export_is_unicode_strict_json(tmp_path):
    import json
    from eclipsekit import write_observation_plan_json

    observer = Observer(40, -4, name="León", country="España")
    engine = FakeEngine({"León": FakeResult(80, 40, 1800, eclipse_type="total")})
    plan = EclipseEngine.plan_observations(engine, [observer], "2026-08-12")
    destination = write_observation_plan_json(plan, tmp_path / "reports" / "plan.json")
    text = destination.read_text(encoding="utf-8")
    assert "León" in text
    assert json.loads(text)["counts"]["recommended"] == 1


def test_plan_json_export_rejects_non_plan_objects(tmp_path):
    from eclipsekit import write_observation_plan_json

    with pytest.raises(TypeError, match="to_dict"):
        write_observation_plan_json(object(), tmp_path / "plan.json")


def test_observation_models_accept_and_freeze_site_and_note_sequences():
    from eclipsekit import ObservationPlan, ObservationSitePlan

    site = ObservationSitePlan(
        _observers()[0], "recommended", FakeResult(75, 20, 600), score=75, rank=1
    )
    source_sites = [site]
    source_notes = ["Note"]
    plan = ObservationPlan(
        FakeTime(), source_sites, ObservationScoreWeights(), 0, 45, 3600,
        notes=source_notes,
    )
    source_sites.clear()
    source_notes.append("Later")
    assert len(plan.sites) == 1
    assert plan.notes == ("Note",)
