from __future__ import annotations

import base64
import json
from dataclasses import asdict, dataclass


@dataclass(slots=True)
class SecureMessage:
    algorithm: str
    device_id: str
    session_id: str
    sequence_number: int
    timestamp: float
    nonce: bytes
    ciphertext: bytes
    signature: bytes

    def to_bytes(self) -> bytes:
        data = asdict(self)
        for field in ("nonce", "ciphertext", "signature"):
            data[field] = base64.b64encode(data[field]).decode()
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()

    @classmethod
    def from_bytes(cls, value: bytes) -> SecureMessage:
        data = json.loads(value.decode())
        for field in ("nonce", "ciphertext", "signature"):
            data[field] = base64.b64decode(data[field], validate=True)
        return cls(**data)

    def signing_bytes(self) -> bytes:
        unsigned = {
            "algorithm": self.algorithm,
            "device_id": self.device_id,
            "session_id": self.session_id,
            "sequence_number": self.sequence_number,
            "timestamp": self.timestamp,
            "nonce": base64.b64encode(self.nonce).decode(),
            "ciphertext": base64.b64encode(self.ciphertext).decode(),
        }
        return json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
