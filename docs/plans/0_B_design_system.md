# Implementation Plan — Design System Bootstrap (from raw brand materials)

One-time setup for replacing the bundled Databricks design system with your own. Run this after `0_A_initial_setup.md` and before per-page plans. It produces the same set of artefacts (`.streamlit/config.toml`, `.streamlit/brand-theme.toml`, `static/fonts/`, `assets/logos/`, `DESIGN-SYSTEM.md`, optional `assets/styles.css`) but populated with *your* brand's colours, type, and logos.

> **Sources of truth.** This plan follows the **`streamlit-custom-style`** skill that ships with this repo (under `.agents/skills/streamlit-custom-style/`). The skill's layered approach is: native theme TOML for ~90% of the work, single `init_page()` bootstrap, scoped `.st-key-*` CSS only when the TOML can't express what you need. See also `DESIGN-SYSTEM.md` (the current Databricks-flavoured one) — your replacement file follows the same outline.

---

## 1. Parameters to set

You will not know all of these up front — fill in §1.1 progressively as you read the brand guide. Per-page plans assume the values here are stable.

| Parameter | Where it lives | Notes |
|---|---|---|
| `brand_name` | `DESIGN-SYSTEM.md` title, `pyproject.toml` description, `app.py` page title | Display name of the brand. |
| `primary_color` | `brand-theme.toml` `primaryColor` | The single most-used accent / CTA colour from the brand guide. |
| `background_color` | `brand-theme.toml` `backgroundColor` | Page ground in light mode. |
| `secondary_background_color` | `brand-theme.toml` `secondaryBackgroundColor` | Sidebar, metrics, code blocks, expander interiors. |
| `text_color` | `brand-theme.toml` `textColor` | Body text in light mode. |
| `link_color` | `brand-theme.toml` `linkColor` | Hyperlinks; often same as `primary_color`. |
| `border_color` | `brand-theme.toml` `borderColor` | Input/widget borders, table grid lines. |
| `ui_font` | `brand-theme.toml` `font` + `headingFont` + `[[theme.fontFaces]]` | Body + heading font family. Must be a self-hostable font file (`.ttf` / `.woff2`). |
| `code_font` | `brand-theme.toml` `codeFont` + `[[theme.fontFaces]]` | Monospace family for code/IDs. Falls back to `monospace`. |
| Logo lockup file | `assets/logos/lockup-primary-color.svg` (or your filename) | Used by `st.logo(image=…)`; horizontal wordmark. |
| Logo symbol file | `assets/logos/<brand>-symbol-color.svg` | Used by `st.logo(icon_image=…)` and as favicon. |
| Semantic colours | `brand-theme.toml` `redColor` / `orangeColor` / `yellowColor` / `greenColor` / `blueColor` | `st.error` / `st.warning` / `st.success` / `st.info` pick these up automatically. |
| Chart palette (5–7 hex) | `brand-theme.toml` `chartCategoricalColors` | Skip the primary CTA colour so chart series do not compete with primary buttons. |
| Dark-mode overrides | `brand-theme.toml` `[theme.dark]` + `[theme.dark.sidebar]` | If the brand defines a dark theme; otherwise derive (see §3.3). |

### 1.1 Fill-in worksheet

- **`brand_name`** = `__________________`
- **`primary_color`** = `#__________`
- **`background_color`** (light) = `#__________`
- **`secondary_background_color`** = `#__________`
- **`text_color`** = `#__________`
- **`link_color`** = `#__________`
- **`border_color`** = `#__________`
- **`ui_font_family`** (CSS name, e.g. `Manrope`) = `__________________`
- **`ui_font_files`** (filenames under `static/fonts/`) = `__________________`
- **`code_font_family`** = `__________________`
- **`code_font_files`** = `__________________`
- **Lockup SVG filename** = `__________________`
- **Symbol SVG filename** = `__________________`
- **`redColor`** (errors) = `#__________`
- **`orangeColor`** = `#__________`
- **`yellowColor`** (warnings) = `#__________`
- **`greenColor`** (success) = `#__________`
- **`blueColor`** (info) = `#__________`
- **Chart categorical palette** = `[ "#____", "#____", "#____", "#____", "#____" ]`
- **Sidebar bg (light)** = `#__________`
- **Sidebar text (light)** = `#__________`

---

