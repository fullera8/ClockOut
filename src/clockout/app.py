from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import AppConfig, load_config
from .messaging import MessagingClient
from .scheduler import Scheduler
from .state_machine import (
    CompletionStoreLike,
    MessagingClientLike,
    StateMachine,
)
from .storage import CompletionStore, default_state_path
from .ui import TrayApplication


def build_app(
    *,
    config_loader: Callable[[], AppConfig] | None = None,
    state_path_factory: Callable[[], Path] | None = None,
    store_factory: Callable[[Path], CompletionStoreLike] | None = None,
    messenger_factory: Callable[[str], MessagingClientLike] | None = None,
    state_machine_factory: Callable[
        [CompletionStoreLike, MessagingClientLike, datetime], StateMachine
    ]
    | None = None,
    scheduler_factory: Callable[[StateMachine], Scheduler] | None = None,
    application_factory: Callable[..., TrayApplication] | None = None,
    now_provider: Callable[[], datetime] | None = None,
    application_kwargs: Mapping[str, object] | None = None,
) -> TrayApplication:
    load = load_config if config_loader is None else config_loader
    state_path = default_state_path if state_path_factory is None else state_path_factory
    create_store = CompletionStore if store_factory is None else store_factory
    create_messenger = MessagingClient if messenger_factory is None else messenger_factory
    start_state_machine = (
        StateMachine.start
        if state_machine_factory is None
        else state_machine_factory
    )
    create_scheduler = Scheduler if scheduler_factory is None else scheduler_factory
    create_application = (
        TrayApplication if application_factory is None else application_factory
    )
    now = datetime.now if now_provider is None else now_provider

    config = load()
    store = create_store(state_path())
    messenger = create_messenger(config.webhook_url)
    state_machine = start_state_machine(store, messenger, now())
    scheduler = create_scheduler(state_machine)
    application_options: dict[str, Any] = (
        {} if application_kwargs is None else dict(application_kwargs)
    )
    return create_application(state_machine, scheduler, **application_options)


def main() -> None:
    build_app().run()


__all__ = ["build_app", "main"]