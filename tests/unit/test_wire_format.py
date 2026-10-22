from smart_city_security.iot_sim.traffic_generator import TrafficGenerator
from smart_city_security.pqc.classical_backend import ClassicalBackend
from smart_city_security.pqc.secure_channel import SecureChannel
from smart_city_security.pqc.wire_format import deserialize, serialize


def test_wire_format_round_trip():
    channel = SecureChannel(ClassicalBackend())
    message = channel.protect(TrafficGenerator(1).generate(1)[0])
    assert deserialize(serialize(message)).session_id == message.session_id