## 2. Overview

**What this plan produces.** A working themed Streamlit app on the existing starter, branded for *your* product instead of Databricks. The deliverables are exactly the same file set as the bundled Databricks system:

| File / dir | Purpose |
|---|---|
| `.streamlit/config.toml` | Enables static serving, points `[theme] base` at `brand-theme.toml`. Usually does not change between brands. |
| `.streamlit/brand-theme.toml` | All brand tokens — colours, fonts, sidebar, dark mode, chart palettes. The one file that changes most per brand. |
| `static/fonts/` | Self-hosted font files referenced from `[[theme.fontFaces]]`. |
| `assets/logos/` | Lockup + symbol SVGs used by `st.logo()` and the favicon. |
| `utils.init_page()` | Bootstrap shared by every page. Only the two `_LOGO_*` constants at the top change. |
| `DESIGN-SYSTEM.md` | Human-facing brand guide for the project. |
| `assets/styles.css` *(optional)* | Scoped `.st-key-*` overrides only when the TOML can't express what you need. |

**Why this architecture (recap from the skill).** Native Streamlit theme tokens handle colours, fonts, radii, sidebar, chart palettes, dark mode, dataframes, semantic alerts. Self-hosting fonts via `[[theme.fontFaces]]` avoids CDN dependencies and works in air-gapped Databricks Apps. A single `init_page()` is the only Python-side bootstrap so the look-and-feel never drifts per page. Scoped CSS with `.st-key-*` selectors is the *only* CSS layer that survives Streamlit upgrades — internal class hashes (`.st-emotion-cache-*`) rotate every release.

**What raw brand materials typically contain.** You need to extract the same set of values regardless of source format:

- A **brand guide / style guide** (PDF or web doc) listing primary colour, neutrals, semantic colours, typography rules.
- A **logo pack** — at minimum a horizontal lockup and a standalone symbol, ideally as SVG. Multiple colour treatments are nice-to-have (colour, mono navy, mono white, mono black).
- A **font file or licence** — either bundled font files or a clear licence statement (SIL OFL, Apache 2.0, commercial seat licence with redistribution rights). If only "Use Helvetica" is specified, see §3.2 — proprietary fonts cannot be redistributed.
- Optional: **chart / data-viz colour rules**, **dark-mode tokens**, **voice & tone**, **logo clear-space rules**, **iconography**.

**Effort estimate.** Reading the brand guide and filling §1.1 → 30 minutes. Producing `brand-theme.toml` + assets → 1–2 hours. Writing `DESIGN-SYSTEM.md` → 1 hour. Total: half a day for a brand that's well-documented; longer if you have to derive tokens or commission logos.

---

## 3. Prerequisites

### 3.1 Raw materials inventory

Before touching code, lay out the source documents and confirm each of the following is available (or note the gap and the mitigation):

| Required | Have it? | If not |
|---|---|---|
| Hex codes for primary, background, text | | Sample the brand's website with a colour-picker; confirm with the brand owner. |
| 2–3 neutral surface colours (sidebar, cards) | | Derive: lighten/darken the page background by 4–8% L\*. |
| Semantic colours (success / warning / error / info) | | Pick from Tailwind/Radix at a contrast-AA level against your background. |
| Heading + body font family and file | | See §3.2. |
| Monospace family for code | | Fall back to system `monospace`. |
| Lockup SVG + symbol SVG | | Commission them; do not crop a raster logo. SVG is essential for `st.logo()`. |
| Dark-mode tokens | | Optional — see §3.3 for derivation rules. |
| Chart palette | | Derive: take 4–6 hues at the same chroma/lightness, skipping the primary CTA. |

### 3.2 Fonts and licensing

Streamlit serves fonts from `static/fonts/` via `[[theme.fontFaces]]`. The files end up in your git repo and the deployed app, so the font's licence must allow redistribution.

- **SIL Open Font License (OFL)** — yes, redistribute freely. Bundle the `OFL.txt` next to the font. Examples: DM Sans (current default), Inter, IBM Plex Sans, Manrope, JetBrains Mono.
- **Apache 2.0 / MIT** — yes. Bundle the licence file.
- **Adobe Fonts / TypeKit** — no embedded distribution; you can only load via Adobe's web URLs, which breaks air-gapped deploys.
- **Commercial seat licences** (e.g. Monotype subscriptions) — varies. Read the EULA, and prefer a free-licensed near-equivalent for the open-source starter unless you have a *server* or *web embedding* licence that covers redistribution.

