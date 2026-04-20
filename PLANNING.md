# PLANNING.md — Layout Switcher Improvement Roadmap

## Files Analyzed
**Total files read:** 24 (every .py file in the project)
**Total lines analyzed:** 3,681
**Large files (>500 lines) confirmed read in full:**
- `ui/page_extensions.py` (636 lines)

### File inventory

| # | File | Lines | Purpose |
|---|------|-------|---------|
| 1 | `main.py` | 61 | Entry point, `Adw.Application` lifecycle |
| 2 | `__init__.py` | 2 | Package stub |
| 3 | `constants.py` | 144 | APP_ID, paths, layouts, featured extensions, color map, i18n |
| 4 | `utils.py` | 149 | `run_cmd()`, gsettings/dconf helpers, `find_file()`, `gnome_shell_version()` |
| 5 | `backup_manager.py` | 160 | dconf dump/restore, atomic writes, prune old backups |
| 6 | `extension_manager.py` | 324 | Install/remove/toggle GNOME extensions (CLI/EGO/pacman) |
| 7 | `shell_reloader.py` | 137 | D-Bus cascade for live extension reload |
| 8 | `theme_manager.py` | 171 | GTK/Icon/Shell theme apply + color scheme |
| 9 | `settings_store.py` | 124 | JSON settings + GSettings watcher |
| 10 | `layout_applier.py` | 59 | `dconf load` for layout files |
| 11 | `ui/__init__.py` | 3 | UI package stub |
| 12 | `ui/window.py` | 352 | Main window — `Adw.OverlaySplitView` + sidebar + stack |
| 13 | `ui/page_layouts.py` | 210 | FlowBox grid of layout cards |
| 14 | `ui/page_extensions.py` | 636 | Featured cards + installed list + global toggle |
| 15 | `ui/page_themes.py` | 354 | Theme list with dark/light toggle |
| 16 | `ui/styles.py` | 75 | `APP_CSS` string — all visual styles |
| 17 | `ui/widgets.py` | 46 | `ColorDot` custom DrawingArea |
| 18 | `tests/__init__.py` | 7 | Test package |
| 19 | `tests/test_utils.py` | 169 | Tests for run_cmd, gsettings, dconf, find_file, color, version |
| 20 | `tests/test_extension_manager.py` | 156 | Tests for enabled_list, is_installed, list_installed, remove |
| 21 | `tests/test_backup_manager.py` | 108 | Tests for create, latest, list_all, restore, prune |
| 22 | `tests/test_layout_applier.py` | 68 | Tests for apply, ShellReloader strategies |
| 23 | `tests/test_theme_manager.py` | 95 | Tests for list, apply, color_scheme |
| 24 | `tests/test_settings_store.py` | 71 | Tests for Settings JSON persistence |

---

## Current State Summary

**Grade: B**

Well-structured single-purpose GTK4/Adwaita app. Clean separation between service modules (backup, extension, theme, layout managers) and UI pages. Error handling in services is solid — never raises exceptions, always returns `(bool, str)`. Previous audit addressed deprecated APIs (Adw.MessageDialog→AlertDialog, AboutWindow→AboutDialog), added accessibility labels (A01–A14), created test suite (59 passing), typed subclasses (NavRow, ThemeRow), cleaned CSS. Main remaining weaknesses: unused imports, formatting inconsistency, incomplete tests for GI-dependent modules, missing i18n files, ToastOverlay still in use (per new requirements), and several UX friction points.

---

## Critical (fix immediately)

- [ ] **C01 — `AdwToastOverlay` still used for notifications:** `window.py:148` wraps entire UI in `Adw.ToastOverlay`, `window.py:341` creates `Adw.Toast`. Toasts are unsuitable for critical feedback (easily missed, no Orca announcement, disappear on timeout). Use inline status labels or `Adw.AlertDialog` for important feedback. Keep toast only for truly ephemeral confirmations (like "copied to clipboard").

- [ ] **C02 — `settings_store.py` imports `gi` unnecessarily for `Settings` class:** `Settings` is pure JSON, doesn't need GI. `GSettingsMonitor` needs GI. The module-level `import gi` + `gi.require_version("Gtk", "4.0")` prevents testing `Settings` class in environments without GTK (e.g., CI, headless). Split: move `GSettingsMonitor` import of `gi` inside class or use conditional import. This blocks 6 test cases currently.

