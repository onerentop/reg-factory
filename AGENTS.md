# Repository Instructions

## Product scope

- RegFactory is a local Outlook and Google registration console.
- The FastAPI modular monolith lives in `services/`; `frontend/` is its Vite/React UI.
- The console supports Outlook, Google, SMS providers, proxy management, task-event logs, account results and Outlook Graph token extraction. Do not reintroduce Claude, ChatGPT, Grok, Codex, Plus activation, token upload, orchestration, alerting, audit or scheduling features.
- Root registration implementations are `register_outlook_standalone.py`, `register_gmail_hybrid.py`, and `register_gmail_protocol.py`. The worker imports them through `services/worker/legacy_bridge.py`.
- `gmail_android/` is a separate local Appium/BlueStacks Google path. It intentionally stops at phone/security verification unless an operator resumes it and accepts terms.

## Environment

- Root automation uses Python 3.10+ from `requirements.txt`.
- `services/` needs Python 3.11+ and is installed from `services/pyproject.toml`.
- `frontend/` uses npm and `package-lock.json`.
- Root `.env` provides browser, proxy, captcha, Gmail SMS and Android settings. Process environment wins.
- `BROWSER_PROVIDER=ixbrowser` is the default (local client API on `127.0.0.1:53200`). Set `BROWSER_PROVIDER=donut` to use DonutBrowser instead (defaults to `127.0.0.1:10108`).

## Commands

- Focused service test: `python -m pytest tests/gateway/test_registration_routes.py -q` from `services/`.
- Focused frontend test: `npm run test -- src/pages/AccountsPage.test.tsx` from `frontend/`.
- Start full local application: `./scripts/start_all.ps1`. It builds frontend and runs migrations, so do not use it just for unit testing.
- API runs on 8000; Vite development runs on 3000 and proxies `/api` / `/ws`.

## Safety and testing

- Keep task status/event persistence and task-log WebSocket intact when editing registration flow.
- Registration, proxy tests, SMS number acquisition, captcha solving and browser profile launches have external effects. Never run them without explicit authorization.
- Do not commit `.env`, account pools, tokens, cookies, screenshots, logs or release zip artifacts.
- Existing uncommitted monolith/Donut work is intentional. Do not run `git clean`, restore deleted legacy features, or remove runtime data directories.
