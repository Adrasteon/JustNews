import io
import textwrap
import pytest

from scripts import news_outlets


def test_parse_domains_from_markdown():
    content = textwrap.dedent("""
        # Example list

        - bbc.co.uk
        - https://www.reuters.com
        - Example.com
        Some trailing text with domain: cnn.com and some noise
    """)

    domains = news_outlets.parse_domains_from_text(content)
    assert isinstance(domains, list)
    assert "bbc.co.uk" in domains
    assert "reuters.com" in domains
    assert "example.com" in domains
    assert "cnn.com" in domains


def test_dry_run_prints_domains(tmp_path, capsys):
    sample = tmp_path / "sample.md"
    sample.write_text("bbc.co.uk\nhttps://nytimes.com/article\ncnn.com\n")

    rc = news_outlets.main(["--file", str(sample), "--dry-run"])
    assert rc == 0
    captured = capsys.readouterr()
    # Expect it to list the domains
    assert "bbc.co.uk" in captured.out
    assert "nytimes.com" in captured.out
    assert "cnn.com" in captured.out
