def absolute_divergence(predicted: float, observed: float) -> float:
    return abs(float(predicted) - float(observed))


def normalized_divergence(predicted: float, observed: float, scale: float) -> float:
    if scale <= 0:
        raise ValueError("scale must be positive")
    return absolute_divergence(predicted, observed) / scale
