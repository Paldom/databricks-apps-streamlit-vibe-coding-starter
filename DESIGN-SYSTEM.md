# Databricks Design System — Streamlit Adaptation

How this project ships a Databricks-branded look-and-feel using Streamlit's native theming layer. Follow the patterns here and every page in the app stays brand-consistent with no per-page CSS.

> **Brand pillars:** distilled · bold · fresh
> **Voice:** confident, technical, optimistic
> **Type:** DM Sans (UI) + DM Mono (code)
> **Anchors:** Lava 600 `#FF3621` · Navy 800 `#1B3139` · Oat Light `#F9F7F4`

---

## 1. What's in the repo

```
.streamlit/
├─ config.toml             # Streamlit project config; turns on static serving
└─ brand-theme.toml        # All brand tokens — colours, fonts, sidebar, dark mode
static/
└─ fonts/                  # DM Sans (4 weights + italics) + DM Mono (3 weights + italic)
   └─ OFL.txt              # SIL Open Font License — required when redistributing
assets/
└─ logos/                  # 10 Databricks lockup / symbol variants in 4 colour treatments
utils.py                   # init_page() — single bootstrap for every page
app.py                     # Calls init_page()
pages/
└─ 0_empty.py              # Template page; also calls init_page()
```

Streamlit's native theme API does ~90% of the work here:

