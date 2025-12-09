def test_copilot_instructions_enforce_canonical_env():
    """Ensure our assistant instructions explicitly require the canonical env for scripts/tests."""
    import pathlib

    p = pathlib.Path(__file__).resolve().parents[1] / "docs" / "copilot_instructions.md"
    assert p.exists(), f"Missing docs file: {p}"
    content = p.read_text(encoding="utf-8")
    # The rule should explicitly say assistants MUST use the canonical conda env
    assert "MUST use the canonical conda environment" in content or "always use the canonical" in content
