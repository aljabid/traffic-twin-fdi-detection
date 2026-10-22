import io
import json
import zipfile

from smart_city_security.evaluation.v2x_datasets import (
    RawMessage,
    read_tampa_bsm,
    read_veremi,
    to_telemetry,
)


def _bsm(message_id, sender, time, x, y, vx=10.0):
    return json.dumps({"type": 3, "rcvTime": time, "sendTime": time, "sender": sender, "senderPseudo": 1,
                       "messageID": message_id, "pos": [x, y, 0.0], "spd": [vx, 0.0, 0.0]})


def _veremi_zip(path):
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("run/traceJSON-7-5-A0-100-1.json",
                   "\n".join([json.dumps({"type": 2, "rcvTime": 100.0}), _bsm(1, 9, 100.0, 0, 0), _bsm(2, 9, 101.0, 500, 0)]))
        z.writestr("run/traceJSON-9-8-A1-100-1.json", "\n".join([_bsm(3, 7, 100.5, 20, 0), _bsm(4, 7, 2000.0, 30, 0)]))
        z.writestr("run/traceJSON-11-10-A0-100-1.json", _bsm(1, 9, 100.0, 0, 0))
        z.writestr("run/traceGroundTruthJSON-1.json", json.dumps({"type": 4, "messageID": 1}))
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("ConstPos/VeReMi_hour.zip", inner.getvalue())


def test_veremi_messages_are_unique_labelled_by_sender_and_windowed(tmp_path):
    _veremi_zip(tmp_path / "attack.zip")
    messages = read_veremi(tmp_path / "attack.zip", duration_s=900.0)
    assert len(messages) == 3
    assert {m.sender: m.attack for m in messages} == {"9": True, "7": False}
    assert abs(next(m for m in messages if m.sender == "7").speed_kmh - 36.0) < 1e-9
    assert len(read_veremi(tmp_path / "attack.zip", duration_s=None)) == 4


def test_mapping_uses_path_length_and_nearest_vehicle():
    raw = [RawMessage("a", 0.0, 0.0, 0.0, 36.0), RawMessage("b", 0.2, 18.0, 0.0, 36.0),
           RawMessage("a", 1.0, 3.0, 4.0, 36.0, attack=True), RawMessage("c", 50.0, 0.0, 0.0, 36.0)]
    stream, attacked = to_telemetry(raw, prefix="t")
    by_id = {m.message_id: m for m in stream}
    assert by_id["t-a-000002"].position == 5.0
    assert attacked == {"t-a-000002"}
    assert by_id["t-b-000001"].occupancy == 0.5
    assert by_id["t-c-000001"].occupancy == 0.05
    assert [m.timestamp for m in stream] == sorted(m.timestamp for m in stream)


def test_tampa_duplicates_dropped_and_ids_merged(tmp_path):
    header = "metadata_recordgeneratedat,metadata_rsuid,coredata_id,coredata_secmark,coredata_lat,coredata_long,coredata_speed"
    rows = [
        "2021-03-19T00:00:01.000,rsu1,111,1000,279000000.0,-824000000.0,500.0",
        "2021-03-19T00:00:01.050,rsu2,222,1000,279000000.0,-824000000.0,500.0",
        "2021-03-19T00:00:02.000,rsu2,222,2000,279000900.0,-824000000.0,500.0",
        "2021-03-19T00:00:03.000,rsu1,333,3000,279500000.0,-824000000.0,0.0",
    ]
    path = tmp_path / "bsm.csv"
    path.write_text("\n".join([header, *rows]), encoding="utf-8")
    messages = read_tampa_bsm(path)
    assert len(messages) == 3
    assert len({m.sender for m in messages}) == 2
    assert abs(messages[0].speed_kmh - 36.0) < 1e-9
    assert abs(messages[1].y - messages[0].y - 10.0) < 0.2
