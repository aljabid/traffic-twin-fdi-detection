import base64
import time
from dataclasses import replace

import yaml

from smart_city_security.config import _merge, load_config
from smart_city_security.integration.live_service import LiveIngestionDaemon
from smart_city_security.integration.provision_device import provision
from smart_city_security.iot_sim import TrafficGenerator
from smart_city_security.pqc import DeviceKey, PreSharedKeyChannel


def test_provisioned_device_round_trips_through_daemon(tmp_path):
    written = provision("wokwi-esp32-01", tmp_path)
    fragment = yaml.safe_load(written["config"].read_text())
    entry = fragment["security"]["preshared_keys"][0]
    aes_key = base64.b64decode(entry["aes_key_b64"])
    private_pem = written["private_key"].read_bytes()

    config = _merge(load_config("configs/field_trial.yaml"), fragment)
    config["network"]["mode"] = "simulated"
    daemon = LiveIngestionDaemon(config)
    daemon.start()
    try:
        device_channel = PreSharedKeyChannel(
            [DeviceKey("wokwi-esp32-01", aes_key, entry["public_key_pem"].encode())]
        )
        telemetry = replace(
            TrafficGenerator(1, seed=5).generate(1)[0],
            device_id="wokwi-esp32-01",
            sequence_number=1,
        )
        message = device_channel.protect(
            telemetry, aes_key, private_pem, timestamp=int(time.time())
        )
        daemon.mqtt_client.publish(config["network"]["topic"], message.to_bytes())

        counters = daemon.metrics.snapshot()["counters"]
        assert counters["telemetry_received_total"] == 1
        assert counters.get("telemetry_undecodable_total", 0) == 0
        assert any(e.event == "message_accepted" for e in daemon.audit.events)
    finally:
        daemon.stop()


def test_provision_cli_writes_all_artifacts(tmp_path, capsys):
    from smart_city_security.integration.provision_device import main

    rc = main(
        [
            "--device-id",
            "esp-77",
            "--output-dir",
            str(tmp_path / "keys"),
            "--config-out",
            str(tmp_path / "run.local.yaml"),
            "--extends",
            "field_trial.yaml",
        ]
    )
    assert rc == 0
    assert (tmp_path / "keys" / "esp-77.private.pem").exists()
    assert (tmp_path / "keys" / "esp-77.h").exists()
    assert (tmp_path / "run.local.yaml").exists()
    assert "device_key.h" in capsys.readouterr().out


def test_provision_writes_runnable_config(tmp_path):
    config_out = tmp_path / "secure.local.yaml"
    written = provision(
        "wokwi-esp32-01", tmp_path, config_out=config_out, extends="field_trial.yaml"
    )
    assert "runnable_config" in written
    text = config_out.read_text()
    parsed = yaml.safe_load(text)
    assert parsed["extends"] == "field_trial.yaml"
    assert parsed["security"]["backend"] == "preshared"
    assert parsed["security"]["preshared_keys"][0]["device_id"] == "wokwi-esp32-01"
    assert "PRIVATE KEY" not in text


def test_daemon_rejects_message_from_unprovisioned_device(tmp_path):
    written = provision("wokwi-esp32-01", tmp_path)
    fragment = yaml.safe_load(written["config"].read_text())
    entry = fragment["security"]["preshared_keys"][0]
    aes_key = base64.b64decode(entry["aes_key_b64"])
    private_pem = written["private_key"].read_bytes()

    config = _merge(load_config("configs/field_trial.yaml"), fragment)
    config["network"]["mode"] = "simulated"
    daemon = LiveIngestionDaemon(config)
    daemon.start()
    try:
        device_channel = PreSharedKeyChannel(
            [DeviceKey("rogue", aes_key, entry["public_key_pem"].encode())]
        )
        telemetry = replace(
            TrafficGenerator(1, seed=5).generate(1)[0],
            device_id="rogue",
            sequence_number=1,
        )
        message = device_channel.protect(
            telemetry, aes_key, private_pem, timestamp=int(time.time())
        )
        daemon.mqtt_client.publish(config["network"]["topic"], message.to_bytes())

        counters = daemon.metrics.snapshot()["counters"]
        assert counters.get("telemetry_received_total", 0) == 0
        assert counters["telemetry_undecodable_total"] == 1
    finally:
        daemon.stop()
