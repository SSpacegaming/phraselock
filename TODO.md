# PhraseLock – Things to do

Tick a box when a feature is done (clickable on GitHub).

## 🔴 High priority

- [x] Background image not the right scale: add display options (fit, fill, stretch, center, tile)
- [x] Automatic save at every change, not only when clicking the Save button
- [ ] Display an icon in the hidden icons tray to show whether the software is running or not
- [ ] Add a panic hotkey or a "disable for X minutes" option that doesn't require the full challenge
- [ ] Add a crash-loop guard: if the app or the watchdog fails several times in a row, it disables itself automatically
- [ ] Add a `LICENSE` file to the repo

## 🟠 Medium priority

- [ ] Multi-screen support: select on which screen the lock is displayed
- [ ] Able to choose multiple pictures and display them randomly
- [ ] Able to put a GIF or video as the lock background
- [ ] Add default theme packs (TechDom, PetDom, Mommy/Daddy, Master/Mistress, Brat Tamer, FinDom, etc.)
- [ ] Add an import/export for settings and stats (backup, move to a new PC)
- [ ] Add a `requirements.txt` with pinned versions
- [ ] Add screenshots or a short GIF of the overlay to the README
- [ ] Add GitHub issue templates (Bug report, Feedback)
- [ ] Add more unit tests, especially for `phrases.py` (CSV, JSON and TXT parsing) and `config.py`
- [ ] Add an update checker that compares the installed version with the latest GitHub release

## 🟢 Low priority

- [ ] Add a bug report feature ("bug found")
- [ ] Add a feedback feature
- [ ] Add a repo description and topics (the About box is empty)
- [ ] Add a `CHANGELOG.md` and short release notes for each version
- [ ] Move the modules into a `phraselock/` package folder
- [ ] Add a language option for the interface and phrases
- [ ] Add a linter to the GitHub Actions workflow (for example ruff)
- [ ] Publish a SHA-256 checksum next to `PhraseLock.exe`, and eventually sign the exe to reduce the SmartScreen warning
