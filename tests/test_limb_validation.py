import pytest

from eclipsekit.limb import GriddedLunarLimbModel
from eclipsekit.limb_validation import (
    LunarLimbBenchmarkSample,
    load_lunar_limb_benchmark,
    render_lunar_limb_validation_markdown,
    run_lunar_limb_model_validation,
)


def test_lunar_limb_benchmark_sample_validates_fields():
    with pytest.raises(ValueError, match="latitude"):
        LunarLimbBenchmarkSample("bad", 91, 0, 0, 0)
    with pytest.raises(ValueError, match="uncertainty"):
        LunarLimbBenchmarkSample("bad", 0, 0, 0, 0, -1)


def test_load_lunar_limb_benchmark_and_optional_uncertainty(tmp_path):
    path = tmp_path / "benchmark.csv"
    path.write_text(
        "sample_id,selenographic_latitude_deg,selenographic_longitude_deg,limb_angle_deg,reference_altitude_m,reference_uncertainty_m\n"
        "a,0,0,45,10,2\n"
        "b,1,1,90,20,3\n",
        encoding="utf-8",
    )
    samples = load_lunar_limb_benchmark(path)
    assert len(samples) == 2
    assert samples[0].reference_uncertainty_m == 2


def test_lunar_limb_benchmark_rejects_duplicate_ids(tmp_path):
    path = tmp_path / "benchmark.csv"
    path.write_text(
        "sample_id,selenographic_latitude_deg,selenographic_longitude_deg,limb_angle_deg,reference_altitude_m\n"
        "same,0,0,45,10\n"
        "same,1,1,90,20\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unique"):
        load_lunar_limb_benchmark(path)


