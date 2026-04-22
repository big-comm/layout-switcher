# PLANNING.md — Layout Switcher Roadmap

Última revisão: 2026-04-21
Versão atual: **2.4.1**

## Status geral

Aplicativo GTK4/Adwaita bem estruturado. **77 testes passando**, `ruff check` limpo,
`ruff format --check` sem violações, 25 arquivos Python formatados. Separação clara
entre módulos de serviço (backup, extension, theme, layout managers) e páginas de UI.

---

## ✅ Concluído nesta rodada (2026-04-21)

### Bug crítico — BigGnome não aplicava
**Sintoma:** Clicar no card *BigGnome* não produzia efeito visual.
**Causa-raiz:** `LayoutApplier.apply()` executava `dconf load /org/gnome/shell/`,
mas os arquivos de layout (ex.: `biggnome.txt`, idênticos ao `settings.gnome`
usado em `comm-gnome-config/etc/skel/.config/dconf/`) contêm seções com
caminhos **absolutos** (`[ca/desrt/dconf-editor]`, `[com/gexperts/Tilix]`,
`[org/gnome/shell/extensions/gsconnect]` …). Ao carregar em
`/org/gnome/shell/`, os caminhos ficavam aninhados incorretamente
(ex.: `/org/gnome/shell/org/gnome/shell/extensions/...`), então nada se
aplicava no caminho real. O `dconf load` retornava sucesso mas gravava em
locais inválidos.

**Correção:** `layout_applier.py` agora segue o padrão do script de sessão
`startgnome-community`:

```python
run_cmd(["dconf", "reset", "-f", "/"], timeout=10)   # estado limpo
run_cmd(["dconf", "load", "/"], stdin_text=data, ...)  # dump absoluto
ShellReloader.reload_all()
```

### Consistência do rename next-gnome → biggnome
- `icons/next-gnome.svg` → `icons/biggnome.svg` (`git mv`)
- `icons/next-gnome.png` → `icons/biggnome.png` (`git mv`)
- `constants.py:141` → ícone referenciado corrigido

### Outras melhorias fechadas
- **L09** — Copyright `© 2022–2026` em `window.py`
- **Versão consistente** — `APP_VERSION = "2.4.1"` (constants.py) =
  `version = "2.4.1"` (pyproject.toml)
- **H08 / diagnóstico** — `find_file()` agora loga (DEBUG) todos os caminhos
  testados quando não encontra o arquivo — facilita diagnosticar layout/ícone
  ausente em produção.
- **Testes de LayoutApplier** — novo caso `test_apply_reset_failure` e
  validação explícita das chamadas `dconf reset -f /` e `dconf load /`.

---

## ✅ Concluído em rodadas anteriores (confirmado no código)

- **C02** — `Settings` desacoplado de `gi`. `GSettingsMonitor.__init__()` faz
  lazy import de `gi` (`settings_store.py:78-83`).
- **C04** — Layout cards aceitam teclado (Enter/Space) via
  `Gtk.EventControllerKey` (`page_layouts.py:154-163`).
- **C06** — Status labels com prefixo `✓`/`✗` (não color-only) em
  `page_layouts.py:263-266`.
- **H08** — `run_cmd()` loga via `log.debug/warning/error` (`utils.py:25,56-68`).
- **M08** — Banner de primeiro uso (`window.py:187-200`).
- **M09** — Undo toast (15s) após aplicar layout (`page_layouts.py:219-231`).
- **L02** — `pyproject.toml` com `[tool.ruff]`, `[tool.pytest.ini_options]`.
- **L03** — `README.md` reescrito (sem placeholder).
- **L05** — `.desktop` usa `StartupWMClass=org.communitybig.layout-switcher`.

---

## 🔶 Pendente — priorizado

### Crítico
- [ ] **C01 — `AdwToastOverlay` para feedback crítico.**
  `window.py:144, 221, 362-364` ainda embrulha toda a UI em
  `Adw.ToastOverlay`. Toasts são OK para confirmações efêmeras (backup salvo,
  layout restaurado), mas feedback de **erro de aplicação** deveria usar
  `Adw.AlertDialog` ou label inline com *live region*. O status label de
  `page_layouts.py` já usa `✓`/`✗`; basta elevar erros críticos para
  diálogo quando `ok=False`.
- [ ] **C05 — Featured cards de extensões sem ativação por teclado.**
  `page_extensions.py:131-250` — cards são `Gtk.Box` sem `set_focusable(True)`
  nem key controller. Install/toggle funciona pelo switch interno, mas
  o card em si não é alcançável via Tab.

