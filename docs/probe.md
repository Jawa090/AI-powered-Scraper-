# API Probe & Architecture Experiments (P0.2)

Recorded against installed packages on Windows environment (Python 3.14.7, LangGraph 1.2.12, langchain-google-genai 4.4.0, psycopg 3.3.6).

---

## Installed Packages Overview

| Package | Version |
|---|---|
| `langgraph` | 1.2.12 |
| `langgraph-checkpoint` | 4.2.0 |
| `langgraph-checkpoint-postgres` | 3.1.2 |
| `langchain` | 1.4.3 |
| `langchain-core` | 1.6.6 |
| `langchain-google-genai` | 4.4.0 |
| `psycopg` | 3.3.6 |
| `psycopg-pool` | 3.3.3 |
| `SQLAlchemy` | 2.1.1 |
| `pgvector` | 0.5.0 |
| `httpx` | 0.28.1 |
| `PyJWT` | 2.15.1 |
| `pydantic` | 2.13.5 |
| `fastapi` | 0.141.1 |
| `alembic` | 1.20.0 |
| `pytest` | 9.1.1 |

---

## Experiment Results (E1–E12)

### E1: Tool returning `Command(update=...)` inside `ToolNode` updates state
- **Question:** Does a tool returning `Command(update=...)` inside `ToolNode` update state?
- **Finding:** YES, but in LangGraph 1.2+, `ToolNode` strictly validates that every tool call in message history has a matching `ToolMessage`. Therefore, the tool MUST inject `tool_call_id: Annotated[str, InjectedToolCallId]` and include `ToolMessage(content=..., tool_call_id=tool_call_id)` in `Command.update['messages']`.
- **Working Code:**
```python
from typing import Annotated, TypedDict
import operator
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.types import Command
from langchain_core.tools import tool, InjectedToolCallId
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

class State(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    custom_field: str

@tool
def sample_tool(tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
    return Command(update={
        'custom_field': 'updated_by_tool',
        'messages': [ToolMessage(content='Success', tool_call_id=tool_call_id)]
    })

tool_node = ToolNode([sample_tool])
builder = StateGraph(State)
builder.add_node('tools', tool_node)
builder.add_edge(START, 'tools')
builder.add_edge('tools', END)
graph = builder.compile()

initial_msg = AIMessage(content='', tool_calls=[{'name': 'sample_tool', 'args': {}, 'id': 'call_1'}])
res = graph.invoke({'messages': [initial_msg], 'custom_field': 'initial'})
assert res['custom_field'] == 'updated_by_tool'
```

---

### E2: Accessor exposing pending interrupt on `graph.get_state(config)`
- **Question:** Which accessor exposes a pending interrupt on `graph.get_state(config)` (`.tasks[i].interrupts` or `.interrupts`)?
- **Finding:** Both exist! `state.interrupts` is a direct property on `StateSnapshot` that returns a tuple of `Interrupt` objects (e.g. `(Interrupt(value=...),)`). Each task in `state.tasks` also has `.interrupts`. The canonical and cleanest accessor is `state.interrupts` (non-empty tuple when interrupted).
- **Working Code:**
```python
state = graph.get_state(config)
if state.interrupts:
    interrupt_value = state.interrupts[0].value
```

---

### E3: Retrying failed node with `graph.invoke(None, config)`
- **Question:** After a node raises, does `graph.invoke(None, config)` re-run that node with earlier state intact?
- **Finding:** YES. When a node raises an unhandled exception, `state.next` retains the failed node name. Calling `graph.invoke(None, config)` re-runs the node with all previous checkpointed state intact.
- **Working Code:**
```python
config = {'configurable': {'thread_id': 't3'}}
try:
    graph.invoke({'count': 5}, config)
except ValueError:
    pass

state_before = graph.get_state(config)
assert state_before.next == ('step',)
res = graph.invoke(None, config)
assert res['count'] == 15
```

---

### E4: Node re-execution behavior on `Command(resume=...)`
- **Question:** On `Command(resume=...)`, does the node containing `interrupt()` re-run from its first line?
- **Finding:** YES. LangGraph re-executes the node containing `interrupt()` from the very first line of that function. The `interrupt()` call returns the resumed value on the second execution. Any side-effects prior to `interrupt()` in that node are executed again.
- **Working Code:**
```python
executions = []
def node_with_interrupt(state: State) -> State:
    executions.append('first_line')
    val = interrupt('ask')
    executions.append('after_interrupt')
    return {'val': val}

# First run: executions == ['first_line']
# graph.invoke(Command(resume='ok'), config)
# Second run: executions == ['first_line', 'first_line', 'after_interrupt']
```

---

