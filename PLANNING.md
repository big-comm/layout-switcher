# PLANNING.md — Layout Switcher Improvement Roadmap

## Files Analyzed
**Total files read:** 17
**Total lines analyzed:** ~3,100
**Large files (>500 lines) confirmed read in full:**
- `ui/page_extensions.py` (573 lines)

### File inventory

| # | File | Lines | Purpose |
|---|------|-------|---------|
| 1 | `main.py` | 60 | Entry point, `Adw.Application` lifecycle |
| 2 | `__init__.py` | 35 | Package exports |
| 3 | `constants.py` | 140 | App ID, paths, layouts, featured extensions, color map, i18n |
| 4 | `utils.py` | 149 | `run_cmd()`, gsettings/dconf helpers, `find_file()`, `gnome_shell_version()` |
| 5 | `backup_manager.py` | 160 | dconf dump/restore, atomic writes, prune old backups |
| 6 | `extension_manager.py` | 321 | Install/remove/toggle GNOME extensions (CLI/EGO/pacman) |
| 7 | `shell_reloader.py` | 137 | D-Bus cascade for live extension reload |
| 8 | `theme_manager.py` | 171 | GTK/Icon/Shell theme apply + color scheme |
| 9 | `settings_store.py` | 119 | JSON settings + GSettings watcher |
| 10 | `layout_applier.py` | 59 | `dconf load` for layout files |
| 11 | `ui/__init__.py` | 25 | UI package exports |
| 12 | `ui/window.py` | 397 | Main window with `Adw.OverlaySplitView` |
| 13 | `ui/page_layouts.py` | 200 | FlowBox grid of layout cards |
| 14 | `ui/page_extensions.py` | 573 | Featured cards + installed list + global toggle |
| 15 | `ui/page_themes.py` | 303 | Theme list with dark/light toggle |
| 16 | `ui/styles.py` | 78 | `APP_CSS` string |
| 17 | `ui/widgets.py` | 42 | `ColorDot` custom DrawingArea |

---

## Current State Summary

**Grade: B−**

The app is functional and well-structured for a single-developer project. Clean separation between managers (business logic) and UI pages. Error handling in service modules is solid (never raises exceptions). The `OverlaySplitView` layout has just been applied. Main weaknesses: zero tests, deprecated API usage, no accessibility support, several UX friction points, and dynamic attributes instead of proper subclasses.

---

## Critical (fix immediately)

- [x] ✅ **C01 — No test suite:** Zero tests exist. Any refactor risks silent regressions. Create at least unit tests for `BackupManager`, `ExtMgr` (mock subprocess), `ThemeMgr`, `LayoutApplier`, `Settings`, and `ShellReloader`.

- [x] ✅ **C02 — Hicolor icon path wrong:** `usr/share/icons/hicolor/org.bigappearance.app.svg` should be `usr/share/icons/hicolor/scalable/apps/org.bigappearance.app.svg`. Without proper path, the icon won't appear in app launchers or the GNOME app grid. *(SVG copiado para caminho correto; arquivo antigo em hicolor/ raiz deve ser removido via `rm usr/share/icons/hicolor/org.bigappearance.app.svg`)*

- [x] ✅ **C03 — `Adw.MessageDialog` deprecated (7 instances):** Migrado para `Adw.AlertDialog` em todos os 7 pontos:
  - `ui/window.py:_do_restore_backup()` — restore confirmation
  - `ui/window.py:_show_intro()` — welcome dialog
  - `ui/page_layouts.py:_on_click()` — layout apply confirmation
  - `ui/page_extensions.py:_confirm_install()` — install confirmation
  - `ui/page_extensions.py:_confirm_remove()` — remove confirmation
  - `ui/page_themes.py:_show_user_theme_dialog()` — user themes missing

- [x] ✅ **C04 — `Adw.AboutWindow` deprecated:** `ui/window.py:_show_about()` migrado para `Adw.AboutDialog`.

- [x] ✅ **C05 — No accessible names on interactive widgets (Orca-breaking):** Adicionados `update_property(LABEL)` em todos os widgets interativos (A01-A14). A15 já está OK (CheckButton com label nativo).

- [x] ✅ **C06 — `Settings.delete()` uses internal hack:** Corrigido — agora usa escrita atômica direta, sem `__func__` nem chave `"__noop__"`.

---

## High Priority (code quality)

