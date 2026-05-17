---
name: streamlit-custom-style
description: How to custom-style a Streamlit application with a modern, stable theming stack — reusable theme TOML files, self-hosted fonts, light/dark modes, sidebar theming, chart palettes, shared page bootstrap, and scoped CSS for custom component variants. Use this skill PROACTIVELY whenever the user wants to style, theme, brand, or customize the appearance of a Streamlit app — including changing colors, fonts, buttons, sidebar look, dark mode, chart colors, or adding custom CSS. Also use when the user mentions config.toml theming, Streamlit design systems, or asks how to make a Streamlit app look professional/branded. Even if the user only asks about one aspect (e.g. "change the sidebar color"), apply this skill because the answer depends on which styling layer is appropriate.
license: MIT
metadata:
  version: "0.1.0"
---

# Streamlit Custom Styling

Style Streamlit apps using a layered approach that prioritizes stability. Native theme config handles 90% of the work; scoped CSS handles the rest. Avoid global CSS selectors and `unsafe_allow_html`.

## The styling layers (in order of stability)

| Layer | What | Stability | When to use |
|-------|------|-----------|-------------|
| 1. Native theme config | `.streamlit/config.toml` + reusable theme TOML | Highest | Colors, fonts, borders, radii, chart palettes, light/dark, sidebar |
| 2. Shared bootstrap | `helpers.py` with `init_page()` | High | Page config, logo, CSS loading — consistent across all pages |
| 3. Scoped CSS | `.st-key-*` selectors only | Medium | Custom button variants, card containers, spacing that config can't express |
| 4. DOM-targeted CSS | Generic element selectors | Low | Avoid unless absolutely necessary — breaks across Streamlit upgrades |

The guiding principle: **use the highest layer that can express what you need**. Drop to a lower layer only when the higher one genuinely can't do it.

## Layer 1: Native theme config

### Architecture

Split config into two files:

**`.streamlit/config.toml`** — project-level config, references the theme file:

```toml
[server]
enableStaticServing = true

[theme]
base = ".streamlit/brand-theme.toml"
```

`enableStaticServing = true` is required when self-hosting fonts from `static/`.

**`.streamlit/brand-theme.toml`** — the reusable visual system. This file can be shared across multiple Streamlit apps for consistent branding.

See `references/brand-theme-template.toml` for the full annotated template with all available tokens.

### Key theme tokens

**Colors:** `primaryColor`, `backgroundColor`, `secondaryBackgroundColor`, `textColor`, `linkColor`, `codeTextColor`, `codeBackgroundColor`, `borderColor`

**Typography:** `font`, `headingFont`, `codeFont`, `baseFontSize`, `baseFontWeight`

**Borders and radii:** `showWidgetBorder`, `baseRadius`, `buttonRadius`, `borderColor`, `dataframeBorderColor`

**Chart palettes:** `chartCategoricalColors`, `chartSequentialColors`, `chartDivergingColors`

**Semantic colors:** `redColor`, `orangeColor`, `yellowColor`, `greenColor`, `blueColor`, `violetColor`, `grayColor`

**DataFrame:** `dataframeHeaderBackgroundColor`, `dataframeBorderColor`

### Custom fonts

Self-host fonts in `static/fonts/` to avoid CDN dependencies and privacy/compliance risks:

```toml
[[theme.fontFaces]]
family = "Manrope"
url = "app/static/fonts/Manrope-VariableFont_wght.ttf"
style = "normal"
```

Then reference it: `font = "Manrope, sans-serif"`.

The URL path starts with `app/static/` because Streamlit serves the `static/` directory at that URL prefix when `enableStaticServing = true`.

### Light/dark themes

Define both in the theme file. Users can switch in the Streamlit settings menu:

```toml
[theme]
primaryColor = "#5FB79B"
backgroundColor = "#FFFFFF"
textColor = "#12283F"

[theme.dark]
primaryColor = "#7CCDB1"
backgroundColor = "#0E1117"
textColor = "#F8FAFC"
```

Tip: lighten the primary color slightly for dark mode to maintain contrast.

### Sidebar theming

The sidebar can have its own color scheme independent of the main content area:

```toml
[theme.sidebar]
backgroundColor = "#12283F"
textColor = "#F8FAFC"
linkColor = "#8AD7BF"

[theme.dark.sidebar]
backgroundColor = "#0B1220"
textColor = "#F8FAFC"
```

### Chart palettes

Define branded palettes so native charts automatically use your colors:

```toml
chartCategoricalColors = ["#5FB79B", "#12283F", "#3C6E71", "#E7A83B", "#D96B6B"]
chartSequentialColors = ["#F0FAF6", "#D8F1E7", "#B9E4D3", "#92D2B8", "#5FB79B"]
chartDivergingColors = ["#D96B6B", "#F3D6D6", "#F6F8FA", "#D6ECE4", "#5FB79B"]
```

Charts (`st.line_chart`, `st.bar_chart`, etc.) inherit these automatically — no per-chart configuration needed.

**TOML is the right layer only for native Streamlit charts.** If the app uses Plotly, Altair, or Matplotlib directly, those libraries do **not** read `chartCategoricalColors` — they need their own `template` / `theme` configured in Python. In that case, add a small helper (e.g., `chart_themes.py`) that reads the same palette and exposes a Plotly template or Altair theme. Don't preemptively introduce such helpers when the app only uses `st.line_chart` / `st.bar_chart` — that's premature abstraction.

## Layer 2: Shared bootstrap

