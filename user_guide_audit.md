# UI Analysis — `user-guide.html` (truncated at line ~80)

**Source scope:** only the head/CSS and the page chrome (skip link, header, nav, wrapper opening) are present in the supplied excerpt. All analysis below is constrained to that visible portion — nothing is inferred from the unseen body of `user-guide.html`.

---

## 1. Visual Appearance

### Colors (literals only)

**Light mode palette (hex verified from CSS):**
- `#0059b3` — skip-link background, nav link text, nav focus outline, note left-border, back-to-top background
- `#fff` — skip-link text, nav background, card background, focus outline (generic), back-to-top text, back-to-top focus outline
- `#1d1d1f` — body text, header background, h2/h3 text, code text, kbd text, note/tip text
- `#f5f5f7` — body background, header text
- `#a0a0a6` — header subtitle text
- `#b0b0b5` — nav bottom border, card border, kbd border, table borders
- `#e0e0ea` — inline code background
- `#8e8e93` — kbd border
- `#e8e8f0` — kbd background, table header background
- `#eeeef3` — even table row background
- `#3a3a3c` — table caption text
- `#cfe2ff` — `.note` background (light blue)
- `#d6f0e8` — `.tip` background (light green)
- `#00704f` — `.tip` left-border (green)
- `rgba(0,0,0,.25)` — back-to-top box-shadow

**Dark mode palette:**
- `#000` body background, `#161617` header, `#1c1c1e` nav/card, `#48484a` borders, `#6eb3ff` accent, `#3c3c42` code/kbd, `#636366` kbd border, `#ebebf5` caption, `#2c2c2e` th background, `#272729` even row, `#102244` note background, `#4dc99a` tip border, `#0d2e22` tip background.

**Forced-colors tokens (Windows High Contrast mode):** `Highlight`, `Canvas`, `CanvasText`, `ButtonFace`, `ButtonText`, `HighlightText` — system/system theme tokens; exact hex unavailable from this file.

### Typography
- Body uses a system font stack: `-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif` (not a single named family — explicit fallback chain).
- Code/kbd use an explicit monospace stack: `"SF Mono", "Fira Code", Menlo, monospace`.
- H1: 2rem, weight 700, letter-spacing −0.02em.
- H2: 1.4rem, weight 700, letter-spacing −0.01em.
- H3: 1.1rem, weight 600.
- Body: 1rem / line-height 1.7.
- Subtitle 1rem, nav 0.875rem, cards content 1rem, table 0.9375rem, caption 0.9rem, note/tip 0.9375rem, back-to-top 0.875rem, skip-link 0.9rem.

### Spacing (literal values from CSS)
- `.wrapper`: `padding: 2rem 1.5rem 4rem`; `max-width: 860px`.
- `header`: `padding: 2rem 1.5rem`.
- `.card`: `padding: 1.75rem 2rem`; `margin-bottom: 1.5rem`; `border-radius: 12px`.
- `nav a`: `padding: 0 0.75rem`; `min-height: 44px`.
- `.note` / `.tip`: `padding: 0.9rem 1.1rem`; `border-left: 4px solid`; `border-radius: 0 8px 8px 0`; `margin-bottom: 0.9rem`.
- `#back-to-top`: `bottom: 2rem; right: 2rem`; `padding: 0.6rem 1rem`; `border-radius: 8px`.
- List items: `margin-bottom: 0.35rem`; paragraph: `margin-bottom: 0.9rem`.
- Nav link `gap: 0.25rem`.

### Graphics & icons
- No images, SVGs, or `Image(systemName:)` references are present in the visible source — nothing to describe.

### Overall composition
Centered single-column layout capped at **860 px**. The page opens with a dark `#1d1d1f` header band, followed by a white sticky nav strip with a 1 px `#b0b0b5` hairline, then a `#f5f5f7` body containing white rounded cards separated by 1.5 rem. A fixed blue pill ("back-to-top") sits in the bottom-right corner. The composition is the conventional Apple/developer-doc pattern (header → sticky nav → bordered cards → floating action).