- [ ] **C03 — Package name `layout-switcher` breaks mypy:** `__init__.py` exists in a dir named `layout-switcher` (hyphen invalid in Python identifiers). mypy refuses to analyze. Either: (a) rename `__init__.py` to not be a package marker, or (b) add `mypy.ini` with `[mypy]` / `namespace_packages = True` / `explicit_package_bases = True`.

- [ ] **C04 — `GestureClick` on layout cards — not keyboard-accessible:** `page_layouts.py:144` — `GestureClick` only responds to mouse/touch. Cards have `set_focusable(True)` but no key handler. Orca users and keyboard-only users cannot activate layout cards via Enter/Space. Add `Gtk.EventControllerKey` that triggers `_on_click` on Enter/Space, or wrap in `Gtk.Button`.

- [ ] **C05 — No keyboard activation for extension featured cards:** `page_extensions.py:131–250` — featured cards are `Gtk.Box` with no click gesture or keyboard handler at all. Install/toggle is via child buttons (OK), but the card itself has no focus/activation. The card `update_property(LABEL)` is set, but it's not focusable or activatable. Add `set_focusable(True)` and key controller.

- [ ] **C06 — Status label color-only feedback (A14 not fully resolved):** `page_layouts.py:200–205` — `.ok-col` and `.err-col` change only color. Orca live region was planned (A14) but not implemented. Add `update_property([Gtk.AccessibleProperty.LIVE], [Gtk.AccessibleLive.POLITE])` to `_status_lbl` so screen readers announce status changes. Also use icon prefix (`✓`/`✗` equivalent via `Gtk.Image`) alongside color for non-color indicator.

---

## High Priority (code quality)

- [ ] **H01 — 14 unused imports across codebase (ruff F401):**
  - `tests/`: 4× unused `MagicMock`, 4× unused `pytest`, 1× unused `subprocess`
  - `main.py`: unused `tr` import
  - `extension_manager.py`: unused `Optional`
  - `settings_store.py`: unused `Path`, unused `Optional`
  - `theme_manager.py`: unused `Optional`
  - `utils.py`: unused `LAYOUTS_DIR`

- [ ] **H02 — 20 files fail `ruff format --check`:** All Python files except `__init__.py` files and `layout_applier.py` need formatting. Run `ruff format .` to fix.

- [ ] **H03 — Vulture dead code (25 findings):**
  - 10× unused lambda params in callbacks (`dlg`, `box`, `g`, `n`, `x`, `y`, `pspec`, `area`, `mock_*`) — use `_` prefix convention
  - `page_extensions.py:290` — `status_lbl` assigned but never used in `_toggle_feat` signature (refactored but param kept)
  - `utils.py` — `LAYOUTS_DIR` imported from constants but never used

- [ ] **H04 — High cyclomatic complexity (4 functions ≥ C grade):**
  - `ThemeMgr.list_themes()` — CC=18 → split into `_scan_gtk()`, `_scan_icons()`, `_scan_shell()` helpers
  - `ExtensionsPage._make_feat_card()` — CC=13 → extract installed vs not-installed widget builders
  - `ExtensionsPage.refresh_installed()` — CC=12 → extract group rendering
  - `ExtMgr.list_installed()` — CC=11 → extract metadata parsing

- [ ] **H05 — `settings_store.py` imports `Gio` at module level but `Settings` class doesn't use it:** This couples pure-JSON `Settings` class to GTK runtime. Move `gi` import to `GSettingsMonitor` class scope or use lazy import.

- [ ] **H06 — Empty locale files:** `locale/en.po` and `locale/pt-BR.po` are 0 bytes. `locale/en.json` is `{}`. gettext is configured but no translations exist. Either: generate `.pot` from source + translate, or remove i18n setup and use plain strings until translations are ready.

- [ ] **H07 — `_install_from_ego()` HTTP request without retry or user-agent rotation:** `extension_manager.py:220` — single attempt `urlopen` with 60s timeout. Extensions.gnome.org may rate-limit or fail transiently. Add 1 retry with backoff for network errors (not for HTTP errors).

- [ ] **H08 — `run_cmd()` logs nothing:** `utils.py:30` — subprocess failures return generic string but no logging. Critical for debugging extension install/remove failures in production. Add `logging.debug` for command + exit code.

---

## Medium Priority (UX improvements)

