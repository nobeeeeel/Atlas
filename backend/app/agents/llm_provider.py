from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class LlmProviderError(RuntimeError):
    pass


class _InvalidStructuredOutput(ValueError):
    """A model answered, but its response was not the requested JSON object."""


class LlmProvider(Protocol):
    def complete(self, *, system_prompt: str, user_prompt: str) -> str: ...


def _enabled(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


SUPPORTED_GOOGLE_MODELS = {
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemma-4-26b-a4b-it",
    "gemma-4-31b-it",
}


RETRYABLE_GOOGLE_HTTP_CODES = {
    408,
    429,
    500,
    502,
    503,
    504,
}


MODEL_FALLBACK_GOOGLE_HTTP_CODES = {
    400,
    404,
}


def _model_list(raw: str) -> tuple[str, ...]:
    return tuple(
        model
        for model in (item.strip() for item in raw.split(","))
        if model
    )


@dataclass(frozen=True)
class LocalLlmSettings:
    enabled: bool
    base_url: str
    model: str
    timeout_seconds: float
    allow_remote: bool

    @classmethod
    def from_environment(cls) -> "LocalLlmSettings":
        return cls(
            enabled=_enabled("ATLAS_LLM_ENABLED"),
            base_url=os.getenv(
                "ATLAS_LLM_BASE_URL",
                "http://127.0.0.1:11434/v1",
            ).rstrip("/"),
            model=os.getenv("ATLAS_LLM_MODEL", "").strip(),
            timeout_seconds=float(
                os.getenv("ATLAS_LLM_TIMEOUT_SECONDS", "90")
            ),
            allow_remote=_enabled("ATLAS_LLM_ALLOW_REMOTE"),
        )

    def public_status(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "provider": "OPENAI_COMPATIBLE_LOCAL",
            "base_url": self.base_url,
            "model": self.model or None,
            "allow_remote": self.allow_remote,
            "execution_authority": "NONE",
        }


class OpenAiCompatibleLocalProvider:
    def __init__(self, settings: LocalLlmSettings):
        self.settings = settings

        if not settings.enabled:
            raise LlmProviderError("Local LLM support is disabled.")

        if not settings.model:
            raise LlmProviderError("ATLAS_LLM_MODEL must be configured.")

        parsed = urlparse(settings.base_url)

        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise LlmProviderError("ATLAS_LLM_BASE_URL is invalid.")

        local_hosts = {
            "127.0.0.1",
            "localhost",
            "::1",
        }

        if parsed.hostname not in local_hosts and not settings.allow_remote:
            raise LlmProviderError(
                "Remote LLM endpoints are blocked. "
                "Use a loopback URL or explicitly set "
                "ATLAS_LLM_ALLOW_REMOTE=true."
            )

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        payload = json.dumps(
            {
                "model": self.settings.model,
                "temperature": 0.1,
                "response_format": {
                    "type": "json_object",
                },
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": user_prompt,
                    },
                ],
            }
        ).encode("utf-8")

        request = Request(
            f"{self.settings.base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(
                request,
                timeout=self.settings.timeout_seconds,
            ) as response:
                body = json.loads(
                    response.read().decode("utf-8")
                )

            return str(
                body["choices"][0]["message"]["content"]
            )

        except Exception as exc:
            raise LlmProviderError(
                f"Local LLM request failed: {exc}"
            ) from exc


@dataclass(frozen=True)
class GeminiGemmaSettings:
    enabled: bool
    api_key: str
    model: str
    fallback_models: tuple[str, ...]
    timeout_seconds: float
    thinking_level: str

    @classmethod
    def from_environment(cls) -> "GeminiGemmaSettings":
        return cls(
            enabled=_enabled("ATLAS_LLM_ENABLED"),
            api_key=(
                os.getenv("GEMINI_API_KEY", "").strip()
                or os.getenv("GOOGLE_API_KEY", "").strip()
            ),
            model=os.getenv(
                "ATLAS_LLM_MODEL",
                "gemini-3.6-flash",
            ).strip(),
            fallback_models=_model_list(
                os.getenv(
                    "ATLAS_LLM_FALLBACK_MODELS",
                    "gemini-3.5-flash,gemini-3.5-flash-lite",
                )
            ),
            timeout_seconds=float(
                os.getenv(
                    "ATLAS_LLM_TIMEOUT_SECONDS",
                    "300",
                )
            ),
            thinking_level=os.getenv(
                "ATLAS_GEMMA_THINKING_LEVEL",
                "high",
            ).strip().lower(),
        )

    def public_status(self) -> dict[str, object]:
        model_chain = list(
            dict.fromkeys(
                (
                    self.model,
                    *self.fallback_models,
                )
            )
        )

        return {
            "enabled": self.enabled,
            "provider": "GOOGLE_GEMINI_API",
            "model": self.model,
            "fallback_models": model_chain[1:],
            "model_chain": model_chain,
            "fallback_enabled": len(model_chain) > 1,
            "api_key_configured": bool(self.api_key),
            "thinking_level": self.thinking_level,
            "execution_authority": "PROPOSAL_ONLY",
        }


