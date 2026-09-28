import logging
from pathlib import Path

import pytest

from clockout.config import AppConfig, ConfigurationError, load_config


def test_load_config_reads_explicit_environment_without_mutating_it(tmp_path: Path) -> None:
    env = {"GCHAT_WEBHOOK_URL": " https://example.invalid/from-env "}

    config = load_config(env=env, dotenv_path=tmp_path / "missing.env")

    assert config == AppConfig(webhook_url="https://example.invalid/from-env")
    assert env["GCHAT_WEBHOOK_URL"] == " https://example.invalid/from-env "
    assert not (tmp_path / "missing.env").exists()


def test_load_config_reads_dotenv_when_environment_does_not_define_value(
    tmp_path: Path,
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "GCHAT_WEBHOOK_URL=https://example.invalid/from-dotenv\n",
        encoding="utf-8",
    )

    config = load_config(env={}, dotenv_path=dotenv_path)

    assert config.webhook_url == "https://example.invalid/from-dotenv"


def test_environment_value_takes_precedence_over_dotenv(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "GCHAT_WEBHOOK_URL=https://example.invalid/from-dotenv\n",
        encoding="utf-8",
    )

    config = load_config(
        env={"GCHAT_WEBHOOK_URL": "https://example.invalid/from-env"},
        dotenv_path=dotenv_path,
    )

    assert config.webhook_url == "https://example.invalid/from-env"


@pytest.mark.parametrize(
    "env, dotenv_contents",
    [
        ({}, None),
        ({"GCHAT_WEBHOOK_URL": ""}, "GCHAT_WEBHOOK_URL=https://example.invalid/file\n"),
        ({"GCHAT_WEBHOOK_URL": "   "}, "GCHAT_WEBHOOK_URL=https://example.invalid/file\n"),
        ({}, "GCHAT_WEBHOOK_URL=   \n"),
    ],
)
def test_missing_or_blank_webhook_raises_sanitized_error(
    tmp_path: Path,
    env: dict[str, str],
    dotenv_contents: str | None,
) -> None:
    dotenv_path = tmp_path / ".env"
    if dotenv_contents is not None:
        dotenv_path.write_text(dotenv_contents, encoding="utf-8")

    with pytest.raises(ConfigurationError) as error:
        load_config(env=env, dotenv_path=dotenv_path)

    assert str(error.value) == "GCHAT_WEBHOOK_URL must be set"
    assert "example.invalid" not in str(error.value)


def test_app_config_repr_does_not_reveal_webhook() -> None:
    config = AppConfig(webhook_url="https://example.invalid/secret")

    assert "example.invalid" not in repr(config)

def test_repository_secret_scaffolding_is_exact() -> None:
    repository_root = Path(__file__).parents[1]

    assert (repository_root / ".gitignore").read_bytes().splitlines()[0] == b".env"
    assert (repository_root / ".env.example").read_bytes() == b"GCHAT_WEBHOOK_URL="
    assert not (repository_root / ".env").exists()

def test_webhook_does_not_appear_in_string_or_logging(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    webhook = "https://example.invalid/secret"

    with caplog.at_level(logging.DEBUG):
        config = load_config(
            env={"GCHAT_WEBHOOK_URL": webhook},
            dotenv_path=tmp_path / "missing.env",
        )

    assert webhook not in str(config)
    assert webhook not in repr(config)
    assert webhook not in caplog.text