- [ ] **M01 — Layout cards lack description:** Users unfamiliar with "G-Unity" or "Next GNOME" have no context about what each layout does before applying. Add a subtitle or tooltip describing the layout. *Principle: recognition over recall (Nielsen #6).*

- [ ] **M02 — Confirmation dialog for every layout apply:** `page_layouts.py:155–175` — Apply always shows `Adw.AlertDialog`. Non-destructive actions should use *commit-then-undo* pattern: apply immediately, show "Undo (10s)" inline/toast. This feels faster. *Principle: error recovery > prevention for reversible actions.*

- [ ] **M03 — No layout preview:** All layout cards show static SVGs. Adding a brief description below card name (e.g., "Taskbar at bottom, Activities top-left") would help first-time users. *Principle: information scent.*

- [ ] **M04 — Theme list has no search/filter:** `page_themes.py` — with 50+ themes, scrolling is tedious. Add a search entry at top of the list that filters in real-time. *Principle: flexibility and efficiency of use (Nielsen #7).*

- [ ] **M05 — Extension sub-tabs should show counts:** "Featured" and "Installed" tabs have no badge showing how many items each contains. Add count badge. *Principle: information scent — expectation setting before interaction.*

- [ ] **M06 — Global "Disable All" button is dangerous without confirmation:** `page_extensions.py:581` — one click disables ALL extensions globally. No confirmation dialog. This is a destructive action that can break user's desktop. Add `Adw.AlertDialog` confirmation with clear warning. *Principle: error prevention (Nielsen #5) — destructive actions require confirmation.*

- [ ] **M07 — No visual distinction between user and system extensions in Featured tab:** System extensions show "system" badge in Installed tab but not in Featured cards. Users may try to remove system extensions and get confused. *Principle: visibility of system status (Nielsen #1).*

- [ ] **M08 — Welcome/first-run experience:** No onboarding flow exists. New users see the Layouts page without context. Consider a first-run `Adw.StatusPage` with brief explanation and "Get Started" CTA. Store "intro_shown" in Settings. *Principle: aesthetic-usability effect.*

- [ ] **M09 — No undo for layout application:** After applying a layout, there's no way to revert except manually restoring a backup. The "Backup & Apply" flow creates backup but restoring requires navigating to a different UI. Add "Undo" inline action for 15s post-apply. *Principle: user control and freedom (Nielsen #3).*

---

## Low Priority (polish & optimization)

- [ ] **L01 — `E402` module-level import warnings (17 instances):** All in app source files due to `gi.require_version()` before GI imports. This is unavoidable for PyGObject. Suppress with `# noqa: E402` or add `ruff.toml` with `[lint] ignore = ["E402"]` for `usr/share/layout-switcher/**`.

- [ ] **L02 — No `ruff.toml` or `pyproject.toml` config:** Lint/format rules are undefined. Create `pyproject.toml` with `[tool.ruff]` section to configure E402 ignore, line length, target version.

- [ ] **L03 — `README.md` is the template placeholder:** Shows "pkgbuild-template-translator" — not the actual project. Write proper README with screenshots, install instructions (pacman + manual), usage, and development setup.

- [ ] **L04 — `PKGBUILD` uses `pkgver=$(date)` — non-reproducible:** `pkgbuild/PKGBUILD:11` — version is build-time date. Consider tagging releases and using `APP_VERSION` from `constants.py` for reproducibility.

- [ ] **L05 — `.desktop` file `StartupWMClass=layout-switcher` may not match:** Window title is set to `tr("Layout Switcher")` which is a translated string. On pt-BR, this becomes "Seletor de Layouts" breaking WM class matching. Set `StartupWMClass` to `APP_ID` (`org.communitybig.layout-switcher`), or explicitly set the window's startup-id.

- [ ] **L06 — `ColorDot._draw` param `data` unused:** `widgets.py:39` — `data` param from `set_draw_func` callback is always `None`. Not a bug but vulture reports it. Rename to `_data`.

- [ ] **L07 — Test coverage gaps:** Tests exist for services but NOT for UI modules (no GTK mocking). Consider adding headless GTK tests for widget construction at minimum, or document that UI tests require display.

- [ ] **L08 — `BackupManager.N_KEEP = 10` is not configurable:** Hardcoded constant. Allow override via `Settings` or env var for power users.

- [ ] **L09 — Copyright year outdated:** `window.py:330` — `© 2022–2025`. Should be `2022–2026` or use dynamic year.

---

## Architecture Recommendations

1. **Decouple `Settings` from GI runtime.** `settings_store.py` imports `gi` at module level solely for `GSettingsMonitor`. Move `GSettingsMonitor` to its own file (`gsettings_monitor.py`) or use lazy import: `def __init__(self): import gi; ...`. This unblocks testability in CI/headless environments.

2. **Create `pyproject.toml` for tooling config.** Currently no lint/format/test configuration. A minimal `pyproject.toml` with `[tool.ruff]`, `[tool.pytest.ini_options]`, and `[project]` metadata would standardize the development workflow.

3. **Reduce `page_extensions.py` complexity.** At 636 lines with CC≥12 in two methods, this is the hardest file to maintain. Extract:
   - `_FeaturedCard` widget class (handles its own state transitions)
   - `_InstalledRow` widget class (encapsulates switch/remove logic)
   - This drops `_make_feat_card` and `_make_installed_row` to simple instantiations.

4. **Standardize callback signature naming.** Current mix: `on_r`, `on_sw`, `task`, `_scan`. Adopt: `_on_<widget>_<signal>` for GTK signals, `_task_<operation>` for thread pool tasks.

5. **Add a `conftest.py` with shared fixtures.** Tests duplicate `sys.path.insert` and `patch("constants.*")` setup. A `conftest.py` with `@pytest.fixture(autouse=True)` for path setup and common mocks would DRY the test suite.

---

## UX Recommendations

1. **Progressive disclosure on layout page.** Show a subtitle under each layout card name: "Classic taskbar, bottom panel" / "GNOME vanilla, no extensions" / "Unity-like left dock". Users shouldn't need to apply a layout to discover what it does. *Principle: recognition over recall.*

2. **Immediate theme preview.** When hovering a theme row, show a small preview thumbnail (screenshot or color swatch panel). This transforms theme selection from trial-and-error to informed choice. *Principle: visibility of system status.*

3. **Replace confirm() pattern with commit-then-undo for layouts.** Apply the layout immediately when clicked. Show an "Undo" action bar at bottom for 15 seconds. Users who know what they want get instant gratification. Users who made a mistake can undo without navigating restore flows. *Principle: user control and freedom + error recovery.*

4. **Add search to both themes and installed extensions.** With 50+ themes and 20+ extensions, scrolling is a O(n) operation. A search box at top filters instantly. Follow Adw.NavigationView search bar pattern. *Principle: flexibility and efficiency of use.*

5. **Badge counts on sub-tabs.** "Installed (12)" and "Featured (4)" — subtle count badges set expectations before clicking. *Principle: information scent — users predict density of content.*

6. **Dark/Light toggle needs more prominence.** The pill in the top-right is easily missed. Consider making it a full-width banner at top of themes page, or a sticky footer. The color scheme is arguably the most important theme setting. *Principle: visual hierarchy.*

---

## Orca Screen Reader Compatibility

### Issues found

| # | Widget | File:Line | Orca Impact | Fix |
|---|--------|-----------|-------------|-----|
| A01 | Layout cards — `GestureClick` only | page_layouts.py:144 | Cards are focusable but cannot be activated via keyboard (Enter/Space). Orca user is stuck. | Add `Gtk.EventControllerKey` → trigger `_on_click` on Enter/Space. |
| A02 | Extension featured cards — no focus or activation | page_extensions.py:131 | Cards are `Gtk.Box` with no `set_focusable(True)`. Invisible to keyboard navigation. | Add `set_focusable(True)` + key controller, or use `Gtk.FlowBoxChild` activatable signal. |
| A03 | Status label — color-only change | page_layouts.py:200 | Success/error indicated only by CSS color (`.ok-col`/`.err-col`). Orca announces nothing. | Add `Gtk.AccessibleProperty.LIVE = POLITE` to `_status_lbl`. Add icon prefix for non-color indicator. |
| A04 | Toast messages — unreliable for screen readers | window.py:341 | `Adw.Toast` may or may not be announced by Orca depending on focus state and timing. | For critical feedback, use inline labels with LIVE region instead of toast. |
| A05 | "Disable All" button — state not announced | page_extensions.py:57 | Button toggles between "Disable All" and "Enable All" — label updates but no ARIA state change. | After `_refresh_global_btn()`, call `update_property([Gtk.AccessibleProperty.LABEL], [current_label])` (already done but verify it fires on toggle). |
| A06 | Theme kind tabs — no ARIA selected state | page_themes.py:169 | Custom buttons toggle `.kind-on` CSS but no accessible selected state. Orca reads all tabs identically. | Use `update_property([Gtk.AccessibleProperty.SELECTED], [True/False])` or migrate to `Adw.ViewSwitcher`. |
| A07 | Extension sub-tabs — same as A06 | page_extensions.py:80 | Custom sub-tabs use CSS `.sub-on` with no accessible state. | Same fix as A06. |
| A08 | FlowBox items in layouts — no role grouping | page_layouts.py:79 | `Gtk.FlowBox` with `Gtk.SelectionMode.NONE` — Orca may not announce grid navigation context. | Set accessible role on FlowBox: `Gtk.AccessibleRole.LIST` or `GRID`. |

### Test checklist for manual verification

- [ ] Launch app with Orca running (`orca &; python3 main.py`)
- [ ] Navigate entire sidebar using only Tab/Shift+Tab and Arrow keys
- [ ] Verify Orca announces every nav item (Layouts, Extensions, Themes)
- [ ] Navigate layout cards using Tab — verify each card name is announced
- [ ] **Press Enter/Space on focused layout card — verify activation works**
- [ ] Verify status label change is announced after applying layout
- [ ] Navigate to Extensions tab — verify featured card contents announced
- [ ] Toggle extension switch — verify "enabled"/"disabled" state announced
- [ ] Navigate Installed list — verify each row name + state announced
- [ ] Press "Disable All" — verify confirmation appears (when implemented)
- [ ] Navigate to Themes tab — verify theme rows announced with name
- [ ] Switch GTK/Icons/Shell tabs — verify selected tab announced
- [ ] Switch Light/Dark — verify mode change announced
- [ ] Apply a theme — verify feedback is announced (not just toast)
- [ ] Test all buttons: Menu, Sidebar toggle, Remove, Install, Settings

---

## Accessibility Checklist (General)

- [x] Most interactive elements have accessible labels (A01-A14 from previous audit)
- [ ] **Keyboard navigation does NOT work for layout cards (GestureClick only)**
- [ ] **Keyboard navigation does NOT work for featured extension cards**
- [x] Color is supplemented by text labels in most places
- [ ] **Status labels use color-only indication (no icon/text prefix)**
- [x] Text is readable at 2x font size (no hardcoded font-size in CSS)
- [x] Focus indicators visible (`.nav-row:focus` has outline)
- [x] Dialog responses are keyboard-accessible (libadwaita handles this)
- [ ] **Custom tab buttons lack accessible selected state**

---

## Tech Debt

| Source | Count | Severity | Details |
|--------|-------|----------|---------|
| Unused imports (F401) | 14 | Low | Tests: `MagicMock`, `pytest`, `subprocess`. Source: `Optional`, `Path`, `tr`, `LAYOUTS_DIR` |
| Format violations | 20 files | Low | `ruff format` would fix all |
| Vulture dead code | 25 | Low | Mostly unused callback params — cosmetic |
| Cyclomatic complexity ≥ C | 4 fns | Medium | `list_themes` CC=18, `_make_feat_card` CC=13, `refresh_installed` CC=12, `list_installed` CC=11 |
| Empty i18n files | 3 | Medium | `.po` files exist but are 0 bytes; `en.json` is `{}` |
| No `pyproject.toml` | 1 | Medium | No lint/format/test config defined |
| mypy blocked | 1 | Low | Package name `layout-switcher` has hyphen — invalid Python identifier |
| Test gaps (GI-dependent) | 6 tests | Medium | `test_theme_manager.py` + `test_settings_store.py` fail without `gi` module |
| TODO/FIXME markers | 0 | — | None found |
| Copyright year | 1 | Low | Says 2022–2025, should be 2022–2026 |
| README placeholder | 1 | Medium | Still shows template text "pkgbuild-template-translator" |

---

## Metrics (current baseline)

| Metric | Value |
|--------|-------|
| Total Python files | 24 |
| Total lines | 3,681 |
| Files >200 lines | 5 (`page_extensions.py`, `page_themes.py`, `window.py`, `extension_manager.py`, `page_layouts.py`) |
| Test files | 6 |
| Tests passing | 59 |
| Tests erroring (need GI) | 6 |
| ruff lint issues | ~30 (14 F401 + 17 E402) |
| ruff format violations | 20 files |
| Vulture findings | 25 |
| Radon CC ≥ C | 4 functions |
| Deprecated API calls | 0 (all migrated in previous audit) |
| Accessible widgets | ~25 of ~30 interactive (5 remaining issues) |
| i18n files | Structure exists, content empty |
| Custom CSS classes | 22 |
