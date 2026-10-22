import csv
import zipfile
from io import StringIO

from smart_city_security.digital_twin.external_dataset import (
    load_uci_metro_zip,
    rolling_volume_validation,
)


def test_external_dataset_adapter_and_metrics(tmp_path):
    content = StringIO()
    writer = csv.DictWriter(
        content, fieldnames=["date_time", "traffic_volume"]
    )
    writer.writeheader()
    for hour in range(48):
        writer.writerow(
            {
                "date_time": f"2020-01-{hour // 24 + 1:02d} {hour % 24:02d}:00:00",
                "traffic_volume": 100 + hour,
            }
        )
    archive = tmp_path / "dataset.zip"
    with zipfile.ZipFile(archive, "w") as target:
        target.writestr("traffic.csv", content.getvalue())
    observations = load_uci_metro_zip(archive)
    report = rolling_volume_validation(observations)
    assert report["observations"] == 48
    assert report["rmse"] > 0
