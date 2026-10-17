# 🔒 PhraseLock

**Turn unlocking your Windows PC into a customizable typing challenge.**

PhraseLock is a Windows application that asks you to type configured phrases as part of a personal discipline, focus, or self-imposed challenge routine.

Customize your phrases, choose a visual theme, track your progress, and make each unlock challenge your own.

> **⚠️ Important:** PhraseLock is a personal challenge tool, not a security product. It is not designed to protect sensitive files or replace Windows security. Test it carefully before enabling any automatic protection.

## ✨ Features

- **Custom typing challenges** — use your own phrases and challenge styles.
- **Techdom-inspired phrase pack** — add a little personality to your routine.
- **Customizable settings** — configure the experience to suit your preferences.
- **Progress tracking** — features in the source include streaks, daily goals, XP, levels, and badges.
- **Phrase libraries** — support for external TXT, CSV, and JSON phrase collections.
- **Visual customization** — themes, backgrounds, interface scaling, and visual effects are available in the project.
- **Emergency recovery** — configure an emergency password before using protection features.
- **System tray icon** — see at a glance that PhraseLock is running; open the settings from the tray.
- **Windows executable** — get started without manually running the Python source code.

Feature availability may depend on the version and configuration you are running.

## 📸 Screenshots

Uncomment this section once the images exist (see TODO.md).

![Lock overlay](docs/screenshots/overlay.png)
![Settings](docs/screenshots/settings.png)

## 📥 Installation

### Option 1: Download the release

1. Open the [PhraseLock Releases page](https://github.com/nanana677777/phraselock/releases).
2. Select the latest release (see the [changelog](CHANGELOG.md) for what changed).
3. Download `PhraseLock.exe` from the release assets.
4. Save it somewhere convenient, such as a dedicated `PhraseLock` folder.
5. Run the executable and configure your preferences.

**Tip:** Keep a copy of your downloaded executable in a safe location so you can recover or reinstall it if needed.

### Windows SmartScreen warning

Windows may display a warning when launching an executable that is not code-signed. This warning does not, by itself, prove that a file is malicious or safe.

Only run the executable if you trust its source. You can also inspect the source code or build the project yourself before running it.

## ⚙️ Getting started

1. Launch PhraseLock.
2. Open the settings interface and configure your phrases.
3. Set an emergency password and verify that your recovery method works.
4. Review the available protection and challenge settings.
5. Test the challenge manually before enabling automatic behavior.
6. Enable only the features you understand and want to use.

**Always test the emergency recovery procedure before enabling strict or automatic protection.** Keep an alternative way to access your Windows account available.

## 📝 Custom phrase libraries

PhraseLock supports external phrase collections in TXT, CSV, and JSON formats.

The documented CSV format uses these columns:

```csv
phrase,category,difficulty
Type this phrase,General,easy
Complete your challenge,Focus,normal
```

The documented JSON format uses objects like this:

```json
[
  {
    "phrase": "Type this phrase",
    "category": "General",
    "difficulty": "easy"
  }
]
```

For TXT files, use the format expected by the phrase loader in the source code. If a file fails to load, check the examples and parsing logic in [`phrases.py`](phrases.py).

## 🛡️ Safety and recovery

PhraseLock can interact with Windows session locking and optional automatic protection. Misconfiguration or unexpected behavior could interrupt your normal workflow.

Before enabling protection:

- Set and test your emergency password.
- Test the application in preview mode where available.
- Keep access to your Windows account and another recovery method.
- Understand how to disable automatic protection.
- Avoid relying on PhraseLock as your only way to control access to your computer.

If PhraseLock behaves unexpectedly, use the recovery instructions in the source code and configuration documentation. Do not enable automatic restart or strict protection until you have confirmed that you can recover safely.

## 🧰 Build from source

Want to inspect the code or build your own executable?

### Requirements

- Windows
- Python 3.12 (the version used by the GitHub Actions build)
- Git (optional, for cloning the repository)
- The pinned dependencies listed in [`requirements.txt`](requirements.txt) (run from source) or [`requirements-build.txt`](requirements-build.txt) (build the executable)

### Get the source

```bash
git clone https://github.com/nanana677777/phraselock.git
cd phraselock
```

To run from source, install the dependencies and start the app:

```bash
python -m pip install -r requirements.txt
python phrase_lock.py
```

To build the executable, run [`bat.bat`](bat.bat) (it installs `requirements-build.txt` for you) or follow the GitHub Actions workflow in [`.github/workflows/build.yml`](.github/workflows/build.yml).

The automated workflow runs the unit tests and builds a Windows executable.

### Run the tests

```bash
python -m unittest discover -s tests -v
```

Running the tests before building helps identify problems in the project's tested logic. Passing tests do not guarantee that every Windows feature works correctly on every system.

## 📂 Project structure

| File or folder          | Purpose                              |
| ----------------------- | ------------------------------------ |
| `phrase_lock.py`        | Main application entry point         |
| `settings.py`           | Settings interface                   |
| `config.py`             | Configuration and defaults           |
| `phrases.py`            | Phrase library loading and selection |
| `stats.py`              | Progress and statistics              |
| `session.py`            | Session and protection logic         |
| `overlay.py`            | Challenge overlay                    |
| `media.py`              | Media and audio functionality        |
| `PhraseLockWatchdog.py` | Optional watchdog functionality      |
| `tray.py`               | System tray status icon              |
| `appicon.py`            | Shared application icon helpers      |
| `tests/`                | Unit tests                           |
| `phrases.csv`           | CSV phrase collection                |
| `phrases.json`          | JSON phrase collection               |
| `phrases.txt`           | Text phrase collection               |
| `icon.ico`, `icon.png`  | Application icon                     |
| `requirements*.txt`     | Pinned dependencies (run / build)    |
| `CHANGELOG.md`          | Version history                      |
| `LICENSE`               | MIT license                          |

## 🐛 Troubleshooting

**PhraseLock does not start**

- Check whether Windows or your antivirus has blocked the executable.
- Download a fresh copy from the official [Releases page](https://github.com/nanana677777/phraselock/releases).
- If the problem persists, open a GitHub issue with your Windows version and the error message.

**My phrase library does not load**

- Check the file format and required fields.
- Compare your file with the expected format in `phrases.py`.
- Try a small test file before importing a larger collection.

**I am worried about being locked out**

- Do not enable automatic or strict protection until recovery has been tested.
- Keep an alternative way to access your Windows account.
- If you cannot recover normally, use the project's documented recovery procedure rather than repeatedly restarting the application.

## 🤝 Contributing and bug reports

PhraseLock is an evolving project, and feedback is welcome.

- **Report a bug or give feedback:** [Open an issue](https://github.com/nanana677777/phraselock/issues/new/choose) and pick a template.
- **Browse the code:** [View the repository](https://github.com/nanana677777/phraselock).
- **Download updates:** [View releases](https://github.com/nanana677777/phraselock/releases).

When reporting a bug, include the PhraseLock version, your Windows version, the steps to reproduce the problem, and any relevant error messages. Do not include passwords or other sensitive information.

## 📜 License

PhraseLock is released under the [MIT License](LICENSE).

---

**PhraseLock v1.0.2** · See the [changelog](CHANGELOG.md)

Made for customizable challenges, personal discipline, and focus.
