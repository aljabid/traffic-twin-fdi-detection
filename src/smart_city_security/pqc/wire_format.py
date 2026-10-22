from smart_city_security.schemas import SecureMessage


def serialize(message: SecureMessage) -> bytes:
    return message.to_bytes()


def deserialize(payload: bytes) -> SecureMessage:
    try:
        return SecureMessage.from_bytes(payload)
    except Exception as exc:
        raise ValueError("Invalid secure-message wire format") from exc