If the brand mandates a font you cannot redistribute:
1. Use the closest permissively-licensed substitute (`Inter` for `Helvetica/Aktiv Grotesk`, `IBM Plex Sans` for `Avenir`, `DM Sans` for `GT Walsheim`, etc.).
2. Document the substitution in `DESIGN-SYSTEM.md` so designers reading the repo know it is intentional.
3. Leave a hook for production builds to swap in the licensed font (env-var-controlled path, or a build-time copy step).

Variable fonts (`.ttf` with multiple weights packed) are ideal: one file covers the whole weight range. If you only have static files, declare a `[[theme.fontFaces]]` block per weight × style as the current Databricks setup does.

### 3.3 Deriving dark mode (if the brand guide is silent)

A workable starting point:

- `[theme.dark] backgroundColor` = the darkest brand neutral, or a deep version of the primary's complementary hue.
- `[theme.dark] textColor` = the lightest brand neutral (your light-mode `backgroundColor` is often a fine pick).
- `[theme.dark] primaryColor` = the light-mode primary lightened by 10–15% L\* so it still pops on the dark ground.
- `[theme.dark] secondaryBackgroundColor` = light-mode `textColor` taken about 5–10% lighter than `backgroundColor`.
- Mirror `[theme.sidebar]` into `[theme.dark.sidebar]` with the same darken-the-darkest pattern.

Validate every pair (text on bg, text on sidebar bg, primary on bg, link on bg) hits WCAG AA contrast (4.5:1 for body text, 3:1 for large text).

### 3.4 Claude Code prompt — extract tokens from a brand guide

If the brand guide is a PDF, drop it under `.local/brand-source/brand-guide.pdf` (gitignored) and paste this into Claude Code:

```text
I have a brand guide at .local/brand-source/brand-guide.pdf. Read it
and fill in §1.1 of docs/plans/0_B_design_system.md with the values
you find. For anything missing, list it under "Gaps" at the bottom of
§1.1 with a one-line note on how to derive it (cf. §3.1 / §3.3 of the
same doc).

Constraints:
- Hex values only for colours.
- Font family names exactly as the brand guide writes them; flag any
  font where the licence is unclear or proprietary.
- Do not invent semantic colours if the guide is silent — leave them
  blank and add a Gap entry.
- Do not change any other file yet.
```

Treat its output as a draft; verify each token against the source PDF before committing.

---

## 4. DAB / configuration updates

The shipped bundle already syncs the directories you'll use. Confirm `databricks.yml` does not exclude any of them — and the bundle currently does not, so this section is largely a sanity check.

### 4.1 Sync includes you depend on

`databricks.yml` ships with these implicitly included (no entry in `sync.exclude`):

- `.streamlit/` — required at runtime; Streamlit reads `config.toml` on boot.
- `static/` — fonts served via `enableStaticServing`.
- `assets/` — logos resolved relative to the app's working directory by `st.logo()`.

Do **not** add any of these to `sync.exclude`. If you reorganise to e.g. `static/logos/`, update `_LOGO_LOCKUP` / `_LOGO_SYMBOL` in `utils.py` accordingly.

### 4.2 Bundle variables

No new bundle variables are required. The design system is fully static — no warehouse, no per-environment resource binding. Per-page plans continue to add their own variables.

### 4.3 Redeploy after asset swap

```bash
databricks bundle deploy -t dev
databricks bundle run streamlit-demo -t dev
```

The Apps runtime restarts Streamlit, which re-reads `brand-theme.toml`. Theme TOML is not hot-reloaded — restart is required.

---

## 5. Source code updates

All paths below are relative to the repo root. Do these in order; each step is independently testable.

### 5.1 Place the font files

```bash
mkdir -p static/fonts
cp /path/to/your-font-files/*.ttf static/fonts/
cp /path/to/your-font-license/OFL.txt static/fonts/   # or LICENSE.txt for Apache/MIT
```

Verify with `ls static/fonts/` — the filenames you use here become the URLs in step 5.3.

### 5.2 Place the logo files

```bash
mkdir -p assets/logos
cp /path/to/lockup.svg  assets/logos/lockup-primary-color.svg
cp /path/to/symbol.svg  assets/logos/<brand>-symbol-color.svg
```

