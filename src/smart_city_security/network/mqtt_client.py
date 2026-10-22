from __future__ import annotations

import ssl
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

mqtt: ModuleType | None
try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None


class MQTTUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MQTTTLSConfig:
    ca_file: str
    certificate_file: str
    private_key_file: str
    minimum_version: ssl.TLSVersion = ssl.TLSVersion.TLSv1_3

    def validate(self) -> None:
        for value in (
            self.ca_file,
            self.certificate_file,
            self.private_key_file,
        ):
            if not Path(value).is_file():
                raise ValueError(f"MQTT TLS file does not exist: {value}")


class MQTTClient:

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1883,
        *,
        client_id: str = "",
        tls: MQTTTLSConfig | None = None,
        keepalive: int = 60,
        session_expiry_seconds: int = 300,
        default_qos: int = 1,
    ):
        if mqtt is None:
            raise MQTTUnavailableError("Install paho-mqtt to use real MQTT transport")
        if default_qos not in {0, 1, 2}:
            raise ValueError("MQTT QoS must be 0, 1, or 2")
        self.host = host
        self.port = port
        self.keepalive = keepalive
        self.session_expiry_seconds = session_expiry_seconds
        self.default_qos = default_qos
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv5,
        )
        if tls:
            tls.validate()
            context = ssl.create_default_context(cafile=tls.ca_file)
            context.minimum_version = tls.minimum_version
            context.load_cert_chain(
                tls.certificate_file, tls.private_key_file
            )
            self.client.tls_set_context(context)

    def set_last_will(
        self, topic: str, payload: bytes, *, qos: int = 1, retain: bool = False
    ) -> None:
        self.client.will_set(topic, payload, qos=qos, retain=retain)

    def connect(self) -> None:
        assert mqtt is not None
        properties = mqtt.Properties(mqtt.PacketTypes.CONNECT)
        properties.SessionExpiryInterval = self.session_expiry_seconds
        self.client.connect(
            self.host,
            self.port,
            keepalive=self.keepalive,
            clean_start=mqtt.MQTT_CLEAN_START_FIRST_ONLY,
            properties=properties,
        )
        self.client.loop_start()

    def publish(
        self,
        topic: str,
        payload: bytes,
        *,
        qos: int | None = None,
        retain: bool = False,
        expiry_seconds: int = 30,
    ) -> None:
        assert mqtt is not None
        properties = mqtt.Properties(mqtt.PacketTypes.PUBLISH)
        properties.MessageExpiryInterval = expiry_seconds
        result = self.client.publish(
            topic,
            payload,
            qos=self.default_qos if qos is None else qos,
            retain=retain,
            properties=properties,
        )
        result.wait_for_publish()
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT publish failed with code {result.rc}")

    def subscribe(
        self,
        topic: str,
        callback: Callable[[bytes], None],
        *,
        qos: int | None = None,
    ) -> None:
        def on_message(_client: object, _userdata: object, message: Any) -> None:
            callback(bytes(message.payload))

        self.client.on_message = on_message
        self.client.subscribe(
            topic, qos=self.default_qos if qos is None else qos
        )

    def close(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()


class InMemoryMQTTClient:
    def __init__(self) -> None:
        self._subscriptions: dict[str, list[Callable[[bytes], None]]] = {}
        self._lock = threading.Lock()

    def connect(self) -> None:
        return None

    def subscribe(
        self, topic: str, callback: Callable[[bytes], None], **_kwargs: object
    ) -> None:
        with self._lock:
            self._subscriptions.setdefault(topic, []).append(callback)

    def publish(self, topic: str, payload: bytes, **_kwargs: object) -> None:
        with self._lock:
            callbacks = list(self._subscriptions.get(topic, ()))
        for callback in callbacks:
            callback(payload)

    def close(self) -> None:
        self._subscriptions.clear()
