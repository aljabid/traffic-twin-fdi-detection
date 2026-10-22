from smart_city_security.messaging import TokenBucket


def test_token_bucket_limits_burst():
    bucket = TokenBucket(rate_per_second=1, capacity=2)
    assert bucket.allow(now=1)
    assert bucket.allow(now=1)
    assert not bucket.allow(now=1)
    assert bucket.allow(now=2)
