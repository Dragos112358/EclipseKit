from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np
import pytest

from eclipsekit.limb import LunarLimbQuery
from eclipsekit.lunar_dem_mosaic import (
    LunarDEMCoverage,
    LunarDEMOutOfCoverageError,
    LunarDEMMosaicModel,
)


@dataclass
class FakeProductInfo:
    product_id: str = "fake"
    format: str = "synthetic"
    coordinate_system_name: str = "MOON_PA_DE440"
    vertical_datum: str = "sphere-1737400"
    reference_radius_m: float = 1_737_400.0
    south_latitude_deg: float = -10.0
    north_latitude_deg: float = 10.0
    west_longitude_deg: float = -20.0
    east_longitude_deg: float = 20.0
    resolution_m: float = 100.0

    def to_dict(self):
        return {
            "product_id": self.product_id,
            "format": self.format,
            "coordinate_system_name": self.coordinate_system_name,
            "vertical_datum": self.vertical_datum,
            "reference_radius_m": self.reference_radius_m,
        }


class FakeDEM:
    def __init__(self, value, info=None, *, failure=None):
        self.value = value
        self.product_info = info or FakeProductInfo()
        self.metadata = SimpleNamespace(
            name=self.product_info.product_id,
            vertical_datum=self.product_info.vertical_datum,
            resolution_m=self.product_info.resolution_m,
            model_type="pds3_dem",
            source=self.product_info.product_id,
        )
        self.failure = failure
        self.calls = []
        self.closed = False

    def predict_altitude_m(self, latitude_deg, longitude_deg):
        self.calls.append((latitude_deg, longitude_deg))
        if self.failure is not None:
            raise self.failure
        return self.value

    def close(self):
        self.closed = True


def test_priority_routes_to_first_declared_source_covering_query():
    north = FakeDEM(100.0, FakeProductInfo(product_id="north", south_latitude_deg=0, north_latitude_deg=20))
    south = FakeDEM(200.0, FakeProductInfo(product_id="south", south_latitude_deg=-20, north_latitude_deg=0))
    model = LunarDEMMosaicModel([north, south])

    assert model.predict_altitude_m(5.0, 0.0) == 100.0
    assert model.predict_altitude_m(-5.0, 0.0) == 200.0
    assert north.calls == [(5.0, 0.0)]
    assert south.calls == [(-5.0, 0.0)]


def test_priority_keeps_order_when_coverages_overlap():
    first = FakeDEM(10.0, FakeProductInfo(product_id="first"))
    second = FakeDEM(20.0, FakeProductInfo(product_id="second"))
    model = LunarDEMMosaicModel([first, second], strategy="priority")

    assert model.predict_altitude_m(0.0, 0.0) == 10.0
    assert len(first.calls) == 1
    assert second.calls == []


def test_finest_strategy_selects_smallest_resolution_with_stable_tie_break():
    coarse = FakeDEM(10.0, FakeProductInfo(product_id="coarse", resolution_m=120.0))
    fine_a = FakeDEM(20.0, FakeProductInfo(product_id="fine-a", resolution_m=30.0))
    fine_b = FakeDEM(30.0, FakeProductInfo(product_id="fine-b", resolution_m=30.0))
    model = LunarDEMMosaicModel([coarse, fine_a, fine_b], strategy="finest")

    assert model.predict_altitude_m(1.0, 1.0) == 20.0
    assert coarse.calls == []
    assert len(fine_a.calls) == 1
    assert fine_b.calls == []


def test_mean_strategy_averages_all_covering_sources_and_reports_provenance():
    first = FakeDEM(100.0, FakeProductInfo(product_id="first"))
    second = FakeDEM(200.0, FakeProductInfo(product_id="second"))
    model = LunarDEMMosaicModel([first, second], strategy="mean")

    prediction = model.predict(LunarLimbQuery(0.0, 0.0, 0.0))
    assert prediction.altitude_m == 150.0
    assert prediction.source == "first; second"
    assert prediction.uncertainty_m is None
    assert len(first.calls) == len(second.calls) == 1


def test_no_coverage_raises_typed_error_without_sampling_any_source():
    source = FakeDEM(1.0)
    model = LunarDEMMosaicModel([source])

    with pytest.raises(LunarDEMOutOfCoverageError, match="No lunar DEM source"):
        model.predict_altitude_m(30.0, 0.0)
    assert source.calls == []


def test_longitude_coverage_wraps_across_antimeridian():
    source = FakeDEM(
        42.0,
        FakeProductInfo(product_id="dateline", west_longitude_deg=170.0, east_longitude_deg=190.0),
    )
    model = LunarDEMMosaicModel([source])

    assert model.predict_altitude_m(0.0, -175.0) == 42.0
    assert model.predict_altitude_m(0.0, 185.0) == 42.0
    with pytest.raises(LunarDEMOutOfCoverageError):
        model.predict_altitude_m(0.0, 0.0)


def test_global_longitude_coverage_accepts_any_finite_longitude():
    source = FakeDEM(
        5.0,
        FakeProductInfo(product_id="global", west_longitude_deg=0.0, east_longitude_deg=360.0),
    )
    model = LunarDEMMosaicModel([source])

    assert model.predict_altitude_m(0.0, -999.0) == 5.0


