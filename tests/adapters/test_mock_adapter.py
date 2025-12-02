from agents.common.mock_adapter import MockAdapter


def test_mock_adapter_basic():
    m = MockAdapter(name="tst", delay=0)
    m.load("mock-model")
    h = m.health_check()
    assert h["loaded"] is True
    out = m.infer("hello world")
    assert "text" in out
    assert out["tokens"] > 0
    batch = m.batch_infer(["a", "b"])
    assert isinstance(batch, list) and len(batch) == 2
    m.unload()
    h2 = m.health_check()
    assert not h2["loaded"]
