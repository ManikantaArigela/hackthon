"""
llm.py
Multi-provider LLM wrapper for Relay.
Supports Groq (free), Google Gemini (free), Ollama (local/free), and Anthropic.

Set LLM_PROVIDER in .env to choose:
  LLM_PROVIDER=groq        → uses Groq (default, free, fast)
  LLM_PROVIDER=gemini      → uses Google Gemini (free tier)
  LLM_PROVIDER=ollama      → uses Ollama locally (100% free, no internet)
  LLM_PROVIDER=anthropic   → uses Claude (paid)
"""

import json
import os

from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()


# ─── GROQ (Free — recommended) ────────────────────────────────────────────────
def _groq_call(system: str, user: str, max_tokens: int = 512) -> str:
    from groq import Groq
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    return response.choices[0].message.content.strip()


# ─── GOOGLE GEMINI (Free tier) ────────────────────────────────────────────────
def _gemini_call(system: str, user: str, max_tokens: int = 512) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system,
    )
    response = model.generate_content(
        user,
        generation_config=genai.GenerationConfig(max_output_tokens=max_tokens),
    )
    return response.text.strip()


# ─── OLLAMA (Local, 100% free) ────────────────────────────────────────────────
def _ollama_call(system: str, user: str, max_tokens: int = 512) -> str:
    import requests as req
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "llama3.1")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        "stream": False,
        "options": {"num_predict": max_tokens},
    }
    resp = req.post(f"{base_url}/api/chat", json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


# ─── ANTHROPIC (Paid) ─────────────────────────────────────────────────────────
def _anthropic_call(system: str, user: str, max_tokens: int = 512) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    model = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text.strip()


# ─── Public interface ─────────────────────────────────────────────────────────

def llm_call(system: str, user: str, max_tokens: int = 512) -> str:
    """Route to the configured LLM provider and return text response."""
    if PROVIDER == "groq":
        return _groq_call(system, user, max_tokens)
    elif PROVIDER == "gemini":
        return _gemini_call(system, user, max_tokens)
    elif PROVIDER == "ollama":
        return _ollama_call(system, user, max_tokens)
    elif PROVIDER == "anthropic":
        return _anthropic_call(system, user, max_tokens)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: '{PROVIDER}'. Choose: groq | gemini | ollama | anthropic")


def llm_call_json(system: str, user: str) -> dict:
    """
    Call the LLM expecting a JSON response.
    Strips markdown fences. Retries once on bad JSON parse.
    """
    system_json = system + "\n\nYou MUST respond with valid JSON only. No explanation, no markdown fences."
    raw = llm_call(system_json, user)

    def clean(text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return text.strip().rstrip("```").strip()

    try:
        return json.loads(clean(raw))
    except json.JSONDecodeError:
        retry_user = user + "\n\nIMPORTANT: Respond with a JSON object only. No prose, no fences."
        raw2 = llm_call(system_json, retry_user)
        return json.loads(clean(raw2))
