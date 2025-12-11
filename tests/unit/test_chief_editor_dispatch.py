import json
import types
import pytest
import requests

from agents.chief_editor.tools import dispatch_agent_tool
from agents.chief_editor.main import make_editorial_decision_endpoint
from agents.chief_editor.main import EditorialDecisionRequest
import agents.chief_editor.tools as tools_module


class DummyResponse:
    def __init__(self, json_data=None, status_code=200):
        self._json = json_data or {}
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"status {self.status_code}")


def test_dispatch_agent_tool_mcp_success(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        # return a 200 OK for the MCP bus call
        assert url.endswith('/call')
        assert json['agent'] == 'analyst'
        assert json['tool'] == 'analyze_article'
        assert json['kwargs'] == {'article_id': 123}
        return DummyResponse({'status': 'success', 'data': {'analysis_result': True}}, 200)

    monkeypatch.setattr('agents.chief_editor.tools.requests.post', fake_post)

    resp = dispatch_agent_tool('analyst', 'analyze_article', kwargs={'article_id': 123})
    assert resp['status'] == 'success'


def test_dispatch_agent_tool_fallback_orch(monkeypatch):
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append(url)
        if url.endswith('/call'):
            # Simulate MCP bus call failure
            raise requests.exceptions.RequestException('MCP failed')
        elif url.endswith('/jobs/submit'):
            # Ensure job payload has expected fields
            assert json['type'] == 'analysis'
            assert json['payload']['article_id'] == 456
            return DummyResponse({'job_id': 'job_456', 'status': 'submitted'}, 200)
        raise AssertionError('Unexpected URL called')

    monkeypatch.setattr('agents.chief_editor.tools.requests.post', fake_post)

    resp = dispatch_agent_tool('analyst', 'analyze_article', kwargs={'article_id': 456})
    assert resp['status'] == 'submitted'


@pytest.mark.asyncio
async def test_make_editorial_decision_endpoint_dispatches(monkeypatch):
    # Patch tools.make_editorial_decision to simulate a decision that requests routing
    def fake_make_editorial_decision(content, metadata=None):
        return {
            'priority': 'medium',
            'stage': 'intake',
            'confidence': 0.8,
            'reasoning': 'test',
            'next_actions': ['route_to_analyst'],
            'agent_assignments': ['analyst'],
            'metadata': metadata or {}
        }

    monkeypatch.setattr('agents.chief_editor.tools.make_editorial_decision', fake_make_editorial_decision)

    called = {}

    def fake_dispatch(agent_name, tool_name, kwargs=None, use_gpu_orchestrator=None):
        called['agent'] = agent_name
        called['tool'] = tool_name
        called['kwargs'] = kwargs
        return {'status': 'dispatched'}

    monkeypatch.setattr('agents.chief_editor.main.dispatch_agent_tool', fake_dispatch)

    request = EditorialDecisionRequest(content='some content', metadata={'article_id': 999})
    # Call the endpoint function directly
    res = await make_editorial_decision_endpoint(request)
    # Ensure the dispatch helper was invoked
    assert called['agent'] == 'analyst'
    assert called['tool'] == 'analyze_article'
    assert called['kwargs'] == {'article_id': 999}


if __name__ == '__main__':
    pytest.main([__file__])