- Fonts are self-hosted via `[[theme.fontFaces]]` and served from `static/` (Streamlit's static serving is on).
- All colour / radius / chart-palette tokens live in `.streamlit/brand-theme.toml` so a single edit re-skins the whole app.
- `utils.init_page()` wires `st.set_page_config()`, `st.logo()`, and the signed-in user badge in one call — no parallel "branding" bootstrap.

No scoped CSS is shipped today. Add a small `assets/styles.css` only when the TOML can't express what you need; restrict its selectors to `.st-key-*` so it survives Streamlit upgrades (see §6).

---

## 2. Colour

### Anchors

| Role | Token | Hex |
|---|---|---|
| Primary CTA / focus / links | Lava 600 | `#FF3621` |
| Body text / heading | Navy 800 | `#1B3139` |
| Page ground (light mode) | Oat Light | `#F9F7F4` |
| Sidebar, metrics, code, cards | Oat Medium | `#EEEDE9` |

### Extended palette

| Family | Default | Extras (300 / 500 / 700) |
|---|---|---|
| Lava | `#FF3621` | `#FF5F46` (500) · `#BD2B26` (700) |
| Navy | `#1B3139` | `#C4CCD6` (300) · `#1B5162` (600) · `#143D4A` (700) · `#0B2026` (900) |
| Green | `#00A972` | `#00875C` (700) |
| Yellow | `#FFAB00` | `#BA7B23` (700) |
| Blue | `#2272B4` | `#0E538B` (700) |
| Maroon | `#98102A` | — |

### Semantic colour bindings

`st.success`, `st.warning`, `st.error`, and `st.info` pick up the semantic colour tokens from `brand-theme.toml`:

| Streamlit | TOML token | Hex |
|---|---|---|
| `st.success` | `greenColor` | `#00875C` |
| `st.warning` | `yellowColor` | `#BA7B23` |
| `st.error` | `redColor` | `#BD2B26` (Lava 700) |
| `st.info` | `blueColor` | `#2272B4` |

### Pairing rules

- ✓ Navy 800 ground + Oat Light text + Lava 600 accent.
- ✓ Oat Light ground + Navy 800 text + Lava 600 accent.
- ✓ Oat Medium card on Oat Light ground (no shadow needed).
- ✗ Lava 600 on Lava 700 (vibrates).
- ✗ Yellow 600 with white text (fails contrast).
- ✗ Two extended-palette accents in one view.

### Charts

Native Streamlit charts (`st.line_chart`, `st.bar_chart`, `st.area_chart`) inherit `chartCategoricalColors` / `chartSequentialColors` / `chartDivergingColors` from `brand-theme.toml` automatically — **no Python helper required**. The categorical palette intentionally skips Lava so chart series do not compete with primary CTAs.

If you add a Plotly or Altair page later, do **not** call `st.line_chart` substitutes. Instead, build a small `chart_themes.py` helper that reads the same hex values and exposes a Plotly `template=` or `alt.themes.register("databricks", ...)` callable. Only add this helper when a non-native chart is actually used — see *What to avoid* in §6.

---

## 3. Typography

### Families

| Family | Files (in `static/fonts/`) | Use |
|---|---|---|
| DM Sans | `dm-sans-{regular,italic,medium,medium-italic,bold,bold-italic}.ttf` | UI, headings, body |
| DM Mono | `dm-mono-{light,regular,italic,medium}.ttf` | Code, IDs, technical labels |

Both are SIL OFL — see `static/fonts/OFL.txt`. Safe to redistribute with the app.

### Token wiring

Set once in `brand-theme.toml`:

```toml
font = "DM Sans, sans-serif"
headingFont = "DM Sans, sans-serif"
codeFont = "DM Mono, monospace"
baseFontSize = 16
baseFontWeight = 400
```

Streamlit auto-applies these to body text, headings (`st.title` / `st.header` / `st.subheader`), inline code, and code blocks. No `@font-face` block in a separate CSS file — the `[[theme.fontFaces]]` arrays in `brand-theme.toml` register the fonts directly.

### Scale (Databricks reference)

| Role | Size | Weight | Notes |
|---|---|---|---|
| H1 (`st.title`) | 44 px | 500 | weight 500, not 700 — the Databricks tell |
| H2 (`st.header`) | 32 px | 500 | |
| H3 (`st.subheader`) | 24 px | 500 | |
| Body | 16 px | 400 | |
| Caption (`st.caption`) | 12 px | 400 | |

Streamlit defaults are within 1–2 px of these. Override only if a page diverges significantly.

### Casing & voice

- **Sentence case** for headings, buttons, labels: *"Get started"*, *"Build AI agents"*.
- **TitleCase** for product nouns only: *Unity Catalog*, *Delta Lake*, *Genie*, *Mosaic AI*, *Lakebase*, *Databricks Apps*, *Model Serving*.
- **Databricks** capitalised in running text; the wordmark itself is always lowercase.
- Confident, technical, optimistic. Plain declarative sentences. Address the reader as **you**; **we / our** sparingly; never **I**. No emoji. No exclamation points outside event copy.

---

## 4. Logo & favicon

`assets/logos/` ships 10 variants:

| File | Use |
|---|---|
| `databricks-symbol-color.svg` | Standalone bricks mark — favicon, `st.logo(icon_image=…)` |
| `databricks-symbol-navy.svg` | Symbol, Navy 800 — single-colour contexts on light bg |
| `databricks-symbol-light.svg` | Symbol, Oat Light — on Navy surfaces |
| `lockup-primary-color.svg` | Wordmark + symbol, horizontal — default for `st.logo(image=…)` |
| `lockup-primary-navy.svg` | Wordmark + symbol, all Navy — monochrome contexts |
| `lockup-primary-white.svg` | Wordmark + symbol, all white — on Navy / photography |
| `lockup-primary-black.svg` | Wordmark + symbol, all black — print, low-colour reproduction |
| `lockup-stacked-color.svg` | Wordmark below symbol — square aspect, splash screens |
| `lockup-stacked-navy.svg` | Stacked, monochrome navy |
| `lockup-stacked-white.svg` | Stacked, white |

`init_page()` wires the colour lockup + colour symbol via `st.logo()` and the symbol again as the favicon. Override per-page with `init_page(page_icon=...)` only when there is a clear reason.

**Rules:** minimum 24 px for the standalone symbol; 80 px wide for the primary lockup; 48 px tall for the stacked lockup. Clear space ≥ the height of the "d" in `databricks` on every side.

---

## 5. Page bootstrap pattern

Every page calls `init_page()` from `utils.py` as its very first Streamlit command:

```python
import streamlit as st
from utils import init_page

init_page(page_title="My Page")

st.title("My Page")
st.write("…")
```

`init_page()` runs `st.set_page_config()`, registers the Databricks lockup + symbol via `st.logo()`, and renders the signed-in user badge in the sidebar. There is intentionally no parallel `apply_branding()` / `setup_brand()` helper — one bootstrap, one place to update when the design system evolves.

If you need to override the icon or layout for a specific page:

```python
init_page(page_title="Wide Editor", layout="wide", page_icon="assets/logos/databricks-symbol-navy.svg")
```

---

## 6. Scoped CSS — only when TOML cannot

The TOML theme covers buttons, links, sidebar, metrics, expanders, tabs, alerts, dataframes, code blocks, focus rings, and chart palettes. For everything else — custom button variants beyond the built-in `primary` / `secondary` / `tertiary`, card containers, special-purpose spacing — use **keyed CSS** with `.st-key-*` selectors so the rule survives Streamlit upgrades:

```python
st.button("Delete", key="warning")
st.button("Confirm", key="success")
```

```css
.st-key-warning button {
  background-color: #BD2B26;  /* Lava 700 */
  color: #FFFFFF;
}
.st-key-success button {
  background-color: #00875C;  /* Green 700 */
  color: #FFFFFF;
}
```

Load such CSS from `assets/styles.css` via `st.html()` inside `init_page()` (don't add a second bootstrap). Add the file only when at least one such rule is needed — premature scoped CSS files are dead weight.

### Patterns to avoid

These break across Streamlit upgrades or fight the native theming layer:

- Global element selectors (`button { }`, `h1 { }`, `input[type=checkbox] { }`).
- Hashed class selectors (`.css-18ni7ap`, `.st-emotion-cache-*`) — they rotate on every release.
- Internal attribute selectors (`button[kind="secondary"]`) — use Streamlit's native `type="secondary"` parameter.
- CSS `@import` for fonts — use `[[theme.fontFaces]]`.
- `st.markdown(..., unsafe_allow_html=True)` for CSS — use `st.html()`.
- A second branding entry point alongside `init_page()`.
- Python chart-theme helpers for native `st.line_chart` / `st.bar_chart` — they already read the TOML palette.

---

## 7. Light & dark mode

Both modes are defined in `brand-theme.toml`. Users switch via Streamlit's settings menu (top-right).

| | Light | Dark |
|---|---|---|
| Ground | Oat Light `#F9F7F4` | Navy 800 `#1B3139` |
| Secondary bg | Oat Medium `#EEEDE9` | Navy 700 `#143D4A` |
| Text | Navy 800 `#1B3139` | Oat Light `#F9F7F4` |
| Primary | Lava 600 `#FF3621` | Lava 500 `#FF5F46` (brighter for contrast on Navy) |
| Sidebar bg | Oat Medium `#EEEDE9` | Navy 900 `#0B2026` |

If you change a token, change it in **both** sections. There is no automatic derivation.

---

## 8. Updating the brand

1. Edit `.streamlit/brand-theme.toml` — colours, fonts, radii, semantic tokens, chart palettes.
2. If swapping logo assets, replace files under `assets/logos/` keeping the same filenames, **or** update the two path constants at the top of `utils.py` (`_LOGO_LOCKUP`, `_LOGO_SYMBOL`).
3. Restart the Streamlit server (`uv run streamlit run app.py`) — theme TOML is read at startup.
4. Verify across the home page and at least one feature page; check both light and dark modes.

That's the whole loop. No CSS edits, no per-page changes.
