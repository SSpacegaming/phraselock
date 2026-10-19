# Changelog

All notable changes to PhraseLock are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **Image display mode per screen.** Next to each monitor in the *Look* tab, an *Image
  mode* menu sets how the background fits that screen (Default, Fill, Fit, Stretch,
  Center, Tile). *Default* uses the global *Image display mode*.
- **Different picture on each screen.** New option *Show a different random picture on
  each screen*. Each locked screen gets its own random image when there are enough
  images (otherwise some are reused); when it is off, all screens show the same picture
  as before.
- New settings `screen_background_modes` and `background_per_screen`, with unit tests.
- **Several background images.** The *Look* tab now has a list of background images
  (*Add files...*, *Add URL...*, *Remove selected*, *Clear all*). One image is picked at
  random each time the lock appears, and never the same one twice in a row. Images that
  cannot be loaded are skipped. All locked screens show the same picture.
- New `background_images` setting. The older single `background_image` value is still
  used when the new key is missing, so existing configs keep working.
- Unit tests for the background list and the random pick (`tests/test_media.py`).
- **Multi-screen support.** The *Look* tab has a new "Show the lock on" section: tick
  one, several or all monitors ("All screens" also covers monitors plugged in later).
  The phrase panel appears on the primary screen (or on the left-most ticked screen if
  the primary is not ticked); the other ticked screens show the background image with
  no panel. Preview closes if you click a cover screen.
- New `lock_screens` setting (`"primary"` by default, so existing installs behave as
  before). The older single-value `lock_screen` key is still understood.
- New `monitors.py` module (monitor detection and selection) with unit tests.

### Fixed
- With a success sound enabled, the extra screens of a multi-screen lock are now hidden
  at the same moment as the main one instead of staying covered until the sound ends.

### Changed
- If a ticked monitor is unplugged it is skipped, and the primary screen is used when
  none of the ticked monitors is left. The saved choice is kept.
- The hidden standby lock rebuilds itself when the monitor layout changes.

## [1.0.2] - 2026-10-18

### Added
- `LICENSE` (MIT).
- `CHANGELOG.md` with the history of each version.
- Pinned `requirements.txt` (run from source) and `requirements-build.txt`
  (build the executable).
- GitHub issue templates (bug report, feedback).
- Screenshots of the lock overlay and the settings window in the README.

### Changed
- The GitHub Actions build now installs the pinned requirements and uses the same
  PyInstaller options as `bat.bat`: it bundles `pystray`, the tray modules and the
  application icons, so executables built by the workflow include the system tray
  icon and the window icon.
- `bat.bat` installs `requirements-build.txt`.
- README updated (license, running from source, project structure, links to the
  issue templates and the changelog) and `TODO.md` updated.

## [1.0.1] - 2026-10-18

### Added
- **System tray icon.** PhraseLock shows its own icon in the Windows notification
  area (including the hidden icons overflow) while it is running. A small badge
  shows the state: no badge when active, yellow when outside the schedule, grey
  when disabled.
- **Tray menu.** Double-click the icon (or right-click, *Open settings*) to open
  the settings window.
- **Application icon.** The settings window and its dialogs use the PhraseLock
  icon instead of the default Tk feather.
- **Automatic save.** Settings are saved at every change, not only when clicking
  the Save button.
- **Background image scaling.** Display options for the lock background image
  (fit, fill, stretch, center, tile).

### Fixed
- The success sound did not play correctly when completing the lock challenge.
- A bug when opening several previews at once.
- Opening the settings from the tray created duplicate windows. If the settings
  are already open, nothing new is launched and a notification is shown.
- *"Failed to start embedded python interpreter!"* when opening the settings from
  the tray icon.
- *"Failed to remove temporary directory"* warning when closing the app: every
  relaunched PhraseLock process now extracts its own temporary folder.

### Changed
- Logging cleanup.
- Added a `TODO.md` roadmap, new modules `tray.py` and `appicon.py`; `bat.bat`
  installs `pystray` and bundles `icon.ico` / `icon.png` into the executable.

## [1.0.0] - 2026-10-17

### Added
- First public release: customizable typing challenge on Windows unlock, phrase
  libraries (TXT, CSV, JSON), themes and visual customization, progress tracking
  (streaks, daily goals, XP, levels, badges), emergency recovery password and a
  Windows executable.

[Unreleased]: https://github.com/nanana677777/phraselock/compare/v1.0.2...HEAD
[1.0.2]: https://github.com/nanana677777/phraselock/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/nanana677777/phraselock/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/nanana677777/phraselock/releases/tag/v1.0.0