SVG is strongly preferred — `st.logo()` accepts PNG too but rasterised lockups look bad on retina screens. Strip any embedded XML comments and `viewBox="0 0 ..."` outliers via `svgo` before committing if the files are bloated.

### 5.3 Rewrite `.streamlit/brand-theme.toml`

Replace the file content with your brand's tokens. Skeleton:

```toml
# <brand_name> Brand Theme for Streamlit
# Anchors: <primary>, <text>, <background>

[[theme.fontFaces]]
family = "<ui_font_family>"
url = "app/static/fonts/<your-font-regular>.ttf"
weight = 400
style = "normal"

# Repeat one [[theme.fontFaces]] block per weight × style you ship.
# A single variable-font .ttf can cover the whole weight range with one block.

[[theme.fontFaces]]
family = "<code_font_family>"
url = "app/static/fonts/<your-code-font-regular>.ttf"
weight = 400
style = "normal"

[theme]
base = "light"

font = "<ui_font_family>, sans-serif"
headingFont = "<ui_font_family>, sans-serif"
codeFont = "<code_font_family>, monospace"
baseFontSize = 16
baseFontWeight = 400

primaryColor = "<primary_color>"
backgroundColor = "<background_color>"
secondaryBackgroundColor = "<secondary_background_color>"
textColor = "<text_color>"

linkColor = "<link_color>"
linkUnderline = false
codeTextColor = "<text_color>"
codeBackgroundColor = "<secondary_background_color>"

borderColor = "<border_color>"
showWidgetBorder = true
showSidebarBorder = true
baseRadius = "md"
buttonRadius = "md"

dataframeHeaderBackgroundColor = "<secondary_background_color>"
dataframeBorderColor = "<border_color>"

chartCategoricalColors = ["<c1>", "<c2>", "<c3>", "<c4>", "<c5>"]
chartSequentialColors  = ["<l1>", "<l2>", "<l3>", "<l4>", "<l5>"]
chartDivergingColors   = ["<d1>", "<d2>", "<d3>", "<d4>", "<d5>"]

redColor    = "<red>"
orangeColor = "<orange>"
yellowColor = "<yellow>"
greenColor  = "<green>"
blueColor   = "<blue>"
violetColor = "<violet>"
grayColor   = "<gray>"

[theme.sidebar]
backgroundColor          = "<sidebar_bg_light>"
secondaryBackgroundColor = "<sidebar_secondary_bg_light>"
textColor                = "<sidebar_text_light>"
linkColor                = "<primary_color>"
showWidgetBorder         = true

[theme.dark]
primaryColor             = "<primary_dark>"
backgroundColor          = "<bg_dark>"
secondaryBackgroundColor = "<secondary_bg_dark>"
textColor                = "<text_dark>"
linkColor                = "<primary_dark>"
codeTextColor            = "<text_dark>"
codeBackgroundColor      = "<code_bg_dark>"
borderColor              = "<border_dark>"
dataframeBorderColor     = "<border_dark>"
showWidgetBorder         = true

[theme.dark.sidebar]
backgroundColor          = "<sidebar_bg_dark>"
secondaryBackgroundColor = "<sidebar_secondary_bg_dark>"
textColor                = "<sidebar_text_dark>"
linkColor                = "<primary_dark>"
```

### 5.4 Confirm `.streamlit/config.toml`

The shipped `config.toml` is brand-agnostic and should not need editing:

```toml
[server]
enableStaticServing = true

[theme]
base = ".streamlit/brand-theme.toml"

[browser]
gatherUsageStats = false

[client]
toolbarMode = "minimal"
```

### 5.5 Point `utils.py` at the new logos

Open `utils.py` and edit the two constants at the top:

```python
_LOGO_LOCKUP = "assets/logos/lockup-primary-color.svg"
_LOGO_SYMBOL = "assets/logos/<brand>-symbol-color.svg"
```

…and the `link` argument inside `init_page()` if you want clicking the logo to go somewhere other than `https://www.databricks.com`:

```python
st.logo(
    _LOGO_LOCKUP,
    icon_image=_LOGO_SYMBOL,
    link="https://<your-product>.example.com",
)
```

No other code changes are needed. Every page already calls `init_page()` and inherits the new branding automatically.