class GeminiGemmaProvider:
    API_ROOT = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models"
    )

    def __init__(
        self,
        settings: GeminiGemmaSettings,
    ):
        self.settings = settings
        self._unavailable_models: set[str] = set()
        self.last_model_used: str | None = None

        if not settings.enabled:
            raise LlmProviderError(
                "Google Gemini support is disabled."
            )

        if not settings.api_key:
            raise LlmProviderError(
                "GEMINI_API_KEY (or GOOGLE_API_KEY) "
                "must be configured."
            )

        self.model_chain = tuple(
            dict.fromkeys(
                (
                    settings.model,
                    *settings.fallback_models,
                )
            )
        )

        unsupported = [
            model
            for model in self.model_chain
            if model not in SUPPORTED_GOOGLE_MODELS
        ]

        if unsupported:
            raise LlmProviderError(
                "Unsupported Google model(s) "
                "in Atlas model chain: "
                + ", ".join(unsupported)
            )

        if settings.thinking_level not in {
            "high",
            "medium",
            "low",
            "minimal",
        }:
            raise LlmProviderError(
                "ATLAS_GEMMA_THINKING_LEVEL must be "
                "high, medium, low, or minimal."
            )

    @staticmethod
    def _required_output_schema(
        user_prompt: str,
    ) -> dict[str, object] | None:
        """
        Recover the Pydantic JSON Schema embedded by Atlas's prompt.

        The schema remains useful for local validation and downstream
        Atlas/Pydantic validation.

        It is intentionally NOT sent to Gemini directly in this version,
        because Gemini structured output only supports a subset of JSON
        Schema and Atlas's full schema can be too large/deep for the API.
        """
        try:
            prompt = json.loads(user_prompt)
        except (TypeError, json.JSONDecodeError):
            return None

        if not isinstance(prompt, dict):
            return None

        schema = prompt.get("required_output_schema")

        if isinstance(schema, dict):
            return schema

        return None

    @staticmethod
    def _supports_thinking_level(
        model: str,
    ) -> bool:
        return model.startswith("gemini-3")

    def _generation_config(
        self,
        model: str,
        response_schema: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """
        Build the Gemini GenerateContent configuration.

        IMPORTANT:
        Atlas requests JSON mode only here.

        We deliberately DO NOT send responseJsonSchema to Google.
        Atlas's Pydantic schema is still embedded in the user prompt and
        is validated by Atlas after generation.

        This avoids Gemini rejecting Atlas's large/deep schema with
        HTTP 400 INVALID_ARGUMENT.
        """
        generation_config: dict[str, object] = {
            "maxOutputTokens": (
                32768
                if model.startswith("gemini-3")
                else 8192
            ),
            "responseMimeType": "application/json",
        }

        if self._supports_thinking_level(model):
            generation_config["thinkingConfig"] = {
                "thinkingLevel": self.settings.thinking_level,
            }

        if not model.startswith("gemini-3"):
            generation_config.update(
                {
                    "temperature": 0.2,
                    "topP": 0.95,
                    "topK": 64,
                }
            )

        return generation_config

    def _request_for_model(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object] | None = None,
    ) -> Request:
        payload = json.dumps(
            {
                "system_instruction": {
                    "parts": [
                        {
                            "text": system_prompt,
                        }
                    ],
                },
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": user_prompt,
                            }
                        ],
                    }
                ],
                "generationConfig": self._generation_config(
                    model,
                    response_schema,
                ),
            }
        ).encode("utf-8")

        return Request(
            f"{self.API_ROOT}/{model}:generateContent",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.settings.api_key,
            },
            method="POST",
        )

    @staticmethod
    def _read_http_error_detail(
        exc: HTTPError,
    ) -> str:
        try:
            return exc.read().decode("utf-8")[:4000]
        except Exception:
            return ""

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        failures: list[str] = []

        response_schema = self._required_output_schema(
            user_prompt
        )

        available_chain = tuple(
            model
            for model in self.model_chain
            if model not in self._unavailable_models
        )

        if not available_chain:
            available_chain = self.model_chain

        for index, model in enumerate(available_chain):
            request = self._request_for_model(
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_schema=response_schema,
            )

            try:
                with urlopen(
                    request,
                    timeout=self.settings.timeout_seconds,
                ) as response:
                    body = json.loads(
                        response.read().decode("utf-8")
                    )

                candidates = body.get("candidates")

                if not isinstance(candidates, list) or not candidates:
                    raise ValueError(
                        "Google model returned no candidates."
                    )

                content = candidates[0].get("content")

                if not isinstance(content, dict):
                    raise ValueError(
                        "Google model returned no candidate content."
                    )

                parts = content.get("parts")

                if not isinstance(parts, list):
                    raise ValueError(
                        "Google model returned no content parts."
                    )

                text_parts = [
                    str(part["text"])
                    for part in parts
                    if (
                        isinstance(part, dict)
                        and part.get("text")
                        and not part.get("thought")
                    )
                ]

                if not text_parts:
                    raise ValueError(
                        "Google model returned no final text content."
                    )

                result = "\n".join(
                    text_parts
                ).strip()

                #
                # Provider boundary validation.
                #
                # Gemini is asked for JSON mode, but Atlas never trusts
                # that blindly.
                #
                # We still require valid JSON here.
                #
                # Full Pydantic and semantic validation remains in the
                # Atlas Analyst/Critic workflow downstream.
                #
                if response_schema:
                    try:
                        parsed_result = json.loads(
                            result
                        )
                    except json.JSONDecodeError as exc:
                        raise _InvalidStructuredOutput(
                            "invalid JSON at "
                            f"line {exc.lineno} "
                            f"column {exc.colno}: "
                            f"{exc.msg}"
                        ) from exc

                    if not isinstance(
                        parsed_result,
                        dict,
                    ):
                        raise _InvalidStructuredOutput(
                            "structured response must "
                            "be a JSON object"
                        )

                self.last_model_used = model

                return result

            except HTTPError as exc:
                detail = self._read_http_error_detail(
                    exc
                )

                can_fallback = (
                    exc.code
                    in RETRYABLE_GOOGLE_HTTP_CODES
                    or exc.code
                    in MODEL_FALLBACK_GOOGLE_HTTP_CODES
                )

                reason = (
                    f"{model}: "
                    f"HTTP {exc.code} {exc.reason}"
                )

                if detail:
                    reason += (
                        f"; response={detail[:600]}"
                    )

                failures.append(reason)

                #
                # Only 404 permanently suppresses a model.
                #
                # 400 may be request/model compatibility.
                # 429 is temporary quota/rate limiting.
                #
                if exc.code == 404:
                    self._unavailable_models.add(
                        model
                    )

                if (
                    can_fallback
                    and index
                    < len(available_chain) - 1
                ):
                    continue

                raise LlmProviderError(
                    "Gemini model chain failed: "
                    + " | ".join(failures)
                ) from exc

            except _InvalidStructuredOutput as exc:
                failures.append(
                    f"{model}: {exc}"
                )

                if (
                    index
                    < len(available_chain) - 1
                ):
                    continue

                raise LlmProviderError(
                    "Gemini model chain returned "
                    "invalid structured output: "
                    + " | ".join(failures)
                ) from exc

            except Exception as exc:
                failures.append(
                    f"{model}: {exc}"
                )

                if (
                    index
                    < len(available_chain) - 1
                ):
                    continue

                raise LlmProviderError(
                    "Gemini model chain failed: "
                    + " | ".join(failures)
                ) from exc

        raise LlmProviderError(
            "Gemini model chain exhausted "
            "without a response."
        )


