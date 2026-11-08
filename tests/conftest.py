import pytest

@pytest.fixture(autouse=True)
def disable_llm_cache_for_mock_tests(monkeypatch, request):
    """Disable LLM cache for mock routing and transport tests so mock assertions pass."""
    if "test_llm_cache" not in request.node.nodeid:
        monkeypatch.setenv("MODERATOR_LLM_CACHE", "0")