- [x] ✅ **H01 — Dynamic `_page_key` attribute on `Gtk.ListBoxRow`:** Criada subclass `NavRow(Gtk.ListBoxRow)` com property `page_key` tipada.

- [x] ✅ **H02 — Dynamic `_theme_name`/`_theme_kind` on `Gtk.ListBoxRow`:** Criada subclass `ThemeRow(Gtk.ListBoxRow)` com properties tipadas `theme_name` e `theme_kind`.

- [x] ✅ **H03 — `__init__.py` re-exports all symbols but is never used:** Limpos ambos `__init__.py` para stubs mínimos.

- [x] ⏭️ **H04 — No type annotations on callbacks:** Skipped — most callbacks are GTK signal lambdas/closures where type hints add noise. Low ROI.

- [x] ✅ **H05 — `_install_from_ego()` validates zip but doesn't verify content-type:** Adicionada verificação de `Content-Type: text/html` antes de processar download.

- [x] ✅ **H06 — `find_file()` `dirs` parameter is confusing:** Renomeado para `subdirs` para clareza.

- [x] ⏭️ **H07 — `_open_gnome_extensions()` fallback opens browser URL:** Skipped — o fallback para o browser é aceitável como último recurso; a UX é adequada.

- [x] ✅ **H08 — `.dim` CSS class still used but `dim-label` is native:** Migrados todos os 12 usos de `.dim` → `dim-label`; removida regra `.dim` do CSS.

---

## Medium Priority (UX improvements)

- [x] ✅ **M01 — No loading state for theme list:** Theme scan now runs in background thread with spinner; UI populates via `GLib.idle_add` when done.

- [x] ✅ **M02 — No feedback when clicking disabled layout card:** Now shows "Already active" toast instead of opening the Apply dialog.

- [x] ⏭️ **M03 — Extension install progress is only a spinner:** Deferred — requires reworking card state machine.

- [x] ⏭️ **M04 — Sub-tabs are custom buttons:** Deferred — requires significant rework to adopt AdwViewSwitcher.

- [x] ⏭️ **M05 — No search/filter:** Deferred — new feature, not a fix.

- [x] ⏭️ **M06 — Global "Disable All" button position:** Deferred — UX decision requiring design review.

- [x] ✅ **M07 — Layout "Backup & Apply" vs "Apply" confusion:** Only "Backup & Apply" is suggested action; "Apply" is default/flat.

- [x] ✅ **M08 — No AdwBreakpoint for responsive layout:** Sidebar toggle button added to content header; visible only when collapsed; auto-closes on nav selection.

- [x] ✅ **M09 — Toast timeout increased:** Changed from 3s to 5s for all toast messages.

- [x] ⏭️ **M10 — Welcome dialog checkbox pattern:** Deferred — UX decision requiring settings page.

---

## Low Priority (polish & optimization)

- [x] ✅ **L01 — `Gtk.CssProvider.load_from_data()` deprecated:** Replaced with `load_from_string()` (GTK 4.10+). `add_provider_for_display` is still the correct static method.

- [x] ✅ **L02 — `.card` CSS class on layout/ext cards:** Removed redundant `border-radius: 14px` from `.layout-card` and `.ext-card`; libadwaita `.card` class handles it natively.

- [x] ✅ **L03 — Hardcoded colors in `.ok-col` and `.err-col`:** Replaced `#26a269` → `@success_color` and `#c01c28` → `@error_color`.

- [x] ⏭️ **L04 — `_prune()` called every backup creation:** Skipped — negligible overhead for N_KEEP=10.

- [x] ⏭️ **L05 — `ColorDot` uses raw Cairo drawing:** Kept as-is. Cairo `DrawingArea` is the correct approach for per-instance dynamic colors; CSS alternative would pollute global providers.

- [x] ⏭️ **L06 — `Pango` imported but only `Pango.EllipsizeMode` used:** Skipped — cosmetic; `require_version` is needed per-file for PyGObject.

- [x] ✅ **L07 — Emoji characters in status text:** Removed ⏳, ✓, ✗ emoji prefixes; status text now uses plain descriptive words with CSS color classes.

- [x] ⏭️ **L08 — No locale/translations directory structure:** Deferred — requires actual translator contributions (.po/.pot files).

---

## Architecture Recommendations

1. **Extract dialog creation into utility functions.** Six places create `Adw.MessageDialog` (soon `Adw.AlertDialog`) with repetitive patterns. A helper like `show_confirm(parent, heading, body, responses) → Future[str]` would reduce duplication.

