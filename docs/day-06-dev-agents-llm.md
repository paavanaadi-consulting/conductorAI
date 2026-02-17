# Day 6: LLM Provider + Development Agents

**Date**: Day 6 of 10-Day Build
**Components**: `BaseLLMProvider`, `MockLLMProvider`, `CodingAgent`, `ReviewAgent`
**Tests**: 103 new tests (38 LLM provider + 34 CodingAgent + 31 ReviewAgent)
**Total**: 381 tests passing
**Status**: ✅ Complete

---

## Overview

Day 6 marks a major milestone: the first **specialized agents** and the **LLM integration layer**. ConductorAI can now generate code and review it — the first two steps of the DEVELOPMENT phase pipeline.

```
┌─────────────── INTEGRATION LAYER ───────────────┐
│                                                   │
│  ┌──────────────────────────────────────────┐    │
│  │     BaseLLMProvider (abstract)            │    │
│  │     ├── MockLLMProvider (testing)         │    │
│  │     ├── OpenAIProvider (future Day 9)     │    │
│  │     └── AnthropicProvider (future Day 9)  │    │
│  └──────────────────────────────────────────┘    │
│            ↑ generate()                           │
└────────────┼─────────────────────────────────────┘
             │
┌────────────┼─────── AGENT LAYER ─────────────────┐
│            │                                      │
│  ┌─────────▼────┐     ┌──────────────┐          │
│  │ CodingAgent  │ ──→ │ ReviewAgent  │          │
│  │ (generates)  │     │ (reviews)    │          │
│  └──────────────┘     └──────────────┘          │
│                                                   │
│  Future Day 7:                                    │
│  ┌──────────────┐     ┌──────────────┐          │
│  │ TestDataAgent│ ──→ │  TestAgent   │          │
│  └──────────────┘     └──────────────┘          │
└───────────────────────────────────────────────────┘
```

---

## LLM Provider Abstraction

### Why an Abstraction Layer?

Agents don't call OpenAI or Anthropic directly. They call through `BaseLLMProvider`:

1. **Swappability** — Switch providers with one config change
2. **Testability** — MockLLMProvider for tests, no API keys needed
3. **Consistency** — All providers return the same `LLMResponse` type
4. **Observability** — Centralized token tracking and logging

### BaseLLMProvider (Abstract)

**File**: `src/conductor/integrations/llm/base.py`

```python
class BaseLLMProvider(ABC):
    """Abstract interface for LLM providers."""

    async def generate(self, prompt, **kwargs) -> LLMResponse: ...
    async def generate_with_system(self, system_prompt, user_prompt, **kwargs) -> LLMResponse: ...
    async def validate(self) -> bool: ...
    def get_available_models(self) -> list[str]: ...
```

### LLMResponse Model

Every LLM call returns the same standardized response:

```python
class LLMResponse(BaseModel):
    content: str           # The generated text
    model: str             # Model that produced it
    usage: LLMUsage        # Token counts (prompt, completion, total)
    finish_reason: str     # "stop", "length", or "error"
    metadata: dict         # Provider-specific extras
    created_at: datetime   # Timestamp
```

### MockLLMProvider

**File**: `src/conductor/integrations/llm/mock.py`

The mock provider is the default for testing and development:

| Feature | Description |
|---|---|
| Response Queue | FIFO queue of pre-configured responses |
| Smart Defaults | Context-aware responses based on prompt keywords |
| Call Tracking | Records all calls for test assertions |
| Token Simulation | Estimates usage from text length |
| Error Simulation | `set_should_fail(True)` for testing error paths |

```python
# Basic usage
provider = MockLLMProvider()
provider.queue_response("def hello(): return 'world'")
response = await provider.generate("Write a function")
assert response.content == "def hello(): return 'world'"

# Smart defaults (no queue needed)
response = await provider.generate("Generate code for an API")
# Returns mock Python code automatically

# Error simulation
provider.set_should_fail(True, "API overloaded")
# All generate() calls now raise RuntimeError
```

### Factory Function

```python
from conductor.integrations.llm import create_llm_provider

provider = create_llm_provider(config.llm)
# Returns MockLLMProvider for "mock"
# OpenAI/Anthropic in Day 9
```

