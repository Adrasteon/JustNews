import pytest

from agents.common.adapter_base import BaseAdapter, AdapterError


def test_base_adapter_methods_raise():
    class Concrete(BaseAdapter):
        pass

    obj = Concrete()
    with pytest.raises(NotImplementedError):
        obj.load("x")
    with pytest.raises(NotImplementedError):
        obj.infer("hi")
    with pytest.raises(NotImplementedError):
        obj.batch_infer(["a"])
    with pytest.raises(NotImplementedError):
        obj.health_check()
    with pytest.raises(NotImplementedError):
        obj.unload()
    with pytest.raises(NotImplementedError):
        obj.metadata()
