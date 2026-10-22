import pytest

from smart_city_security.network.mqtt_client import MQTTClient, MQTTTLSConfig


def test_mqtt_client_uses_mqtt5_and_validates_qos():
    client = MQTTClient(client_id="test")
    assert client.default_qos == 1
    with pytest.raises(ValueError, match="QoS"):
        MQTTClient(default_qos=3)


def test_tls_configuration_rejects_missing_files():
    with pytest.raises(ValueError, match="does not exist"):
        MQTTTLSConfig("missing-ca", "missing-cert", "missing-key").validate()