def test_lunar_limb_benchmark_rejects_non_finite_values(tmp_path):
    path = tmp_path / "benchmark.csv"
    path.write_text(
        "selenographic_latitude_deg,selenographic_longitude_deg,limb_angle_deg,reference_altitude_m\n"
        "0,0,nan,10\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="finite"):
        load_lunar_limb_benchmark(path)


def make_dem():
    return GriddedLunarLimbModel(
        [0, 1], [0, 1], [[0, 10], [20, 30]],
        uncertainties_m=[[2, 2], [2, 2]],
        name="Benchmark DEM", source="test fixture DEM", vertical_datum="test radial datum",
    )


def test_lunar_limb_validation_reports_metrics_and_spherical_baseline():
    samples = [
        LunarLimbBenchmarkSample("center", 0.5, 0.5, 45, 14, 3),
    ]
    report = run_lunar_limb_model_validation(
        make_dem(), samples, benchmark_source="independent test fixture", benchmark_vertical_datum="test radial datum"
    )
    assert report["status"] == "UNASSESSED"
    assert report["metrics"]["bias_m"] == pytest.approx(1.0)
    assert report["metrics"]["mae_m"] == pytest.approx(1.0)
    assert report["metrics"]["rmse_m"] == pytest.approx(1.0)
    assert report["uncertainty_metrics"]["samples_with_combined_uncertainty"] == 1
    assert report["spherical_zero_relief_baseline"]["metrics"]["mae_m"] == pytest.approx(14.0)
    threshold_report = run_lunar_limb_model_validation(
        make_dem(), samples, benchmark_source="independent test fixture", acceptance_rmse_m=2.0,
    )
    assert threshold_report["status"] == "PASS"
    failing_report = run_lunar_limb_model_validation(
        make_dem(), samples, benchmark_source="independent test fixture", acceptance_rmse_m=0.5,
    )
    assert failing_report["status"] == "FAIL"


def test_lunar_limb_validation_records_out_of_coverage_as_failed_sample():
    samples = [LunarLimbBenchmarkSample("outside", 10, 10, 0, 0)]
    report = run_lunar_limb_model_validation(
        make_dem(), samples, benchmark_source="test benchmark"
    )
    assert report["status"] == "ERROR"
    assert report["error_count"] == 1
    assert report["errors"][0]["sample_id"] == "outside"


def test_lunar_limb_markdown_renders_metrics_and_provenance():
    report = run_lunar_limb_model_validation(
        make_dem(), [LunarLimbBenchmarkSample("center", 0.5, 0.5, 45, 15)],
        benchmark_source="reference publication table", benchmark_vertical_datum="test radial datum",
    )
    markdown = render_lunar_limb_validation_markdown(report)
    assert "reference publication table" in markdown
    assert "radial" in markdown
    assert "RMSE (m)" in markdown


def test_lunar_limb_validation_rejects_mismatched_vertical_datums():
    with pytest.raises(ValueError, match="vertical datums do not match"):
        run_lunar_limb_model_validation(
            make_dem(),
            [LunarLimbBenchmarkSample("center", 0.5, 0.5, 45, 15)],
            benchmark_source="independent reference",
            benchmark_vertical_datum="different radial datum",
        )


def _benchmark_csv(path, *, latitude=0.5, longitude=0.5, angle=45.0, altitude=0.0):
    path.write_text(
        "sample_id,selenographic_latitude_deg,selenographic_longitude_deg,limb_angle_deg,reference_altitude_m\n"
        f"sample-1,{latitude},{longitude},{angle},{altitude}\n",
        encoding="utf-8",
    )
    return path


def test_lunar_limb_cli_runs_spherical_benchmark_and_writes_reports(tmp_path, capsys):
    from eclipsekit.limb_validation import main

    benchmark = _benchmark_csv(tmp_path / "benchmark.csv")
    json_path = tmp_path / "nested" / "report.json"
    markdown_path = tmp_path / "nested" / "report.md"
    status = main([
        "--benchmark-csv", str(benchmark), "--benchmark-source", "independent fixture",
        "--model", "spherical", "--max-rmse-m", "1",
        "--json-out", str(json_path), "--markdown-out", str(markdown_path),
    ])

    assert status == 0
    assert json_path.is_file() and markdown_path.is_file()
    import json
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["benchmark"]["source"] == "independent fixture"
    assert "Spherical zero-relief baseline" not in capsys.readouterr().out


def test_lunar_limb_cli_runs_angular_profile_model(tmp_path):
    from eclipsekit.limb_validation import main

    benchmark = _benchmark_csv(tmp_path / "benchmark.csv", angle=45.0, altitude=15.0)
    profile = tmp_path / "profile.csv"
    profile.write_text(
        "limb_angle_deg,altitude_m\n0,0\n90,30\n180,60\n270,90\n",
        encoding="utf-8",
    )
    status = main([
        "--benchmark-csv", str(benchmark), "--benchmark-source", "profile fixture",
        "--model", "angular-profile", "--model-file", str(profile),
        "--max-rmse-m", "1", "--json-out", str(tmp_path / "out.json"),
        "--markdown-out", str(tmp_path / "out.md"),
    ])
    assert status == 0


def test_lunar_limb_cli_runs_dem_model_with_matching_vertical_datum(tmp_path):
    from eclipsekit.limb_validation import main

    benchmark = _benchmark_csv(tmp_path / "benchmark.csv", altitude=15.0)
    dem = tmp_path / "dem.csv"
    dem.write_text(
        "latitude_deg,longitude_deg,altitude_m\n0,0,0\n0,1,10\n1,0,20\n1,1,30\n",
        encoding="utf-8",
    )
    status = main([
        "--benchmark-csv", str(benchmark), "--benchmark-source", "DEM control",
        "--benchmark-vertical-datum", "radial datum", "--model", "dem",
        "--model-file", str(dem), "--vertical-datum", "radial datum",
        "--resolution-m", "100", "--max-rmse-m", "1",
        "--json-out", str(tmp_path / "out.json"),
        "--markdown-out", str(tmp_path / "out.md"),
    ])
    assert status == 0


def test_lunar_limb_cli_uses_neural_factory(monkeypatch, tmp_path):
    from eclipsekit import limb_validation
    from eclipsekit.limb import SphericalLunarLimbModel

    benchmark = _benchmark_csv(tmp_path / "benchmark.csv")
    checkpoint = tmp_path / "fake.pt"
    checkpoint.write_bytes(b"fake")
    captured = {}

    def factory(path, *, device, name, source):
        captured.update(path=path, device=device, name=name, source=source)
        return SphericalLunarLimbModel(name=name)

    monkeypatch.setattr(limb_validation.NeuralLimbModelFactory, "from_checkpoint", factory)
    status = limb_validation.main([
        "--benchmark-csv", str(benchmark), "--benchmark-source", "neural fixture",
        "--model", "neural", "--model-file", str(checkpoint), "--device", "cpu",
        "--model-name", "test neural", "--model-source", "checkpoint provenance",
        "--json-out", str(tmp_path / "out.json"),
        "--markdown-out", str(tmp_path / "out.md"),
    ])
    assert status == 0
    assert captured == {
        "path": str(checkpoint), "device": "cpu", "name": "test neural",
        "source": "checkpoint provenance",
    }


def test_neural_limb_factory_attaches_cli_provenance(monkeypatch, tmp_path):
    from eclipsekit import limb_validation
    from eclipsekit.limb import LunarLimbCorrector, LunarLimbMetadata

    checkpoint = tmp_path / "checkpoint.pt"
    checkpoint.write_bytes(b"fake")
    corrector = LunarLimbCorrector(object(), LunarLimbMetadata(0.0, 1.0))
    monkeypatch.setattr(
        LunarLimbCorrector, "from_checkpoint", classmethod(lambda cls, path, device: corrector)
    )
    model = limb_validation.NeuralLimbModelFactory.from_checkpoint(
        checkpoint, device="cpu", name="named neural", source="published checkpoint",
    )
    assert model.metadata.name == "named neural"
    assert model.metadata.source == "published checkpoint"


def test_lunar_limb_cli_reports_model_load_errors(tmp_path):
    from eclipsekit.limb_validation import main

    benchmark = _benchmark_csv(tmp_path / "benchmark.csv")
    with pytest.raises(SystemExit) as exc:
        main([
            "--benchmark-csv", str(benchmark), "--benchmark-source", "fixture",
            "--model", "dem", "--model-file", str(tmp_path / "missing.csv"),
            "--json-out", str(tmp_path / "out.json"),
            "--markdown-out", str(tmp_path / "out.md"),
        ])
    assert exc.value.code == 2


@pytest.mark.parametrize(
    "extra_args, message",
    [
        (("--model", "dem"), "--model-file is required"),
        (("--model", "spherical", "--model-file", "x.csv"), "do not apply to the spherical baseline"),
        (("--model", "angular-profile", "--model-file", "x.csv", "--periodic-longitude"), "apply only to a gridded DEM"),
        (("--model", "dem", "--model-file", "x.csv", "--non-periodic"), "apply only to an angular profile"),
        (("--model", "spherical", "--max-rmse-m", "-1"), "finite and non-negative"),
    ],
)
def test_lunar_limb_cli_rejects_incompatible_options(tmp_path, extra_args, message):
    from eclipsekit.limb_validation import main

    benchmark = _benchmark_csv(tmp_path / "benchmark.csv")
    base = ["--benchmark-csv", str(benchmark), "--benchmark-source", "fixture"]
    with pytest.raises(SystemExit) as exc:
        main([*base, *extra_args])
    assert exc.value.code == 2
