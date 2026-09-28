from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values


WEBHOOK_ENV_VAR = "GCHAT_WEBHOOK_URL"


class ConfigurationError(RuntimeError):
    """Raised when required application configuration is unavailable."""


@dataclass(frozen=True, slots=True)
class AppConfig:
    webhook_url: str = field(repr=False)


def load_config(
    env: Mapping[str, str] | None = None,
    dotenv_path: Path | None = None,
) -> AppConfig:
    """Load the webhook configuration without mutating the process environment."""
    environment = os.environ if env is None else env
    file_values = dotenv_values(dotenv_path or Path(".env"))

    if WEBHOOK_ENV_VAR in environment:
        raw_webhook_url = environment[WEBHOOK_ENV_VAR]
    else:
        raw_webhook_url = file_values.get(WEBHOOK_ENV_VAR)

    if not isinstance(raw_webhook_url, str) or not raw_webhook_url.strip():
        raise ConfigurationError(f"{WEBHOOK_ENV_VAR} must be set")

    return AppConfig(webhook_url=raw_webhook_url.strip())