"""
AI Client — Smart fallback across multiple providers.
Priority: Groq (fast, free) → OpenRouter (many models) → Anthropic → OpenAI
"""

import os
import json
from dotenv import load_dotenv

load_dotenv()


def chat(prompt: str, temperature: float = 0.2, max_tokens: int = 500) -> str:
    """
    Send a prompt to the best available AI model.
    Tries providers in order until one succeeds.
    Returns the response text.
    """
    providers = [
        _try_groq,
        _try_openrouter,
        _try_anthropic,
        _try_openai,
    ]

    last_error = None
    for provider in providers:
        try:
            result = provider(prompt, temperature, max_tokens)
            if result:
                return result
        except Exception as e:
            last_error = e
            continue

    raise RuntimeError(f"All AI providers failed. Last error: {last_error}")


def _try_groq(prompt: str, temperature: float, max_tokens: int) -> str:
    """Groq — fast, free tier, llama-3.3-70b"""
    api_key = os.getenv("ai2")
    if not api_key:
        return None

    from openai import OpenAI
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
    )
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


def _try_openrouter(prompt: str, temperature: float, max_tokens: int) -> str:
    """OpenRouter — access to many models"""
    api_key = os.getenv("ai1")
    if not api_key:
        return None

    from openai import OpenAI
    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )
    response = client.chat.completions.create(
        model="meta-llama/llama-3.3-70b-instruct",
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


def _try_anthropic(prompt: str, temperature: float, max_tokens: int) -> str:
    """Anthropic Claude"""
    api_key = os.getenv("ai4")
    if not api_key:
        return None

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def _try_openai(prompt: str, temperature: float, max_tokens: int) -> str:
    """OpenAI GPT-4o (fallback — may have quota issues)"""
    api_key = os.getenv("ai3")
    if not api_key:
        return None

    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


def chat_json(prompt: str, temperature: float = 0.1, max_tokens: int = 500) -> dict:
    """
    Like chat() but parses and returns JSON.
    Strips markdown code fences if present.
    """
    raw = chat(prompt, temperature, max_tokens)

    # Strip markdown code fences
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON from the response
        import re
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        raise ValueError(f"Could not parse JSON from AI response: {raw[:200]}")


if __name__ == "__main__":
    # Test which provider works
    result = chat("Say 'hello' in one word.")
    print(f"AI response: {result}")