### Alto
- [ ] **Outros layouts com formato misto.** Os arquivos
  `classic.txt`, `minimal.txt`, `modern.txt`, `g-unity.txt` contêm
  mistura de seções absolutas (`[org/gnome/Console]`) e relativas
  (`[extensions/arcmenu]`, `[keybindings]`). Agora que o loader usa
  `dconf load /`, seções relativas como `[extensions/...]` serão aplicadas em
  `/extensions/...` (raiz do dconf), não em `/org/gnome/shell/extensions/...`.
  **Ação:** regerar cada arquivo na VM com `dconf dump / > layout.txt` após
  configurar o desktop no estado desejado, igual ao `biggnome.txt`.
- [ ] **H06 — i18n incompleto.** `locale/en.po` e `locale/pt-BR.po` são
  arquivos vazios; `locale/en.json` é `{}`. Decidir entre (a) gerar `.pot` via
  `xgettext` e manter tradução viva, ou (b) remover gettext e usar strings
  literais até que traduções sejam reais.
- [ ] **H04 — Complexidade ciclomática.**
  - `ThemeMgr.list_themes()` — CC=18 → dividir em `_scan_gtk/_scan_icons/_scan_shell`.
  - `ExtensionsPage._make_feat_card()` — CC=13 → separar estados
    (instalada vs não-instalada).
  - `ExtensionsPage.refresh_installed()` — CC=12 → extrair renderização de grupos.
  - `ExtMgr.list_installed()` — CC=11 → extrair parsing de metadados.

### Médio (UX)
- [ ] **M01 / UX-1 — Descrição nos cards de layout** (já há `tooltip_text`
  e subtítulo em `page_layouts.py:132-141`, confirmar cobertura em todos os cards).
- [ ] **M02 / UX-3 — Commit-then-undo para apply.** Hoje há diálogo de
  confirmação + undo toast. Para ações reversíveis, remover o diálogo e
  ir direto ao apply + undo toast (já implementado, só simplificar fluxo).
- [ ] **M04 — Busca/filtro em temas.** `page_themes.py` com 50+ itens
  ganharia barra de busca no topo.
- [ ] **M06 — Confirmação para "Disable All".** `page_extensions.py:581`
  desabilita todas as extensões sem confirmar.
- [ ] **M07 — Badge "system" em featured cards** (hoje só aparece em
  Installed).

### Baixo
- [ ] **L04 — `PKGBUILD` `pkgver=$(date)` não-reproduzível.** Decisão de
  distribuição; usar tag ou `APP_VERSION` daria reprodutibilidade.
- [ ] **L07 — Testes de UI.** 77 testes cobrem services; UI widgets não são
  testados (requer display/xvfb).
- [ ] **L08 — `BackupManager.N_KEEP` é configurável via env
  `LAYOUT_SWITCHER_N_KEEP` (`backup_manager.py:28`) — documentar.**
- [ ] **Arquivos legados.** `PLANNING.old.md` pode ir para o histórico git.

---

## Arquitetura / Débitos técnicos

| Item | Estado | Observação |
|---|---|---|
| `ruff check` | ✅ limpo | `[tool.ruff]` em `pyproject.toml` com E402 ignorado |
| `ruff format --check` | ✅ 25 arquivos formatados | — |
| Testes | ✅ 77 passing | `tests/` com 7 arquivos de teste |
| mypy | ⚠ bloqueado pelo nome de pacote | `layout-switcher` (hífen) — ver C03 original |
| Vulture (dead code) | ⚠ ~25 findings (cosmético) | maioria params não-usados em callbacks |
| CC ≥ C | ⚠ 4 funções | ver H04 |

---

## Padrão de formato de arquivos de layout

**IMPORTANTE:** arquivos em `layouts/*.txt` devem ser produzidos por:

```bash
# no ambiente GNOME com o layout desejado aplicado:
dconf dump / > usr/share/layout-switcher/layouts/<nome>.txt
```

Arquivos no formato antigo (`dconf dump /org/gnome/shell/`) **não funcionam**
com o loader atual. O `biggnome.txt` é a referência canônica e é idêntico ao
`settings.gnome` usado em `comm-gnome-config/etc/skel/.config/dconf/`.

O `LayoutApplier.apply()` faz:
1. `dconf reset -f /` — limpa o perfil do usuário
2. `dconf load /` — aplica o dump absoluto
3. `ShellReloader.reload_all()` — recarrega extensões sem logout

Um backup é criado antes de aplicar (via `BackupManager.create()`) e o toast
de undo permite restaurá-lo nos 15 s seguintes.
