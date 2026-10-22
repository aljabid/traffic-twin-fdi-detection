import pytest

from smart_city_security.ml_detection.dataset_manifest import (
    DatasetManifest,
    DatasetPartition,
)


def test_dataset_manifest_enforces_temporal_separation(tmp_path):
    manifest = DatasetManifest(
        "traffic",
        "1",
        "abc",
        "features-v1",
        "operator-confirmed",
        (
            DatasetPartition("train", ("i1",), 0, 10, 100),
            DatasetPartition("validation", ("i2",), 11, 20, 20),
            DatasetPartition("test", ("i3",), 21, 30, 20),
        ),
    )
    assert manifest.write(tmp_path / "manifest.json").is_file()


def test_dataset_manifest_rejects_temporal_leakage():
    manifest = DatasetManifest(
        "traffic",
        "1",
        "abc",
        "features-v1",
        "policy",
        (
            DatasetPartition("train", ("i1",), 0, 10, 10),
            DatasetPartition("validation", ("i2",), 10, 20, 10),
            DatasetPartition("test", ("i3",), 21, 30, 10),
        ),
    )
    with pytest.raises(ValueError, match="chronologically"):
        manifest.validate_leakage()