---

## CodingAgent

**File**: `src/conductor/agents/development/coding_agent.py`

### What It Does

The CodingAgent generates source code from specifications. It is the entry point of the DEVELOPMENT phase.

### Input / Output

**Input** (`task.input_data`):
```python
{
    "specification": "Create a REST API for user management",  # REQUIRED
    "language": "python",          # optional, default "python"
    "framework": "fastapi",        # optional
    "additional_context": "...",   # optional
    "file_name": "api.py",        # optional
}
```

**Output** (`result.output_data`):
```python
{
    "code": "...",                 # The generated source code
    "language": "python",
    "framework": "fastapi",
    "description": "Generated python code for: Generate API",
    "files": ["api.py"],
    "llm_model": "gpt-4",
    "llm_usage": {"prompt_tokens": 100, "completion_tokens": 200, ...},
    "specification": "Create a REST API...",
}
```

### Execution Flow

```
CodingAgent._execute(task)
  │
  ├─ 1. Extract specification, language, framework from input_data
  │
  ├─ 2. Build user prompt with _build_user_prompt()
  │     └─ Includes: specification, language, framework, additional_context
  │
  ├─ 3. Call LLM: generate_with_system(CODING_SYSTEM_PROMPT, user_prompt)
  │     └─ System prompt defines LLM as expert developer
  │
  └─ 4. Package response into TaskResult with structured output_data
```

### System Prompt

The CodingAgent uses a carefully crafted system prompt:
- Expert software developer role
- Clean, documented, production-quality code
- Type hints, docstrings, error handling
- Language-specific best practices
- SOLID principles

---

## ReviewAgent

**File**: `src/conductor/agents/development/review_agent.py`

### What It Does

The ReviewAgent examines code and evaluates quality, bugs, style, and best practices. It produces a structured review with an approval decision.

### Input / Output

**Input** (`task.input_data`):
```python
{
    "code": "def hello(): ...",              # REQUIRED
    "language": "python",                    # optional
    "review_criteria": ["security", ...],    # optional focus areas
    "context": "REST API endpoint",          # optional
    "specification": "Build user auth",      # optional
}
```

**Output** (`result.output_data`):
```python
{
    "review": "## Code Review Summary...",   # Full LLM review text
    "approved": True,                        # Based on score vs threshold
    "score": 8,                              # Quality score (1-10)
    "findings": [                            # Parsed issues
        "Missing input validation",
        "No error handling",
    ],
    "recommendations": [                     # Parsed suggestions
        "Add type hints",
        "Add logging",
    ],
    "language": "python",
    "llm_model": "gpt-4",
    "llm_usage": {...},
}
```

### Approval Logic

The ReviewAgent uses a configurable **approval threshold** (default: 6):

```
Score >= threshold → approved = True  (e.g., 8 >= 6 → APPROVED)
Score <  threshold → approved = False (e.g., 3 <  6 → REJECTED)
```

### Response Parsing

The ReviewAgent parses the LLM's free-text review into structured data:

1. **Score extraction**: Regex patterns match `Score: 8/10`, `Quality: 7`, `8 out of 10`
2. **Findings extraction**: Numbered/bulleted items after "Findings" header
3. **Recommendations extraction**: Items after "Recommendations" header
4. **Fallback**: If parsing fails, returns sensible defaults (score=7, empty lists)

---

## Design Decisions

### 1. LLM as Constructor Dependency

**Decision**: The LLM provider is injected via constructor, not resolved from config.

```python
agent = CodingAgent("coding-01", config, llm_provider=mock_provider)
```

**Rationale**: Explicit dependency injection makes testing trivial — just pass a MockLLMProvider. No global state, no service locator, no monkey-patching.

### 2. System + User Prompt Pattern

**Decision**: Agents always use `generate_with_system()` (not plain `generate()`).

**Rationale**: The system prompt defines the LLM's role (expert developer, senior reviewer) while the user prompt contains the actual task. This separation produces better LLM output.

### 3. Lenient Response Parsing

**Decision**: The ReviewAgent's parser falls back to defaults if it can't extract structured data.