def test_metadata_frame_datum_and_radius_must_match():
    reference = FakeDEM(1.0)
    bad_frame = FakeDEM(2.0, FakeProductInfo(product_id="bad-frame", coordinate_system_name="DE421_ME"))
    with pytest.raises(ValueError, match="coordinate system"):
        LunarDEMMosaicModel([reference, bad_frame])

    bad_datum = FakeDEM(2.0, FakeProductInfo(product_id="bad-datum", vertical_datum="other"))
    with pytest.raises(ValueError, match="vertical datum"):
        LunarDEMMosaicModel([reference, bad_datum])

    bad_radius = FakeDEM(2.0, FakeProductInfo(product_id="bad-radius", reference_radius_m=1_737_401.0))
    with pytest.raises(ValueError, match="reference radius"):
        LunarDEMMosaicModel([reference, bad_radius])


def test_finest_strategy_requires_resolution_for_every_source():
    info = FakeProductInfo(product_id="unknown-resolution", resolution_m=None)
    source = FakeDEM(1.0, info)
    with pytest.raises(ValueError, match="requires a positive resolution"):
        LunarDEMMosaicModel([source], strategy="finest")


def test_transformed_or_generic_source_requires_explicit_coverage_override():
    info = FakeProductInfo(product_id="virtual")
    info.south_latitude_deg = None
    info.north_latitude_deg = None
    source = FakeDEM(3.0, info)
    with pytest.raises(ValueError, match="explicit coverage override"):
        LunarDEMMosaicModel([source])

    model = LunarDEMMosaicModel(
        [source],
        coverage_overrides=[LunarDEMCoverage(-5.0, 5.0, 10.0, 30.0)],
    )
    assert model.predict_altitude_m(0.0, 20.0) == 3.0
    with pytest.raises(LunarDEMOutOfCoverageError):
        model.predict_altitude_m(0.0, 0.0)


def test_invalid_coverage_and_query_values_are_rejected():
    with pytest.raises(ValueError, match="latitude bounds"):
        LunarDEMCoverage(10.0, -10.0, 0.0, 20.0)
    with pytest.raises(ValueError, match="longitude span"):
        LunarDEMCoverage(-10.0, 10.0, 0.0, 0.0)
    with pytest.raises(TypeError, match="numeric value"):
        LunarDEMCoverage(False, 10.0, 0.0, 20.0)

    model = LunarDEMMosaicModel([FakeDEM(1.0)])
    with pytest.raises(TypeError, match="numeric value"):
        model.predict_altitude_m(True, 0.0)
    with pytest.raises(ValueError, match=r"within \[-90, 90\]"):
        model.predict_altitude_m(91.0, 0.0)
    with pytest.raises(ValueError, match="finite"):
        model.predict_altitude_m(0.0, np.inf)


def test_source_error_inside_coverage_is_not_hidden_by_fallback():
    primary = FakeDEM(0.0, FakeProductInfo(product_id="primary"), failure=ValueError("NoData cell"))
    fallback = FakeDEM(10.0, FakeProductInfo(product_id="fallback"))
    model = LunarDEMMosaicModel([primary, fallback], strategy="priority")

    with pytest.raises(RuntimeError, match="did not silently fall back") as error:
        model.predict_altitude_m(0.0, 0.0)
    assert isinstance(error.value.__cause__, ValueError)
    assert fallback.calls == []


def test_predict_many_broadcasts_and_preserves_shape():
    source = FakeDEM(12.5)
    model = LunarDEMMosaicModel([source])

    result = model.predict_many(np.array([[0.0], [1.0]]), np.array([0.0, 1.0, 2.0]))
    assert result.shape == (2, 3)
    assert np.all(result == 12.5)


def test_product_metadata_contains_common_reference_and_coverage_components():
    source = FakeDEM(7.0, FakeProductInfo(product_id="granule-a"))
    model = LunarDEMMosaicModel([source], product_id="regional-mosaic")
    info = model.product_info.to_dict()

    assert info["format"] == "virtual-mosaic"
    assert info["product_id"] == "regional-mosaic"
    assert info["coordinate_system_name"] == "MOON_PA_DE440"
    assert info["vertical_datum"] == "sphere-1737400"
    assert info["reference_radius_m"] == 1_737_400.0
    assert info["sources"][0]["name"] == "granule-a"
    assert info["sources"][0]["coverage"]["north_latitude_deg"] == 10.0


def test_source_lifecycle_is_not_owned_by_default_and_can_be_transferred():
    source = FakeDEM(1.0)
    model = LunarDEMMosaicModel([source])
    model.close()
    assert not source.closed
    with pytest.raises(RuntimeError, match="is closed"):
        model.predict_altitude_m(0.0, 0.0)

    owned_source = FakeDEM(2.0)
    with LunarDEMMosaicModel([owned_source], close_sources=True) as owned:
        assert owned.predict_altitude_m(0.0, 0.0) == 2.0
    assert owned_source.closed


def test_invalid_constructor_contracts_are_rejected():
    with pytest.raises(ValueError, match="at least one"):
        LunarDEMMosaicModel([])
    source = FakeDEM(1.0)
    with pytest.raises(ValueError, match="strategy"):
        LunarDEMMosaicModel([source], strategy="blend")
    with pytest.raises(ValueError, match="source_names"):
        LunarDEMMosaicModel([source], source_names=["a", "b"])
    with pytest.raises(ValueError, match="unique"):
        LunarDEMMosaicModel([FakeDEM(1), FakeDEM(2)], source_names=["same", " SAME "])
    with pytest.raises(ValueError, match="same model more than once"):
        LunarDEMMosaicModel([source, source])
