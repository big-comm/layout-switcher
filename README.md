<h1 align="center">Community Layout Switcher</h1>

<p align="center">
A GTK4 + libadwaita application for switching GNOME desktop layouts, managing shell extensions, fonts, visual effects, and themes.
</p>

<p align="center">
  <img alt="License"    src="https://img.shields.io/badge/License-MIT-green.svg">
  <img alt="Platform"   src="https://img.shields.io/badge/Platform-Linux-informational.svg">
  <img alt="Python"     src="https://img.shields.io/badge/Python-3.10%2B-3776ab.svg?logo=python&logoColor=white">
  <img alt="GTK"        src="https://img.shields.io/badge/GTK-4.0-4a86cf.svg">
  <img alt="Libadwaita" src="https://img.shields.io/badge/libadwaita-1.x-3584e4.svg">
  <img alt="GNOME"      src="https://img.shields.io/badge/GNOME-45%2B-4a86cf.svg?logo=gnome&logoColor=white">
  <img alt="Tests"      src="https://img.shields.io/badge/tests-102%20passing-success.svg">
  <img alt="i18n"       src="https://img.shields.io/badge/i18n-28%20languages-blueviolet.svg">
</p>

---

## Overview

Community Layout Switcher is the appearance-management tool for [BigCommunity Linux](https://communitybig.org). It lets users reshape the GNOME desktop — panels, docks, extensions, fonts and themes — without editing dconf or logging out, while staying compatible with the distribution's `comm-gnome-config` sync services.

## Features

- **Layouts** — Apply curated desktop layouts (BigGnome, Classic, Hybrid, G-Unity, Minimal, Modern) with one click. Automatic pre-apply backup; per-layout user snapshots with a Plasma-style *Resume your changes* or *Apply original* prompt when revisiting a customized layout.
- **Fonts** — Interface / document / monospace / legacy title selectors via `Gtk.FontDialog`, plus hinting and antialiasing controls, a searchable list of installed families with live previews, and quick access to Google Fonts.
- **Themes** — GTK, icon and shell themes with real previews (actual `folder` icon from each icon theme; accent color parsed from each theme's CSS), search filter and one-click apply.
- **Effects** — Dedicated page for visual extensions (Desktop Cube, Magic Lamp, Compiz Windows, Desktop Icons NG). Installs prefer `pacman` for stability and fall back to extensions.gnome.org.
- **Extensions** — Compact view of installed extensions with toggle, remove and a shortcut to GNOME Extensions manager.
- **Backups** — Every apply creates a timestamped dconf dump. A dedicated dialog lists all backups with restore/delete and a manual-snapshot button.
- **Sync-aware** — Cooperates with the `dconf-sync-gnome.service` from `comm-gnome-config`: the monitor is paused around each apply, user extensions are suspended to avoid transient error states, and the final state is persisted atomically to `~/.config/dconf/settings.gnome`.

## Screenshots

> Screenshots go in `docs/screenshots/` and are referenced here.

## Requirements

- GNOME Shell **45+**
- Python **3.10+**
- PyGObject bindings for **GTK 4** and **libadwaita 1**
- `dconf`, `gsettings`, `gnome-extensions` (standard on GNOME systems)

## Installation

### Arch Linux / BigCommunity

```sh
sudo pacman -S layout-switcher
```

### Build from source (Arch)

```sh
git clone https://github.com/big-comm/layout-switcher.git
cd layout-switcher/pkgbuild
makepkg -si
```

### Manual install (any distro with GTK 4 + libadwaita)

```sh
git clone https://github.com/big-comm/layout-switcher.git
cd layout-switcher
sudo cp -r usr/ /
```

## Usage

Launch from the application grid or run `layout-switcher` from a terminal. The sidebar exposes the five sections:

```
Layouts   Fonts   Themes   Effects   Extensions
```

The hamburger menu gives access to **Backups…** (restore or snapshot the dconf state) and **About**.

## Development

```sh
# run from the checkout without installing
python usr/share/layout-switcher/main.py

# lint + format
ruff check .
ruff format .

# tests (102 unit tests, no display required)
python -m pytest tests/ -q
```

### Project layout

```
usr/share/layout-switcher/
├── main.py                          # Adw.Application entry point
├── constants.py                     # APP_ID, LAYOUTS, i18n setup
├── utils.py                         # subprocess + gsettings helpers
├── backup_manager.py                # timestamped dconf dumps
├── snapshot_manager.py              # per-layout user snapshots
├── layout_applier.py                # atomic apply orchestration
├── extension_manager.py             # install / toggle / remove
├── shell_reloader.py                # D-Bus cascade reload (no logout)
├── theme_manager.py                 # GTK / icons / shell theme apply
├── theme_preview.py                 # folder icon + CSS color extraction
├── settings_store.py                # JSON settings + GSettings watcher
└── ui/
    ├── window.py                    # main window, sidebar, menu
    ├── page_layouts.py              # layout grid with Resume/Original
    ├── page_fonts.py                # font selectors + installed list
    ├── page_themes.py               # GTK / icons / shell with previews
    ├── page_effects.py              # featured visual extensions
    ├── page_extensions.py           # installed extensions list
    ├── dialog_backups.py            # backup management dialog
    ├── widgets.py                   # shared custom widgets
    └── styles.py                    # APP_CSS

usr/share/locale/                    # .po sources + compiled .mo (28 languages)
tests/                               # pytest unit tests
pkgbuild/                            # Arch PKGBUILD
```

## Translations

User-facing strings are wrapped with `tr()` and extracted to `usr/share/locale/layout-switcher.pot`. The catalog is compiled to `.mo` files for **28 languages**:

> bg · cs · da · de · el · en · es · et · fi · fr · he · hr · hu · is · it · ja · ko · nl · no · pl · pt · pt_BR · ro · ru · sk · sv · tr · uk · zh

### Add or update a translation

```sh
# 1. Regenerate the POT from source
find usr/share/layout-switcher -name '*.py' | xargs xgettext \
    --keyword=tr --language=Python --from-code=UTF-8 \
    --output=usr/share/locale/layout-switcher.pot \
    --package-name=layout-switcher

# 2. Create/merge a language catalog
msgmerge --update usr/share/locale/<lang>.po usr/share/locale/layout-switcher.pot

# 3. Translate the msgstr entries, then compile
msgfmt -o usr/share/locale/<lang>/LC_MESSAGES/layout-switcher.mo \
          usr/share/locale/<lang>.po
```

## License

[MIT](LICENSE) © Big Community & Contributors