**Rationale**: LLMs are unpredictable in output format. If the parser fails, the agent still returns a valid result with `score=7` and empty findings — better than crashing.

### 4. BaseAgent Handles Errors

**Decision**: If the LLM call fails (RuntimeError), BaseAgent catches it and returns a FAILED TaskResult.

**Rationale**: This is the Template Method pattern at work. Agents focus on business logic; BaseAgent handles the lifecycle. LLM failures become structured FAILED results, not unhandled exceptions.

---

## Testing Summary

### LLM Provider Tests (38 tests)

| Category | Tests | What's Verified |
|---|---|---|
| LLMUsage Model | 3 | Defaults, custom values, serialization |
| LLMResponse Model | 4 | Basic, with usage, metadata, error finish_reason |
| Mock Init | 4 | Default config, custom config, initial state, repr |
| Response Queue | 5 | Text queue, FIFO order, full LLMResponse queue, clear, metadata |
| Smart Defaults | 5 | Code keyword, review keyword, test keyword, unknown, metadata |
| Call Tracking | 4 | Basic recording, system prompt, clear history, kwargs |
| Error Simulation | 4 | Should fail, records call on fail, disable failure, system prompt fail |
| Validation | 2 | Always true, available models |
| Factory | 4 | Create mock, case-insensitive, unknown raises, passes config |

### CodingAgent Tests (34 tests)

| Category | Tests | What's Verified |
|---|---|---|
| Initialization | 4 | Type, identity, custom name, provider access |
| Validation | 5 | Valid spec, missing spec, empty spec, whitespace, raises AgentError |
| Execution | 6 | Generates code, files list, LLM metadata, custom language, custom filename, spec in output |
| LLM Interaction | 5 | Uses generate_with_system, prompt has spec, language, framework, additional context |
| Error Handling | 2 | LLM failure → FAILED result, returns to IDLE |
| Startup | 2 | Validates provider, sets IDLE |
| Prompt Building | 3 | Basic, with framework, with context |
| File Extensions | 7 | python, javascript, typescript, go, rust, unknown, case-insensitive |

### ReviewAgent Tests (31 tests)

| Category | Tests | What's Verified |
|---|---|---|
| Initialization | 6 | Type, identity, default threshold, custom threshold, clamping, provider |
| Validation | 5 | Valid code, missing code, empty, whitespace, raises AgentError |
| Execution | 5 | Reviews code, findings, recommendations, LLM metadata, language |
| Approval Logic | 3 | High score approved, low score rejected, exact threshold |
| LLM Interaction | 3 | Uses generate_with_system, prompt has code, prompt has criteria |
| Response Parsing | 6 | Standard score, quality format, default score, findings, recommendations, empty |
| Error Handling | 2 | LLM failure → FAILED, returns to IDLE |
| Prompt Building | 4 | Basic, with context, with specification, with criteria |

---

## Files Created

| File | Purpose |
|---|---|
| `src/conductor/integrations/__init__.py` | Integration layer package |
| `src/conductor/integrations/llm/__init__.py` | LLM sub-package exports |
| `src/conductor/integrations/llm/base.py` | BaseLLMProvider + LLMResponse |
| `src/conductor/integrations/llm/mock.py` | MockLLMProvider |
| `src/conductor/integrations/llm/factory.py` | create_llm_provider factory |
| `src/conductor/agents/development/__init__.py` | Development agents package |
| `src/conductor/agents/development/coding_agent.py` | CodingAgent |
| `src/conductor/agents/development/review_agent.py` | ReviewAgent |
| `tests/test_integrations/test_llm_provider.py` | LLM provider tests (38) |
| `tests/test_agents/test_development/test_coding_agent.py` | CodingAgent tests (34) |
| `tests/test_agents/test_development/test_review_agent.py` | ReviewAgent tests (31) |

---

## What's Next

**Day 7** completes the Agent Layer with the remaining development agents:
- **TestDataAgent**: Generates test data and fixtures
- **TestAgent**: Creates and executes test suites
- **DevOpsAgent**: Creates CI/CD configurations
- **DeployingAgent**: Handles deployment

These agents will follow the same patterns established here — BaseAgent subclass with LLM provider injection, structured input/output, and comprehensive tests.
