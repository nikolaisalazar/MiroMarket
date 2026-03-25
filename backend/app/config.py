from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Database
    DATABASE_URL: str

    # LLM model selection (LiteLLM format: "provider/model-name")
    # Swap these freely without touching any other code.
    # Examples:
    #   "openai/gpt-4o-mini"
    #   "anthropic/claude-haiku-3-5"
    #   "together_ai/Qwen/Qwen2.5-72B-Instruct"
    #   "groq/llama-3.1-70b-versatile"
    #   "ollama/llama3.2"  (local, free)
    AGENT_MODEL: str = "openai/gpt-4o-mini"
    REPORT_MODEL: str = "openai/gpt-4o"

    # LLM API keys — only needed for providers you actually use
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    TOGETHER_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    GROQ_API_KEY: str = ""

    # Kalshi
    KALSHI_API_KEY: str = ""
    KALSHI_BASE_URL: str = "https://trading-api.kalshi.com/trade-api/v2"


settings = Settings()
