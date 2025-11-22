"""7B re-ranker helper — lightweight wrapper for loading an OSS 7B model in int8
for re-ranking candidate passages and scoring them.

Design decisions:
- Default model: environment variable `RE_RANKER_MODEL` or fallback to a small stub
- Uses bitsandbytes `BitsAndBytesConfig` when available and environment indicates 8-bit
- Testable in CI by setting `RE_RANKER_TEST_MODE=1` which uses a deterministic stub model
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, List, Sequence

try:
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
    import torch
except Exception:
    AutoTokenizer = None
    AutoModelForCausalLM = None
    BitsAndBytesConfig = None
    torch = None


@dataclass
class ReRankCandidate:
    id: str
    text: str


class _StubReRanker:
    """Simple deterministic scorer used in test mode or when model unavailable.

    Scoring strategy: length-based deterministic score for reproducible tests.
    """

    def __init__(self):
        pass

    def score(self, query: str, candidates: Sequence[ReRankCandidate]) -> List[float]:
        # deterministic scoring: longer overlap / length heuristics
        qwords = set(query.lower().split())
        scores = []
        for c in candidates:
            common = len(qwords.intersection(set(c.text.lower().split())))
            # base score is number of common words + normalized length
            scores.append(float(common) + len(c.text) / 1000.0)
        return scores


class ReRanker:
    """Wraps a quantized 7B model for re-ranking tasks.

    On an RTX 3090 we expect int8 loading to be available; for tests the
    `RE_RANKER_TEST_MODE=1` environment variable will use the deterministic stub
    so tests run quickly and offline.
    """

    def __init__(self, model_id: str | None = None):
        self.model_id = model_id or os.environ.get("RE_RANKER_MODEL")
        self.test_mode = os.environ.get("RE_RANKER_TEST_MODE") in ("1", "true")
        self.model = None
        self.tokenizer = None

        if self.test_mode or AutoModelForCausalLM is None:
            # fallback stub for test mode or missing deps
            self._impl = _StubReRanker()
        else:
            self._impl = None
            self._load_model()

    def _load_model(self) -> None:
        # If user set 8-bit preference, configure bitsandbytes
        load_in_8bit = os.environ.get("RE_RANKER_LOAD_8BIT", "1") in ("1", "true")
        if load_in_8bit and BitsAndBytesConfig is not None and torch is not None:
            bnb = BitsAndBytesConfig(
                load_in_8bit=True,
                bnb_8bit_compute_dtype=getattr(torch, "float16", None),
                bnb_8bit_use_double_quant=True,
            )
            model = AutoModelForCausalLM.from_pretrained(
                self.model_id,
                device_map="auto",
                quantization_config=bnb,
                trust_remote_code=True,
            )
        else:
            # fallback non-quantized loading
            model = AutoModelForCausalLM.from_pretrained(self.model_id, device_map="auto", trust_remote_code=True)

        tokenizer = AutoTokenizer.from_pretrained(self.model_id)

        self.model = model
        self.tokenizer = tokenizer
        self._impl = model

    def score(self, query: str, candidates: Sequence[ReRankCandidate]) -> List[float]:
        """Return a list of scores aligned with candidates.

        If using a real model, we implement a cheap scoring heuristic: compute
        a log-probability for each candidate appended to query by the causal LM.
        This is intentionally simple (no beam or full rerank pipeline) — the
        goal is a prototype re-ranker showing how to integrate an int8 7B model.
        """
        if isinstance(self._impl, _StubReRanker):
            return self._impl.score(query, candidates)

        # Model-based scoring
        scores = []
        for c in candidates:
            # build prompt: query + candidate
            input_text = f"Query: {query}\nCandidate: {c.text}\nScore:"  # model will continue
            inputs = self.tokenizer(input_text, return_tensors="pt")
            if torch is not None and torch.cuda.is_available():
                inputs = {k: v.to("cuda") for k, v in inputs.items()}

            with torch.no_grad():
                out = self.model(**inputs, return_dict=True)

            # heuristic: negative mean of logits for the 'Score' token region as a stand-in
            # This is intentionally lightweight; replace with a cross-encoder for production.
            logits = out.logits
            # take mean over last token logits, sum softmax probability of EOS-ish token
            last_logits = logits[:, -1, :]
            # compute normalized score
            probs = last_logits.softmax(dim=-1).max().values.item()
            scores.append(float(probs))

        return scores


def simple_demo():
    model = ReRanker()
    queries = "Is the company profitable?"
    cands = [ReRankCandidate(id="a1", text="The company saw revenue growth in Q4."), ReRankCandidate(id="a2", text="We reported losses last year.")]
    print(model.score(queries, cands))


if __name__ == "__main__":
    simple_demo()