2. **Create proper `GObject.Property`-based subclasses for custom rows.** `NavRow`, `ThemeRow`, `ExtRow` would eliminate all `type: ignore[attr-defined]` hacks and make the code more introspectable.

3. **Move CSS class management to a constants module.** CSS class names like `"nav-sel"`, `"ext-on"`, `"scheme-pill"`, `"s-on"`, `"kind-on"` are string literals scattered across 5 files. A `CssClass` enum or namespace would prevent typos.

4. **Consider migrating custom sub-tabs to `Adw.ViewStack` + `Adw.ViewSwitcher`.** The custom tab bars in Extensions and Themes pages reinvent `Adw.ViewSwitcher` behavior (mutual exclusion, active highlighting). Using native widgets would give free accessibility, animation, and responsive behavior.

5. **Add a single-instance guard.** The app uses `GtkApplication` which normally handles single-instance, but the `APP_ID` should match the `.desktop` file's `StartupWMClass`. Currently the `.desktop` uses `StartupWMClass=layout-switcher` but the window title is set to a translated string, which may break matching.

---

## UX Recommendations

1. **Progressive disclosure (layout page):** Show layout descriptions on hover or in a subtitle under each card. Users unfamiliar with "G-Unity" or "Next GNOME" have no way to know what they do without trying them. *Principle: recognition over recall (Nielsen's 6th heuristic).*

2. **Undo instead of confirm:** Instead of "Apply this layout?" confirmation dialogs, apply immediately and show an "Undo (10s)" toast. This follows the *commit-then-undo* pattern which feels faster and more forgiving. *Principle: error recovery > error prevention for non-destructive actions.*

3. **Immediate visual feedback on theme change:** When applying a theme, the list refreshes but the user doesn't see the desktop change. Add a small preview thumbnail or before/after overlay. *Principle: visibility of system status (Nielsen's 1st heuristic).*

4. **Group "Enabled" count as a badge on the Extensions tab:** Instead of showing "15 installed · 8 enabled" as text, put a badge on the "Installed" sub-tab showing the count. *Principle: information scent — users know what to expect before clicking.*

5. **First-run experience:** The current welcome dialog is text-heavy. Consider a `Adw.StatusPage` splash with an illustration and a single "Get Started" button. *Principle: aesthetic-usability effect — users perceive beautiful interfaces as more usable.*

6. **Consistent action hierarchy in dialogs:** "Backup & Apply" and "Apply" as both suggested actions violates the *one primary action* principle. Make "Backup & Apply" the primary (suggested) and "Apply without backup" a secondary flat button. *Principle: Hick's Law — fewer equivalent choices = faster decisions.*

---

## Orca Screen Reader Compatibility

### Issues found