---

## 2. Ease of Use for Sighted Users

- **Clear hierarchy:** H1 → sticky nav → H2/H3 inside cards → body copy. The 2 rem / 1.4 rem / 1.1 rem step-down makes the structure readable at a glance.
- **Wayfinding:** The 15-link nav is wide but wraps (`flex-wrap: wrap`); the active link is communicated by a 3 px blue underline and bolder weight — the `aria-current="location"` selector is wired in CSS, though the markup for setting it is not visible in the excerpt.
- **Tap affordance:** Nav links are 44 px tall and have visible padding, so they read as clickable. The back-to-top is a saturated blue pill with shadow — clearly a button.
- **Contrast on chrome:** Dark `#1d1d1f` header with off-white `#f5f5f7` text reads with strong separation; subtitle in muted `#a0a0a6` recedes appropriately. The blue accent is consistent.
- **No visual clutter** in the visible chrome — generous padding, breathing room, rounded corners.

---

## 3. Professional Quality

**Verdict: Polished** — with the caveat that the page body has not been seen.

Reasons:
- Consistent design tokens (one primary blue, one neutral family, two semantic callout tints).
- Three-mode awareness: light / dark / Windows High Contrast, all wired in CSS.
- Motion safety via `prefers-reduced-motion`.
- Focus rings explicitly defined for `a` and `button` in all three modes.
- Forced-colors block uses system color keywords correctly (`Canvas`, `CanvasText`, `Highlight`, etc.) and even sets `forced-color-adjust: none` on the back-to-top button so the system highlight wins.
- Subtle touches: focus outline is 3 px (above the 2 px minimum) and `outline-offset: 2px` keeps it off the element edge.
- Card border is the same `#b0b0b5` as the nav hairline — visual coherence.

The polished reading depends on body content (not shown) holding the same discipline.

---

## 4. Accessibility

### What's working
- `lang="en"` on `<html>`. [good]
- Skip link `<a class="skip-link" href="#main-content">` with high-contrast blue/white (pre-computed `#0059b3 on #fff` = **6.82:1, AA PASS**) and a `:focus` rule that moves it on screen. [good]
- Semantic landmarks: `<header>`, `<nav aria-label="Page sections">`, `<main id="main-content">`. [good]
- WCAG 2.5.5 touch target: `nav a { min-height: 44px }`. [good]
- `:focus-visible` outline defined globally (`3px solid #0059b3`, offset 2 px) and reinforced on nav links. [good]
- `prefers-reduced-motion: reduce` removes transitions on nav links and back-to-top. [good]
- Forced-colors block respects system colors. [good]
- Dark mode preserves focus ring by switching to `#6eb3ff` accent. [good]
- Back-to-top visibility is gated by an `opacity` + `pointer-events` switch — when hidden it is not focusable. [good]
- Callouts have bold left borders plus tinted backgrounds — distinguishable for many color-vision conditions (border ≠ background hue). [good]

### Issues / fixes

1. **`<a>` styling without an underline is risky for color-blind users.** [design discussion]
   - `nav a` and skip-link both rely on color + border-bottom for "this is a link." The hover/current states use a 3 px underline that helps, but the default state is unstyled text.
   - Fix: add a `text-decoration: underline; text-underline-offset: 3px; text-decoration-thickness: 1px;` baseline, or make the bottom border always present (1 px) and grow to 3 px on hover/current.

2. **Subtitle contrast on dark header.** The CSS comment claims `#a0a0a6 on #1d1d1f ≈ 4.8:1` (AA PASS for body text). Not on the pre-computed list — re-verify with a contrast tool before shipping. [design discussion]

3. **Body text in dark mode (`#f5f5f7` on `#000`)** is not in the supplied pre-computed table. The pairing should be spot-checked with a tool — the palette is bright-on-black and is *likely* fine, but a measured ratio is required to claim AA. [design discussion]