Create a single `init_page()` function that every page calls before any visual output. This prevents per-page drift in config, logo, and style loading:

```python
from pathlib import Path
import streamlit as st


def _load_css(path: str | Path = "assets/styles.css") -> None:
    css_path = Path(path)
    if css_path.exists():
        st.html(f"<style>{css_path.read_text(encoding='utf-8')}</style>")


def init_page(
    page_title: str = "My App",
    page_icon: str = "images/logo_closed.svg",
    layout: str = "wide",
    sidebar_state: str = "expanded",
    load_css: bool = True,
) -> None:
    st.set_page_config(
        page_title=page_title,
        page_icon=page_icon,
        layout=layout,
        initial_sidebar_state=sidebar_state,
    )
    if load_css:
        _load_css()
    st.logo("images/logo.svg", icon_image="images/logo_closed.svg")
```

Key details:
- Use `st.html()` for CSS injection, not `st.markdown(..., unsafe_allow_html=True)`. It's cleaner and the recommended approach.
- `st.logo()` supports a separate `icon_image` for the collapsed sidebar state.
- Every page should call `init_page(page_title="Page Name")` as its first action.
- **Wire logo and favicon through `init_page()` — don't add a parallel `apply_branding()` or `setup_brand()` bootstrap.** A second entry point invites drift (two places to update fonts, two places to register the logo). If you adopt a new brand asset set, swap the file paths inside `init_page()` and the theme TOML; keep the bootstrap shape.

## Layer 3: Scoped CSS

Keep the CSS file intentionally small. Only use `.st-key-*` selectors — these are stable because the `key` parameter is user-controlled and won't change with Streamlit upgrades.

### Custom button variants

Streamlit has three built-in button types: `primary`, `secondary`, `tertiary`. For additional brand variants, use keyed CSS:

```python
st.button("Delete", key="warning")
st.button("Confirm", key="success")
st.button("More info", key="outline")
```

```css
.st-key-warning button {
  background-color: #C14545;
  color: #FFFFFF;
  border-color: #C14545;
}
.st-key-warning button:hover {
  background-color: #A93636;
  color: #FFFFFF;
}
```

### Card containers

```python
with st.container(key="card"):
    st.subheader("Card title")
    st.write("Card content")
```

```css
.st-key-card {
  border: 1px solid #D7E2EA;
  border-radius: 1rem;
  padding: 1rem;
}
```

See `references/scoped-css-patterns.md` for the complete pattern library.

## What to avoid

These patterns are fragile and break across Streamlit version upgrades:

- **Global element selectors** (`button { }`, `h1 { }`, `p { }`, `input[type=checkbox] { }`) — the theme config handles typography and widget styling natively.
- **Internal attribute selectors** (`button[kind="secondary"]`) — use Streamlit's native `type="secondary"` parameter instead.
- **Hashed class selectors** (`.css-18ni7ap`, `.st-emotion-cache-*`) — these rotate on every Streamlit release.
- **CSS `@import` for fonts** — use `[[theme.fontFaces]]` in the theme TOML instead.
- **`st.markdown(..., unsafe_allow_html=True)` for CSS** — use `st.html()`.
- **Bootstrap or framework injection** — heavy and conflicts with Streamlit's own styles.
- **A second branding entry point** (e.g., `apply_branding()` alongside `init_page()`) — duplicates responsibility and drifts. Extend `init_page()` instead.
- **Python-side chart theming for native Streamlit charts** — `st.line_chart` / `st.bar_chart` already read `chartCategoricalColors` from the TOML; wrapping them in a helper is dead weight. Only add a Python chart-theme helper when the app calls Plotly / Altair / Matplotlib directly.

## File structure

A well-organized Streamlit app with custom styling:

```
.streamlit/
  config.toml              # References brand-theme.toml
  brand-theme.toml         # All theme tokens: colors, fonts, dark mode, sidebar
static/
  fonts/
    YourFont.ttf           # Self-hosted font files
assets/
  styles.css               # Tiny, scoped CSS — only .st-key-* rules
images/
  logo.svg                 # Sidebar logo (expanded)
  logo_closed.svg          # Sidebar logo (collapsed)
helpers.py                 # Shared init_page() bootstrap
Home.py                    # Main entry point
pages/
  01_Page.py               # Each page calls init_page()
requirements.txt           # Pin streamlit to a minor version
```

## Version discipline

Pin Streamlit to a minor version range (e.g., `streamlit>=1.55,<1.56`). CSS selectors and DOM structure can change between minor versions, so test before upgrading.

## Quick decision guide

| "I want to..." | Use |
|---|---|
| Change app colors | `brand-theme.toml` — `primaryColor`, `backgroundColor`, etc. |
| Add a custom font | `[[theme.fontFaces]]` + `static/fonts/` + `font = "..."` |
| Support dark mode | `[theme.dark]` section in brand-theme.toml |
| Style the sidebar | `[theme.sidebar]` section |
| Brand my charts | `chartCategoricalColors` / `chartSequentialColors` / `chartDivergingColors` |
| Add a logo | `st.logo()` in `init_page()` |
| Create a warning/success button | `key="warning"` + `.st-key-warning` CSS |
| Make a card container | `st.container(key="card")` + `.st-key-card` CSS |
| Style widget borders | `showWidgetBorder = true` + `borderColor` in theme |
| Set button shape | `buttonRadius = "full"` or `"md"` or `"none"` |
| Adjust heading size | `headingFont`, and heading size tokens if available |
