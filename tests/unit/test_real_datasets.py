from smart_city_security.evaluation.real_datasets import (
    ngsim_rows_to_telemetry,
    occupancy_from_headway,
    occupancy_from_speed,
    pneuma_lines_to_telemetry,
    sumo_fcd_rows_to_telemetry,
)


def test_occupancy_proxies_are_bounded_and_monotone():
    assert occupancy_from_headway(0.0) == 0.05
    assert occupancy_from_headway(5.0) > occupancy_from_headway(30.0)
    assert 0.0 <= occupancy_from_headway(200.0) <= 1.0
    assert occupancy_from_speed(0.0) == 1.0
    assert occupancy_from_speed(60.0) == 0.0


def _ngsim_row(**over):
    row = {
        "vehicle_id": "5", "frame_id": "10", "global_time": "1163000000",
        "local_y": "300.0", "v_vel": "40.0", "v_class": "2", "space_headway": "60.0",
        "v_length": "15", "int_id": "3", "section_id": "1", "location": "lankershim",
    }
    row.update(over)
    return row


def test_ngsim_transform_maps_schema():
    rows = [_ngsim_row(frame_id="10"), _ngsim_row(frame_id="20"), _ngsim_row(frame_id="15")]
    out = list(ngsim_rows_to_telemetry(rows, downsample=10))
    assert len(out) == 2
    t = out[0]
    assert t.device_id == "ngsim-lankershim-5"
    assert t.device_type == "vehicle"
    assert 0.0 < t.speed < 89.0
    assert 0.0 <= t.occupancy <= 1.0
    assert t.intersection_id == "lankershim-3"
    assert t.sequence_number == 1


def test_ngsim_filters_by_location():
    rows = [_ngsim_row(location="us-101"), _ngsim_row(location="lankershim")]
    out = list(ngsim_rows_to_telemetry(rows, downsample=10))
    assert len(out) == 1


def test_pneuma_transform():
    line = "1; Bus; 100; 20; " + "; ".join(
        f"37.98{i:02d}; 23.72{i:02d}; {10 + i}; 0; 0; {i}.0" for i in range(30)
    )
    out = list(pneuma_lines_to_telemetry([line], downsample=10))
    assert out
    assert out[0].device_id == "pneuma-1"
    assert out[0].device_type == "bus"
    assert all(0.0 <= t.occupancy <= 1.0 for t in out)


def test_sumo_transform():
    rows = [
        {"time": "1.0", "id": "v1", "x": "10", "y": "250.5", "speed": "12.0",
         "type": "vehicle", "edge": "-e1_0", "occupancy": "0.3", "signal_state": "green"},
    ]
    out = list(sumo_fcd_rows_to_telemetry(rows))
    assert out[0].device_id == "sumo-v1"
    assert out[0].signal_state == "green"
    assert out[0].speed == round(12.0 * 3.6, 4)