4. **Back-to-top focus outline color is white in light mode (`outline:3px solid #fff`).** This is fine because the button background is `#0059b3`, so the outline is visible. But the rule `a:focus-visible, button:focus-visible { outline: 3px solid #0059b3; outline-offset: 2px }` is also active, which would mean the *generic* rule fires on the same element with the *same* color as the button background — a same-color outline against same-color background is invisible. The specific `#back-to-top:focus-visible` rule correctly overrides to white, but this depends on specificity being preserved. [cosmetic]
   - Fix: add a contrasting border to the button itself (e.g., `border: 2px solid #fff`) for a permanent focus cue that survives cascade mistakes.

5. **Back-to-top HTML not visible in excerpt.** The CSS expects `<button id="back-to-top">…</button>` somewhere later in the file. It needs:
   - An accessible name (visible text "Back to top" appears to be styled for, but verify the element exists in the unshown portion).
   - `aria-label="Back to top"` if the visible text is hidden.
   - The `.visible` class is toggled by JavaScript (not in this file) — confirm the toggle exists and that the button is `display: none` (not just `opacity: 0`) when inactive, so it is *not* in the tab order until shown. CSS only sets `pointer-events: none`; tabbability is not explicitly removed. [design discussion]
   - Fix: add `#back-to-top:not(.visible) { visibility: hidden; }` so it drops out of the tab order when hidden.

6. **`<table>` markup not visible in excerpt.** The CSS correctly styles `caption`, `th`, `td`, and even-nth rows, but the HTML elements themselves are in the unseen portion. To be WCAG-compliant, every table needs:
   - `<caption>` describing the table (the CSS positions it left/bold at 0.9 rem — good styling).
   - `<th scope="col">` for column headers and `<th scope="row">` for row headers.
   - Verify these are present in the unshown body.

7. **15 nav links in a single sticky bar** may cause horizontal scroll on narrow viewports despite `flex-wrap: wrap` (it wraps vertically and may push the page header off-screen on first paint). [design discussion]
   - Fix: consider a `<details>` summary or `role="navigation"` with a "Sections" disclosure on small screens.

8. **Images / inputs not present in excerpt.** No `<img alt>` or `<label for>` issues can be evaluated from the visible source — flag this as a check for the unshown body.

9. **`prefers-reduced-motion` only disables two transitions** (`nav a` and `#back-to-top`). If any other animated content appears in the unseen body (scroll-triggered reveals, accordion transitions), it is not covered. [design discussion]

10. **Reduced-motion doesn't disable the focus ring's potential glow/animation** because there is no keyframe animation in the visible CSS — nothing to fix here, just noting the rule set is minimal. [cosmetic]

---

## 5. Other Important Details

- **Animations present:** `nav a` border-color transition `0.15s`; `#back-to-top` opacity transition `0.2s`. Both are removed under `prefers-reduced-motion: reduce`. No `@keyframes` in the visible CSS.
- **Dark mode** is implemented via `@media (prefers-color-scheme: dark)` and includes a near-complete token override (background, text, borders, focus rings, callout tints, back-to-top).
- **Forced-colors mode** is implemented separately; uses `Highlight`, `Canvas`, `CanvasText`, `ButtonFace`, `ButtonText`, `HighlightText` — all system color keywords.
- **Error states / empty states / loading states:** none present in the visible source.
- **Conditional UI:** `#back-to-top` is hidden by default (`opacity: 0; pointer-events: none`) and revealed via a `.visible` class — but `visibility: hidden` is not set, so the button is technically still in the tab order (see Accessibility issue #5).
- **Skip link behavior:** Off-screen at `top: -100%`, slides in on `:focus`. Works without JS.
- **Sticky nav `z-index: 100`** vs. **skip link `z-index: 9999`** vs. **back-to-top `z-index: 200`** — the stacking order is sensible (skip link wins, then back-to-top, then nav).
- **No JS in the visible source** — the file is HTML+CSS only at this point. The `.visible` toggle for back-to-top must live in the unseen portion or an external script.
- **`max-width: 860px`** is repeated on `header .inner`, `nav .inner`, and `.wrapper` — consistent reading column.