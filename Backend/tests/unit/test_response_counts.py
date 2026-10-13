import pytest
from langchain_core.messages import AIMessage
from agents.graph.nodes import finalize as node
from agents.llm.chat_model import LLMUnavailable
import importlib
module = importlib.import_module('agents.graph.nodes.finalize')


def test_wrong_small_record_count_is_repaired(monkeypatch):
    monkeypatch.setattr(module, 'invoke_llm', lambda *a: AIMessage(content='Found 0 matching companies.'))
    response = module.grounded_reply(object(), [], {'available': 0, 'returned': 0},
        AIMessage(content='Found **10 roofing companies**.', id='reply'))
    assert response.content == 'Found 0 matching companies.' and response.id == 'reply'


def test_unrepaired_count_fails_without_delivering_a_false_success(monkeypatch):
    monkeypatch.setattr(module, 'invoke_llm', lambda *a: AIMessage(content='Here are 10 matching records.'))
    with pytest.raises(LLMUnavailable):
        module.grounded_reply(object(), [], {'recordsFound': 0, 'recordsDelivered': 0},
            AIMessage(content='Here are 10 matching records.'))


def test_actual_available_and_returned_counts_remain_unchanged():
    answer = AIMessage(content='Found 12 matching companies; returned 10 records. You requested 10.')
    assert module.grounded_reply(object(), [], {'available': 12, 'returned': 10}, answer) is answer