### 5.6 Rewrite `DESIGN-SYSTEM.md`

Use the existing `DESIGN-SYSTEM.md` (Databricks flavour) as a template — same eight sections, populated with your brand's values:

1. **Header** — brand pillars, voice, type, colour anchors.
2. **What's in the repo** — same file tree (probably unchanged).
3. **Colour** — anchors table, extended palette table, semantic bindings, pairing do/don't, chart guidance.
4. **Typography** — families, token wiring, scale table, casing & voice.
5. **Logo & favicon** — variant inventory, rules (minimum size, clear space).
6. **Page bootstrap pattern** — describe `init_page()` (unchanged from the Databricks version).
7. **Scoped CSS — only when TOML cannot** — copy the same "What to avoid" list from the skill.
8. **Light & dark mode** — token table.
9. **Updating the brand** — describes this very loop.

If the brand owner cannot answer voice/tone questions, copy the skill's defaults: "confident, technical, plain declarative sentences, address the reader as you" and flag for review.

### 5.7 Optional: scoped CSS

Only add `assets/styles.css` if you have a concrete need the TOML cannot express:

- A button variant beyond Streamlit's built-in `primary` / `secondary` / `tertiary`.
- A card container shape.
- Page-specific spacing the theme tokens don't expose.

Pattern: every CSS rule must select on a `.st-key-<your-key>` class (created by passing `key="<your-key>"` to the Streamlit widget). Anything else is fragile across Streamlit minor versions. Wire the file in via `st.html(Path("assets/styles.css").read_text())` inside `init_page()` — *not* a second bootstrap function.

---

## Verification

1. **TOML parses**
   ```bash
   uv run python -c "import tomllib, pathlib; tomllib.loads(pathlib.Path('.streamlit/brand-theme.toml').read_text())"
   ```
   Catches obvious syntax errors before Streamlit prints them.

2. **Static check**
   ```bash
   uv run python -m py_compile app.py utils.py
   ```

3. **Local smoke**
   ```bash
   uv run streamlit run app.py --server.headless true --server.port 18501
   ```
   Watch the boot log for `Failed to load custom theme`, `Could not load font`, or 404s on `app/static/fonts/...`. Open the URL and confirm:
   - The new logo appears top-left in the sidebar.
   - Body and heading text use your UI font (browser devtools → Computed → `font-family`).
   - Primary buttons use `primaryColor`.
   - The sidebar background uses the sidebar palette.
   - `st.success` / `st.error` use the new semantic colours.

4. **Both modes**
   - In the Streamlit settings menu (top-right ☰), switch between *Light* and *Dark*.
   - Verify there's no unreadable text or invisible borders in either mode.

5. **Bundle validate + deploy**
   ```bash
   databricks bundle validate -t dev
   databricks bundle deploy  -t dev
   databricks bundle run streamlit-demo -t dev
   ```
   The remote app must boot and render the same theming. Fonts that 404 locally will also 404 in Databricks Apps — `enableStaticServing` is enforced identically.

6. **Cross-page** — click into `pages/0_empty.py` and confirm the brand is applied there too (proves `init_page()` is the only bootstrap and there's no per-page drift).

---

## What to avoid

These break across Streamlit upgrades or fight the native theming layer (mirrored from the `streamlit-custom-style` skill):

- Hashed class selectors in CSS (`.st-emotion-cache-*`) — they rotate every minor.
- Global element selectors (`button { }`, `h1 { }`) — use theme tokens instead.
- `@import` for fonts — use `[[theme.fontFaces]]`.
- `st.markdown(unsafe_allow_html=True)` for CSS — use `st.html()`.
- A second branding entry point alongside `init_page()`.
- Python-side chart themes for native `st.line_chart` — they already read `chartCategoricalColors`.

---

## Where this slots into the plan ladder

```
0_A_initial_setup.md      ← run once: scaffolding (utils, app.py, app.yaml, databricks.yml)
0_B_design_system.md    ← THIS PLAN: replace Databricks design with your brand
1_sample_data_page.md   ← per-page plan (adds one Streamlit page + its resources)
…                       ← further per-page plans
```

Per-page plans depend on `init_page()` being wired up by `0_A_initial_setup.md`. They do not depend on which brand is loaded — swapping brands later does not require touching any per-page plan.