| # | Widget | File:Line | Orca Impact | Fix |
|---|--------|-----------|-------------|-----|
| A01 | Layout cards (`Gtk.Box` + `GestureClick`) | page_layouts.py:87 | Orca cannot announce card purpose, cannot focus via keyboard, not a button/activatable | Wrap each card in `Gtk.Button` or make the `Gtk.FlowBoxChild` activatable with `set_accessible_name(layout_name)` |
| A02 | Extension featured cards | page_extensions.py:131 | Same as A01 — cards are not focusable by Orca | Same fix — make FlowBoxChild accessible |
| A03 | Nav sidebar rows | window.py:264 | `Gtk.ListBoxRow` has no accessible name, Orca reads raw widget type | Add `row.update_property([Gtk.AccessibleProperty.LABEL], [label])` |
| A04 | Theme rows | page_themes.py:236 | Row is activatable but has no accessible name describing the theme | Add `row.update_property([Gtk.AccessibleProperty.LABEL], [f"{name} theme, {'active' if is_on else 'inactive'}"])` |
| A05 | Extension switches (featured) | page_extensions.py:182 | `Gtk.Switch` has no accessible name — Orca says "switch" with no context | `sw.update_property([Gtk.AccessibleProperty.LABEL], [f"Toggle {ext['name']}"])` |
| A06 | Extension switches (installed) | page_extensions.py:520 | Same — switch has no label for Orca | `sw.update_property([Gtk.AccessibleProperty.LABEL], [f"Toggle {ext['name']}"])` |
| A07 | Remove buttons (installed list) | page_extensions.py:536 | Icon-only button with tooltip but no accessible name | `rm.set_accessible_name(f"Remove {ext['name']}")` or `update_property` |
| A08 | Light/Dark pill buttons | page_themes.py:105,115 | Buttons have child Box with icon+label — Orca may not read the label | Set `self._light_btn.update_property([Gtk.AccessibleProperty.LABEL], [tr("Light mode")])` |
| A09 | Global enable/disable button | page_extensions.py:57 | Button label changes dynamically but accessible state doesn't | After `_refresh_global_btn()`, also call `update_property` with current state |
| A10 | Restore backup button | window.py:154 | Icon-only button, tooltip only — Orca says "button" | `restore_btn.update_property([Gtk.AccessibleProperty.LABEL], [tr("Restore Backup")])` |
| A11 | Menu button | window.py:160 | Has icon name but no accessible label | `menu_btn.update_property([Gtk.AccessibleProperty.LABEL], [tr("Main menu")])` |
| A12 | `ColorDot` widget | widgets.py:22 | Custom DrawingArea has no accessible role or description — completely invisible to Orca | Set `self.update_property([Gtk.AccessibleProperty.LABEL], [f"Color: {hex_color}"])` and `set_accessible_role(Gtk.AccessibleRole.IMG)` |
| A13 | Layout card "Active" ribbon | page_layouts.py:102 | Visual-only indicator — Orca user has no way to know which layout is active | Include "(active)" in the card's accessible name |
| A14 | Status labels (ok/error) | page_layouts.py:196 | Color-only change (`.ok-col` / `.err-col`) to indicate success/failure | Orca needs a live region announcement: use `update_property([Gtk.AccessibleProperty.LIVE], [Gtk.AccessibleLive.POLITE])` |
| A15 | Dialog extra_child checkbox | window.py:383 | `Gtk.CheckButton` inside `Adw.MessageDialog.set_extra_child()` — may not be in Orca's tab order | Verify focusability; consider moving to app settings |

### Test checklist for manual verification

- [ ] Launch app with Orca running (`orca &; python3 main.py`)
- [ ] Navigate entire sidebar using only Tab/Shift+Tab and Arrow keys
- [ ] Verify Orca announces every nav item (Layouts, Extensions, Themes)
- [ ] Navigate layout cards — verify each card is announced by name
- [ ] Activate a layout card — verify dialog is announced
- [ ] Navigate to Extensions tab — verify featured cards are announced
- [ ] Toggle an extension switch — verify state change is announced
- [ ] Navigate installed extensions list — verify each row is announced
- [ ] Navigate to Themes tab — verify theme rows are announced
- [ ] Switch between Light/Dark — verify Orca announces the change
- [ ] Switch theme kind tabs (GTK/Icons/Shell) — verify announcement
- [ ] Test all buttons: Restore Backup, Menu, Global Enable/Disable, Remove
- [ ] Verify all error/success messages are announced by Orca
- [ ] Test welcome dialog with keyboard only

---

## Accessibility Checklist (General)

- [ ] All interactive elements have accessible labels
- [ ] Keyboard navigation works for all flows (Tab, Arrow, Enter, Escape)
- [ ] Color is never the only indicator (`.ok-col`/`.err-col` use only color — fix L07/A14)
- [ ] Text is readable at 2x font size (verified: no hardcoded `font-size` in CSS)
- [ ] Focus indicators are visible (`.nav-row:focus` has outline — OK)
- [ ] Dialog responses are keyboard-accessible (libadwaita handles this — OK)

---

## Tech Debt

| Source | Count | Severity | Details |
|--------|-------|----------|---------|
| Deprecated APIs | 8 | High | 7× `Adw.MessageDialog` + 1× `Adw.AboutWindow` |
| `type: ignore` | 5 | Medium | 3× `_page_key`, 2× `_theme_name`/`_theme_kind` — dynamic attrs |
| Dead code | 1 | Low | `__init__.py` re-exports never used externally |
| Missing translations | 1 | Medium | gettext setup present but no `.po`/`.pot` files |
| No tests | 1 | Critical | Zero test files exist |

---

## Metrics (before)

| Metric | Value |
|--------|-------|
| Total Python files | 17 |
| Total lines | ~3,100 |
| Files >200 lines | 4 (`page_extensions.py`, `window.py`, `extension_manager.py`, `page_themes.py`) |
| Deprecated API calls | 8 |
| Accessible widgets | 0 of ~30 interactive widgets |
| Tests | 0 |
| i18n coverage | Setup only; 0 `.po` files |
| Custom CSS classes | 22 |
| `type: ignore` comments | 5 |
