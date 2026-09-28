# ClockOut

ClockOut is a small Windows system-tray app that asks at 4:50 PM local time
on weekdays whether you will be home on time. Every answer posts a message to
a Microsoft Teams Workflows incoming webhook. The environment variable keeps
the legacy name `GCHAT_WEBHOOK_URL`.

## Install on Windows

Open PowerShell in this repository and create a virtual environment:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Copy the example configuration to the local, ignored file and edit it with the
Teams Workflows URL:

```powershell
Copy-Item .env.example .env
notepad .env
```

Set the value as follows. The URL must be the incoming webhook URL created by
Teams Workflows, despite the legacy variable name:

```text
GCHAT_WEBHOOK_URL=https://...
```

Never commit `.env`. It is git-ignored, and `.env.example` intentionally has
an empty value.

## Launch

With the virtual environment active, launch ClockOut with either command:

```powershell
python -m clockout
clockout
```

The process must remain running for the tray polling and prompt window to
work. ClockOut does not install a Windows service, scheduled task, or startup
registration.

To start it with Windows manually, create a shortcut in the Startup folder:

1. Press `Win+R`, enter `shell:startup`, and press Enter.
2. Create a shortcut whose target is the repository's
	`.venv\Scripts\python.exe` with the argument `-m clockout`.
3. Set the shortcut's "Start in" directory to the repository root.

This is manual shortcut guidance only; the application does not register
itself with Windows.

## Verification

Automated tests use fake stores and messengers and never send an HTTP request.
Live Teams delivery and the visible tray/window require manual verification by
a human. The test suite does not establish end-to-end success.
