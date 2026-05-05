from openai import OpenAI

from src.config.settings import GROQ_API_KEY, GROQ_MODEL

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not set in .env")
    if _client is None:
        _client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
    return _client


def complete(prompt: str, max_tokens: int = 500, temperature: float = 0) -> str:
    """Send a prompt to Groq/Llama and return the response text."""
    client = get_client()
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()