from config.config import CONFIG
from loguru import logger


class LLMManager:
    _llm_instance = None

    @classmethod
    def get_llm(cls):
        """Returns a singleton LLM instance, using config settings."""
        if cls._llm_instance is None:
            llm_config = CONFIG.llm

            if llm_config.get("provider") == "openai":
                logger.info("Using OpenAI LLM provider")
                from langchain_openai import ChatOpenAI
                cls._llm_instance = ChatOpenAI(
                    temperature=llm_config.get("temperature", 0.7),
                    model_name=llm_config.get("model_name", "gpt-4o-mini"),
                    max_tokens=llm_config.get("max_tokens", 1000)
                )
            if llm_config.get("provider") == "groq":
                logger.info("Using Groq LLM provider")
                from langchain_groq import ChatGroq
                cls._llm_instance = ChatGroq(
                    model=llm_config.get("model", "llama3-70b-8192"),
                    temperature=llm_config.get("temperature", 0.7),
                    max_tokens=llm_config.get("max_tokens", 1000)
                )
        return cls._llm_instance
