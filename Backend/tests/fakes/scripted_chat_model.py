"""Scripted chat model fake for testing LangGraph and LLM layer without real API calls."""
from typing import Any, Callable, List, Optional, Sequence, Union
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class ScriptedChatModel(BaseChatModel):
    """A fake BaseChatModel that returns scripted responses or raises configured errors."""

    scripted_responses: List[Union[AIMessage, Exception]] = Field(default_factory=list)
    structured_responses: List[Any] = Field(default_factory=list)
    call_history: List[List[BaseMessage]] = Field(default_factory=list)
    mode: Optional[str] = None  # None | "timeout" | "auth_error" | "rate_limited" | "server_error"
    _current_index: int = 0
    _structured_index: int = 0

    class Config:
        arbitrary_types_allowed = True

    @property
    def _llm_type(self) -> str:
        return "scripted-fake-chat-model"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.call_history.append(messages)

        if self.mode == "timeout":
            import httpx
            raise httpx.TimeoutException("Scripted timeout error")
        elif self.mode == "auth_error":
            raise PermissionError("Scripted 401 unauthorized / invalid API key")
        elif self.mode == "rate_limited":
            raise RuntimeError("Scripted 429 ResourceExhausted rate limit")
        elif self.mode == "server_error":
            raise RuntimeError("Scripted 500 InternalServerError")

        if self._current_index < len(self.scripted_responses):
            resp = self.scripted_responses[self._current_index]
            self._current_index += 1
            if isinstance(resp, Exception):
                raise resp
            generation = ChatGeneration(message=resp)
            return ChatResult(generations=[generation])

        default_msg = AIMessage(content="Default scripted assistant response.")
        return ChatResult(generations=[ChatGeneration(message=default_msg)])

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedChatModel":
        return self

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        class ScriptedStructuredRunnable:
            def __init__(self, outer: "ScriptedChatModel"):
                self.outer = outer

            def invoke(self, input_messages: Any, config: Optional[dict] = None) -> Any:
                if self.outer.mode == "timeout":
                    import httpx
                    raise httpx.TimeoutException("Scripted timeout error")
                elif self.outer.mode == "auth_error":
                    raise PermissionError("Scripted auth error")
                elif self.outer.mode == "rate_limited":
                    raise RuntimeError("Scripted rate limit")
                elif self.outer.mode == "server_error":
                    raise RuntimeError("Scripted 500 server error")

                if self.outer._structured_index < len(self.outer.structured_responses):
                    val = self.outer.structured_responses[self.outer._structured_index]
                    self.outer._structured_index += 1
                    return val
                if isinstance(schema, type) and hasattr(schema, "__fields__"):
                    return schema()
                return {}

        return ScriptedStructuredRunnable(self)