### E5: Thinking-level constructor parameter of `ChatGoogleGenerativeAI`
- **Question:** What is the thinking-level constructor parameter of the installed `ChatGoogleGenerativeAI`?
- **Finding:** `thinking_budget` (takes `int | None`) and `thinking_config` (takes `dict[str, Any] | ThinkingConfig | None`).
- **Working Code:**
```python
from langchain_google_genai import ChatGoogleGenerativeAI
# Direct parameter:
model = ChatGoogleGenerativeAI(
    model='gemini-2.5-flash',
    google_api_key=api_key,
    thinking_budget=1024,  # or thinking_config={'thinking_budget': 1024}
)
```

---

### E6: `PostgresSaver(pool)` with `dict_row` and idempotent `setup()`
- **Question:** Does `PostgresSaver(pool)` with `dict_row` work, and is `setup()` idempotent?
- **Finding:** YES. Initializing `ConnectionPool(..., kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0})` and passing it to `PostgresSaver(pool)` works cleanly. Calling `saver.setup()` multiple times is fully idempotent and succeeds without errors.
- **Working Code:**
```python
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres import PostgresSaver

pool = ConnectionPool(
    conninfo=DB_URL,
    max_size=5,
    open=True,
    kwargs={'autocommit': True, 'row_factory': dict_row, 'prepare_threshold': 0}
)
saver = PostgresSaver(pool)
saver.setup()
saver.setup()  # Idempotent
pool.close()
```

---

### E7: Invoking with new input after failed run
- **Question:** After a failed run (`state.next` non-empty), does invoking with **new input** start from START (pending task dropped) or not?
- **Finding:** It starts from START with the new input, dropping the pending failed task and progressing forward through START.
- **Working Code:**
```python
# Initial failed invoke leaves st.next == ('A',)
res = graph.invoke({'val': 'new_input'}, config)
# Executes START -> A -> B cleanly with new input
assert res['val'] == 'new_input -> A -> B'
```

---

### E8: Repairing dangling tool calls via `graph.update_state`
- **Question:** Does `graph.update_state(config, {"messages": [ToolMessage(...)]}, as_node=...)` work for repairing dangling tool calls?
- **Finding:** YES. Passing a `ToolMessage` with the matching `tool_call_id` to `graph.update_state(config, {"messages": [ToolMessage(...)]}, as_node="agent")` appends the message and resolves the dangling tool call.
- **Working Code:**
```python
repair_msg = ToolMessage(content='error: tool unavailable', tool_call_id='c1')
graph.update_state(config, {'messages': [repair_msg]}, as_node='agent')
```

---

### E9: JWT Exception Hierarchy (`InvalidSignatureError` vs `DecodeError`)
- **Question:** Is `issubclass(jwt.InvalidSignatureError, jwt.DecodeError)` true?
- **Finding:** YES (`True`). In `PyJWT`, `InvalidSignatureError` subclasses `DecodeError`. In the original unpatched codebase, an `except jwt.DecodeError:` block fell back to `user_id = token`, allowing forged tokens with invalid signatures to be accepted as valid logins.
- **Working Code:**
```python
import jwt
assert issubclass(jwt.InvalidSignatureError, jwt.DecodeError) is True
```

---

### E10: Gemini handling history with tool calls, tool results, and `[JOB EVENT]`
- **Question:** Does Gemini accept history with AI tool-call messages + ToolMessages + a HumanMessage starting with `[JOB EVENT]`?
- **Finding:** YES. Tested against Google GenAI API with `ChatGoogleGenerativeAI(model=...)`. Gemini successfully accepts the conversation sequence:
  1. `HumanMessage`
  2. `AIMessage` with `tool_calls`
  3. `ToolMessage` with matching `tool_call_id`
  4. `HumanMessage` beginning with `[JOB EVENT]`
- **Note:** In newer API endpoints, `gemini-2.0-flash` is superseded by `gemini-2.5-flash` / `gemini-3.8-flash`.

---

### E11: `Command(resume=..., update={...})` at `invoke` level
- **Question:** Does `Command(resume=..., update={...})` at `invoke` level apply the update directly?
- **Finding:** YES. When passed to `graph.invoke(Command(resume=..., update={...}), config)`, the update dictionary is applied directly to the graph state upon resumption. There is no need for a separate `update_state` call.
- **Working Code:**
```python
res = graph.invoke(Command(resume='approved', update={'extra': 'updated_extra'}), config)
assert res['extra'] == 'updated_extra'
```

---

### E12: `ToolNode` handling unregistered tool names
- **Question:** Does `ToolNode` error on a tool call whose name isn't in its tool list?
- **Finding:** YES. When `ToolNode` receives a tool call whose name is not registered, it returns a `ToolMessage` with `status="error"` and content: `"Error: <name> is not a valid tool, try one of [...]"`. Consequently, pseudo-tools such as `propose_scrape` must NEVER be routed to `ToolNode`; they must be routed to custom graph nodes (e.g. `validate_proposal`).
