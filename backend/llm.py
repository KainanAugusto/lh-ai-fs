"""Thin LLM layer shared by every agent.

Two entry points:
- ``call_llm`` — raw text completion (kept for flexibility / debugging).
- ``call_llm_json`` — the workhorse: forces a JSON response, validates it against
  a Pydantic schema, and retries once with a corrective nudge if the model returns
  malformed or schema-invalid JSON. Agents always use this so the data flowing
  between them is typed, never a free-text blob.
"""

from __future__ import annotations

import json

from openai import OpenAI
from pydantic import BaseModel, ValidationError

import config

client = OpenAI(
    api_key=config.OPENAI_API_KEY,
    base_url=config.OPENAI_BASE_URL,
    timeout=config.REQUEST_TIMEOUT,
    max_retries=config.MAX_RETRIES,
)

# Only cap output tokens when explicitly configured (> 0). Forcing a high ceiling
# on a reasoning model makes it think up to that ceiling and time out; leaving it
# unset lets the provider use its (fast) default. See config.MAX_TOKENS.
_MAX_TOKENS_KW = {"max_tokens": config.MAX_TOKENS} if config.MAX_TOKENS > 0 else {}


def call_llm(
    messages: list[dict],
    model: str | None = None,
    temperature: float | None = None,
) -> str:
    """Call the chat completions API and return the response text."""
    response = client.chat.completions.create(
        model=model or config.MODEL,
        messages=messages,
        temperature=config.TEMPERATURE if temperature is None else temperature,
        **_MAX_TOKENS_KW,
    )
    return response.choices[0].message.content


def call_llm_json(
    system: str,
    user: str,
    schema: type[BaseModel],
    model: str | None = None,
    temperature: float | None = None,
) -> BaseModel:
    """Run a single agent step and return a validated instance of ``schema``.

    The expected JSON shape is appended to the system prompt so the model knows
    the exact contract. On malformed/invalid JSON we retry once, feeding the error
    back to the model; a second failure raises.
    """
    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    system_with_schema = (
        f"{system}\n\n"
        "Respond with a single JSON object that conforms exactly to this JSON Schema. "
        "Do not include markdown fences, comments, or any prose outside the JSON. "
        "Do not add any top-level key that is not in the schema (e.g. no 'analysis', "
        "'reasoning', 'thoughts', or 'scratchpad' field) — do any reasoning silently and "
        "output only the final JSON object with exactly the schema's fields populated.\n\n"
        f"JSON Schema:\n{schema_json}"
    )

    messages = [
        {"role": "system", "content": system_with_schema},
        {"role": "user", "content": user},
    ]

    last_error: Exception | None = None
    for attempt in range(2):
        response = client.chat.completions.create(
            model=model or config.MODEL,
            messages=messages,
            temperature=config.TEMPERATURE if temperature is None else temperature,
            response_format={"type": "json_object"},
            **_MAX_TOKENS_KW,
        )
        content = response.choices[0].message.content or ""
        try:
            return schema.model_validate_json(content)
        except (ValidationError, json.JSONDecodeError) as err:
            last_error = err
            # Feed the bad output and the error back for a single corrective retry.
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"That response did not validate against the schema. Error:\n{err}\n\n"
                        "Return corrected JSON that conforms exactly. JSON only."
                    ),
                }
            )

    raise ValueError(f"LLM did not return schema-valid JSON after retry: {last_error}")
