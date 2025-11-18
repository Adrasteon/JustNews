import pytest

from agents.analyst import tools as analyst_tools


class FakeAnalystEngine:
    def __init__(self):
        self.spacy_nlp = True
        self.ner_pipeline = True
        self.gpu_analyst = False
        self.processing_stats = {'total_processed': 0}

    def extract_entities(self, text):
        return {'entities': [{'text': 'OpenAI', 'label': 'ORG'}], 'total_entities': 1, 'method': 'spacy'}

    def analyze_text_statistics(self, text):
        return {'word_count': 4, 'character_count': len(text), 'sentence_count': 1, 'readability_score': 50}

    def extract_key_metrics(self, text, url=None):
        return {'metrics': [{'name': 'revenue', 'value': 100}], 'total_metrics': 1, 'text_length': len(text), 'url': url}

    def analyze_sentiment(self, text):
        return {'dominant_sentiment': 'positive', 'confidence': 0.9, 'intensity': 'mild', 'method': 'basic'}

    def detect_bias(self, text):
        return {'has_bias': False, 'bias_score': 0.1, 'bias_level': 'low', 'confidence': 0.6}

    def analyze_sentiment_and_bias(self, text):
        return {
            'sentiment_analysis': self.analyze_sentiment(text),
            'bias_analysis': self.detect_bias(text),
            'combined_assessment': {'reliability': 0.9},
            'recommendations': ['source balance']
        }


@pytest.fixture(autouse=True)
def monkey_engine(monkeypatch):
    engine = FakeAnalystEngine()
    # Monkeypatch the module's internal _engine
    monkeypatch.setattr(analyst_tools, '_engine', engine)
    yield
    monkeypatch.setattr(analyst_tools, '_engine', None)


def test_identify_entities_success():
    res = analyst_tools.identify_entities('OpenAI released a new model')
    assert res['total_entities'] == 1
    assert isinstance(res['entities'], list)


def test_identify_entities_empty():
    res = analyst_tools.identify_entities('   ')
    assert res['total_entities'] == 0


def test_analyze_text_statistics_success():
    res = analyst_tools.analyze_text_statistics('This is a test')
    assert res['word_count'] == 4


def test_analyze_text_statistics_empty():
    res = analyst_tools.analyze_text_statistics('')
    assert res['word_count'] == 0


def test_extract_key_metrics_success():
    res = analyst_tools.extract_key_metrics('Revenue was $100', url='https://example.com')
    assert res['total_metrics'] == 1
    assert res['url'] == 'https://example.com'


def test_analyze_sentiment_and_bias():
    res = analyst_tools.analyze_sentiment_and_bias('Neutral content')
    assert 'sentiment_analysis' in res
    assert 'bias_analysis' in res


def test_process_analysis_request_unknown_type(monkeypatch):
    # Use monkeypatch to set module engine
    monkeypatch.setattr(analyst_tools, '_engine', FakeAnalystEngine())
    # Async function; call via pytest
    import asyncio
    res = asyncio.run(analyst_tools.process_analysis_request('x', 'unknown'))
    assert 'error' in res and 'Unknown analysis type' in res['error']
