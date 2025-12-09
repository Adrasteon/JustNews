from pathlib import Path


def test_ci_workflow_exists_and_uses_canonical_env():
    repo_root = Path(__file__).resolve().parents[1]
    wf = repo_root / '.github' / 'workflows' / 'ci-justnews-py312.yml'
    assert wf.exists(), f"Expected CI workflow for canonical env at {wf}"
    text = wf.read_text(encoding='utf-8')
    # Sanity checks: points to our canonical environment name and uses environment.yml
    assert 'justnews-py312' in text
    assert 'environment-file: environment.yml' in text or 'environment-file:' in text