def configured_llm_status() -> dict[str, object]:
    provider_name = os.getenv(
        "ATLAS_LLM_PROVIDER",
        "GEMINI",
    ).strip().upper()

    if provider_name in {
        "GEMINI",
        "GEMINI_FLASH",
        "GEMINI_GEMMA",
    }:
        return (
            GeminiGemmaSettings
            .from_environment()
            .public_status()
        )

    if provider_name == "OPENAI_COMPATIBLE_LOCAL":
        return (
            LocalLlmSettings
            .from_environment()
            .public_status()
        )

    return {
        "enabled": False,
        "provider": provider_name,
        "configuration_error": (
            "Unsupported ATLAS_LLM_PROVIDER."
        ),
        "execution_authority": "NONE",
    }


def build_configured_provider() -> LlmProvider:
    provider_name = os.getenv(
        "ATLAS_LLM_PROVIDER",
        "GEMINI",
    ).strip().upper()

    if provider_name in {
        "GEMINI",
        "GEMINI_FLASH",
        "GEMINI_GEMMA",
    }:
        return GeminiGemmaProvider(
            GeminiGemmaSettings.from_environment()
        )

    if provider_name == "OPENAI_COMPATIBLE_LOCAL":
        return OpenAiCompatibleLocalProvider(
            LocalLlmSettings.from_environment()
        )

    raise LlmProviderError(
        "Unsupported ATLAS_LLM_PROVIDER: "
        f"{provider_name}"
    )