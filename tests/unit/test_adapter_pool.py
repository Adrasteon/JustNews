import importlib.util


def test_adapter_pool_spawn(tmp_path, monkeypatch):
    # run workers in test mode for a very short hold time to ensure script path is sound
    monkeypatch.setenv('RE_RANKER_TEST_MODE', '1')

    spec = importlib.util.spec_from_file_location('pool', 'scripts/ops/adapter_worker_pool.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # spawn a single worker for 1 second and return quickly
    # call spawn_pool directly with a short hold to avoid long tests
    mod.spawn_pool(num_workers=1, model_id=None, adapter=None, hold_time=1)

    # If we get here without exceptions, test is successful
    assert True
