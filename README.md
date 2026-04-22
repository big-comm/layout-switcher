# Community Layout Switcher

GTK4 + libadwaita app for managing GNOME desktop layouts, shell extensions, and themes.

## Features

- **Layouts** — Switch between pre-configured desktop layouts (BigGnome, Classic, Hybrid, G-Unity, Minimal, Modern) with one click. Automatic dconf backup before applying.
- **Extensions** — Browse featured GNOME Shell extensions, install from extensions.gnome.org, enable/disable/remove installed extensions.
- **Themes** — Manage GTK, icon, cursor, and shell themes. Filter by kind, search by name, apply with one click.

## Requirements

- GNOME Shell 45+
- Python 3.10+
- PyGObject (gi) with GTK 4.0 and Adw 1
- `dconf`, `gsettings`, `gnome-extensions` CLI tools

## Install

### Arch Linux (pacman)

```sh
# from BigCommunity repo (if configured)
sudo pacman -S layout-switcher
```

### Manual

```sh
git clone https://github.com/BigCommunity/layout-switcher.git
cd layout-switcher
# copy files to system paths
sudo cp -r usr/ /
```

## Development

```sh
# run from source
python usr/share/layout-switcher/main.py

# lint
ruff check .

# format
ruff format .

# tests
python -m pytest tests/ -q
```

## Project Structure

```
usr/
  bin/layout-switcher              # launcher script
  share/layout-switcher/
    main.py                        # app entry point
    constants.py                   # APP_ID, layouts, paths
    utils.py                       # run_cmd, helpers
    settings_store.py              # Settings + GSettings monitor
    extension_manager.py           # GNOME Shell extension ops
    theme_manager.py               # theme listing + application
    layout_applier.py              # dconf backup + apply
    shell_reloader.py              # GNOME Shell D-Bus reload
    backup_manager.py              # timestamped backups
    ui/
      window.py                    # main AdwApplicationWindow
      page_layouts.py              # layouts page
      page_extensions.py           # extensions page
      page_themes.py               # themes page
      widgets.py                   # shared widgets (ColorDot)
      styles.py                    # CSS-in-Python
  share/applications/              # .desktop file
  share/icons/                     # app icons
tests/                             # pytest unit tests
```

## License

MIT — see [LICENSE](LICENSE).
