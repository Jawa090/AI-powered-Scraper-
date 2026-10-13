from unittest.mock import MagicMock
from langchain_core.messages import AIMessage
import pytest
from agents.llm import chat_model as llm


def test_chain_reaches_fallback_without_primary_configuration(monkeypatch):
    monkeypatch.setattr(llm.ProviderChain, '_candidates', lambda self: iter([
        ('deepseek', 'openai_compatible', 'primary', '', ''),
        ('gemini', 'gemini', 'fallback', 'test-key', '')]))
    model = MagicMock(); model.invoke.return_value = AIMessage(content='fallback result')
    monkeypatch.setattr(llm, '_build_model', lambda **kwargs: model)
    assert llm.invoke_llm(llm.get_chat_model(), []).content == 'fallback result'


def test_structured_chain_falls_back_after_construction_failure(monkeypatch):
    monkeypatch.setattr(llm.ProviderChain, '_candidates', lambda self: iter([
        ('deepseek', 'openai_compatible', 'primary', 'test-key', ''),
        ('gemini', 'gemini', 'fallback', 'test-key', '')]))
    model = MagicMock(); model.with_structured_output.return_value.invoke.return_value = {'decision': 'modify'}
    def build(**kwargs):
        if kwargs['model'] == 'primary':
            raise RuntimeError('SDK construction failed')
        return model
    monkeypatch.setattr(llm, '_build_model', build)
    assert llm.invoke_structured(dict, []) == {'decision': 'modify'}


def test_all_provider_failure_is_explicit(monkeypatch):
    monkeypatch.setattr(llm.ProviderChain, '_candidates', lambda self: iter([
        ('deepseek', 'openai_compatible', 'primary', 'test-key', '')]))
    def build(**kwargs):
        raise llm.LLMUnavailable('auth_error')
    monkeypatch.setattr(llm, '_build_model', build)
    with pytest.raises(llm.LLMUnavailable):
        llm.invoke_llm(llm.get_chat_model(), [])
