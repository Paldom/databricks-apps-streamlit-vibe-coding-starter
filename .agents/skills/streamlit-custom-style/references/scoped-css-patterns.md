# Scoped CSS Patterns

All CSS in a styled Streamlit app should use `.st-key-*` selectors. These are stable because the `key` parameter is controlled by your Python code and won't change with Streamlit upgrades.

## How it works

When you pass `key="something"` to a Streamlit widget, Streamlit wraps it in a container with class `.st-key-something`. You can target this in CSS.

## Button variants

Streamlit has three built-in types: `primary`, `secondary`, `tertiary`. For additional variants:

### Warning / destructive

```python
st.button("Delete item", key="warning")
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

### Success / confirm

```python
st.button("Approve", key="success")
```

```css
.st-key-success button {
  background-color: #228B5D;
  color: #FFFFFF;
  border-color: #228B5D;
}
.st-key-success button:hover {
  background-color: #1C734D;
  color: #FFFFFF;
}
```

### Outline / ghost

```python
st.button("Learn more", key="outline")
```

```css
.st-key-outline button {
  background-color: transparent;
  color: inherit;
  border-width: 1px;
}
```

## Container variants

### Card

```python
with st.container(key="card"):
    st.subheader("Title")
    st.write("Content in a card-like container.")
```

```css
.st-key-card {
  border: 1px solid #D7E2EA;
  border-radius: 1rem;
  padding: 1rem;
}
```

### Highlighted section

```python
with st.container(key="highlight"):
    st.info("Important callout content")
```

```css
.st-key-highlight {
  background-color: #F0FAF6;
  border-left: 4px solid #5FB79B;
  padding: 1rem;
  border-radius: 0.5rem;
}
```

## Input variants

### Compact text input

```python
st.text_input("Search", key="compact-input")
```

```css
.st-key-compact-input input {
  padding: 0.25rem 0.5rem;
  font-size: 0.875rem;
}
```

## Rules for scoped CSS

1. **Always use `.st-key-*` selectors.** Never target bare elements (`button`, `h1`, `input`).
2. **Include hover states** for interactive elements.
3. **Keep colors consistent** with your brand-theme.toml values.
4. **Keep the file small.** If it grows past ~50 rules, reconsider whether some can move to theme config.
5. **Target the inner element.** For buttons: `.st-key-x button`. For inputs: `.st-key-x input`. The `.st-key-x` class is on the wrapper, not the widget itself.
6. **Use `!important` sparingly.** It's usually not needed with `.st-key-*` selectors since they have sufficient specificity.

## Anti-patterns

```css
/* BAD: Global selector — will affect every button in the app */
button { background-color: red; }

/* BAD: Internal attribute — not part of public API */
button[kind="secondary"] { ... }

/* BAD: Hashed class — changes every Streamlit release */
.css-18ni7ap { ... }
.st-emotion-cache-abc123 { ... }

/* GOOD: Keyed selector — stable */
.st-key-warning button { background-color: red; }
```
