import importlib.util


def test_parse_args_and_dry_run():
    # Load the script by path and call main() with --dry-run
    spec = importlib.util.spec_from_file_location("train_qlora", "scripts/train_qlora.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    rc = module.main(["--dry-run"])
    assert rc == 0
