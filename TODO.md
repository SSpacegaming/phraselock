# PhraseLock – Things to do

Tick a box when a feature is done (clickable on GitHub).

## 🔴 High priority

- [x] Background image not the right scale: add display options (fit, fill, stretch, center, tile)
- [x] Automatic save at every change, not only when clicking the Save button
- [x] Display an icon in the hidden icons tray to show whether the software is running or not
- [x] Add a panic hotkey or a "disable for X minutes" option that doesn't require the full challenge
- [ ] Add a crash-loop guard: if the app or the watchdog fails several times in a row, it disables itself automatically
- [x] Add a `LICENSE` file to the repo
- [ ] 🆕 Add a first-launch setup wizard to guide users through their initial configuration
- [ ] 🆕 Add a theme editor to create, rename, duplicate, and delete custom themes
- [ ] Add default theme packs (TechDom, PetDom, Mommy/Daddy, Master/Mistress, Brat Tamer, FinDom, etc.)
- [ ] 🆕 Add a "What's new?" window after updates
- [ ] 🆕 Add a clear uninstall and cleanup process

## 🟠 Medium priority

- [x] Multi-screen support: choose on which screen(s) the lock is displayed (one, several or all)
- [x] Able to choose multiple pictures and display them randomly
- [x] Choose the image display mode (fill, fit, stretch, center, tile) for each screen
- [x] Option to show a different random picture on each screen instead of the same one everywhere
- [x] Able to put a GIF as the lock background (animated)
- [ ] Able to put a video as the lock background
- [x] Add an import/export for settings and stats (backup, move to a new PC)
- [x] Add a `requirements.txt` with pinned versions
- [x] Add screenshots or a short GIF of the overlay to the README
- [x] Add GitHub issue templates (Bug report, Feedback)
- [ ] Add more unit tests, especially for `phrases.py` (CSV, JSON and TXT parsing) and `config.py`
- [ ] Add an update checker that compares the installed version with the latest GitHub release
- [ ] Add an exit option on the tray
- [ ] 🆕 Add text positioning controls (top, center, bottom, or custom position)
- [ ] 🆕 Add an optional progress bar showing how much of the phrase has been typed correctly
- [ ] 🆕 Add a choice between resetting the whole phrase or keeping the correctly typed portion after a mistake
- [ ] 🆕 Add multiple configuration profiles (Work, Gaming, Streaming, Sleep, etc.)
- [ ] 🆕 Add one-click profile switching from the system tray
- [ ] 🆕 Add a "Reset to defaults" button with a confirmation dialog
- [ ] 🆕 Add a local API or plugin system for third-party integrations (Discord integration?)

## 🟢 Low priority

- [ ] 🆕 Add drag-and-drop support for importing images, videos, audio, and phrase files
- [ ] 🆕 Add a schedule to activate specific profiles at certain times
- [ ] 🆕 Add a button to open the configuration folder
- [ ] 🆕 Add a button to open the current log file
- [ ] 🆕 Add keyboard shortcuts for common actions
- [ ] 🆕 Add a privacy section explaining what data PhraseLock stores locally
- [ ] Add a bug report feature ("bug found")
- [ ] Add a feedback feature
- [ ] Add a repo description and topics (the About box is empty)
- [x] Add a `CHANGELOG.md` and short release notes for each version
- [ ] Move the modules into a `phraselock/` package folder
- [ ] Add a language option for the interface and phrases
- [x] Add a linter to the GitHub Actions workflow (for example ruff)
- [ ] Publish a SHA-256 checksum next to `PhraseLock.exe`, and eventually sign the exe to reduce the SmartScreen warning
