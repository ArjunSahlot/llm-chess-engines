from __future__ import annotations


PROVIDER_DEFAULTS = {
    "openai": ("OPENAI_API_KEY", None),
    "anthropic": ("ANTHROPIC_API_KEY", None),
    "gemini": ("GEMINI_API_KEY", None),
    "deepseek": ("DEEPSEEK_API_KEY", "https://api.deepseek.com"),
    "kimi": ("MOONSHOT_API_KEY", "https://api.moonshot.ai/v1"),
    "moonshot": ("MOONSHOT_API_KEY", "https://api.moonshot.ai/v1"),
}


def provider_defaults(provider: str) -> tuple[str, str | None]:
    return PROVIDER_DEFAULTS.get(provider.lower(), (f"{provider.upper()}_API_KEY", None))
