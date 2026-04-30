---
name: "eu-tech-jobs"
version: 0.1.0
description: "Editorial-minimal indie data product. Inky, generous, monospace meta, EU-yellow accent used sparingly."
tags: [editorial, minimal, indie, data-product]
target_audiences: [job-seeker, developer, recruiter]
status: draft
---

# eu-tech-jobs — Design System

The system the site ships under. Hand this to an agent before any visual work — it should produce work indistinguishable from a careful pass.

## 1. Visual Theme & Atmosphere

Editorial-minimal indie data product. Reads like a typeset catalogue: confident type, generous breathing room, silence around each row, mono accents for metadata. Restraint over ornament. The data is the design — chrome apologises, never decorates. Spirit anchors: Pinboard's stubborn typography, every.to's column rhythm, lite.cnn's information density without UI noise.

## 2. Color Palette & Roles

```
--bg          #fafaf7   page background (cream)
--fg          #141413   primary ink (near-black)
--ink         #141413   alias of --fg, used for buttons/wordmark
--on-ink      #ffffff   text on ink (CTAs, active chips)
--muted       #6b6b6b   secondary text, meta, captions
--accent      #ffcc00   EU-flag yellow — accent only, never a fill for text
--border      #e5e5e2   hairline rules, dividers, input bottoms
--row-hover   #f3f2ee   hover background
```

Dark-mode tokens flip `--bg`/`--fg`/`--ink`/`--on-ink`. Accent stays yellow.

**Usage rules**
- Primary CTAs: `--ink` background, `--on-ink` text. Never use `--accent` as a CTA fill (yellow doesn't carry text legibly at small sizes).
- `--accent` lives in: hover-highlight marks (mark/excerpt highlights), wordmark dots, focus rings, hover-state border accents, the `+N` pill on chips.
- Body links: ink, underlined with `--border` color, thicken to 2px with `--accent` color on hover.
- Never apply both colour and underline to the same link state — pick one cue per state.

## 3. Typography Rules

```
--serif   "Inter Tight", Inter, system-ui, sans-serif    // UI + body
--mono    "JetBrains Mono", ui-monospace, monospace      // meta, captions, badges
```

**Scale (modular, ratio ≈1.25)**
- 10px — chip-popover group heads, chip-pill counter
- 11px – 12px — captions, badges, chip-row counts, mono meta
- 13px — secondary text, helper copy, filter-block labels
- 14px — base small, table cells, search input
- 15px — body, table primary, result-meta line
- 16px — result title (one-line list density)
- 17px – 19px — section subheads, card titles
- 24px — page subheads
- 28px – 32px — page titles, wordmark

**Hierarchy rules**
- Body uses `--serif` regular 400 / 1.55 line-height.
- Long-form (job description): 16.5px / 1.7, max-width 660px.
- All-caps + letter-spacing (`text-transform: uppercase; letter-spacing: 0.06em`) only on **mono captions**, never on serif body.
- Tabular numerals (`font-variant-numeric: tabular-nums`) on counts and dates.
- Titles: weight 600, slight negative tracking (-0.01em). Body: 400. Bold inside body: 600.

**Anti-patterns**
- ❌ Don't size meta below 11px — gets unreadable on 14" screens.
- ❌ Don't render serif text in uppercase + letter-spacing. That's a mono treatment.
- ❌ Don't mix font-families inside a single line of meta.

## 4. Component Stylings

### Buttons / CTAs
- **Primary**: `--ink` bg, `--on-ink` text, 600 weight, 12-14px padding, 8px radius. Hover: lift 1px translateY, switch border to `--accent`.
- **Secondary**: transparent bg, `--fg` text, 1px `--border`, hover: `--row-hover` bg, border becomes `--fg`.
- **Tertiary text-link**: muted text, `--border` underline, hover: ink + accent underline.
- Focus ring: 2px `--accent`, 2px offset.

### Inputs
- **Boxed**: 1px `--border`, 6px radius, 8px padding. Focus: border becomes `--ink` (no shadow).
- **Bare** (rail filter input): 0 border, 1px `--border` bottom rule, 0 radius, 8px vertical padding. Focus: bottom rule darkens to `--ink`.

### Chips (filter triggers)
- 999px radius pill, 1px `--border`, 8/14 padding. `--bg` fill.
- **Active** (selection present): `--ink` bg, `--on-ink` text, `--ink` border. Selection summary baked into label: `Country: France +2` (the `+N` is an accent pill).
- Caret `▾` is muted and 10px. Drop the gesture, use the chip itself as the popover trigger.

### Pills (active filter chips)
- Same shape as chips but smaller (4/10 padding, 12px text). `--row-hover` bg, `--border` outline.
- Inner structure: mono uppercase facet label (10/0.06em) + serif value (500) + `×` (14px, 0.7 opacity).
- Hover flips to `--ink` reversal.

### Result row (the canonical density unit)
- **Stacked** layout (default). Two lines: title, then meta.
- Title: 16/500/-0.005em ink, can wrap to 2 lines with ellipsis on overflow.
- Meta: 13px serif muted, sentence-case (NOT uppercase), `·` separator. Reads "Datadog · Paris · 5d ago · Remote-EU".
- Padding: 14px 0. Hairline divider at 60% `--border` opacity.
- Hover: 3px inset `--accent` stripe on the left, 14px padding-left shift, 120ms ease.
- Excerpt: optional, 13px muted, 2-line `-webkit-line-clamp`. Default off — only render when explicit search query produces highlighted excerpt.

### Badges
- Pure metadata text, NOT boxes. Mono uppercase 11px 0.06em, `--muted`.
- Multiple badges on the same line are separated by `·` glyph at `--border` color.

### Filter rail
- 220px wide, 56px gutter from results column.
- No border-right; whitespace separates.
- Each facet block: top hairline rule, mono uppercase group head, list of options, `+N more` muted text-link to expand long lists.
- `Clear all` is a small text-link demoted under the last block. Never a full-width button.

### Pagination
- Inline numeric pages, 6/12 padding, 1px `--border`, 6px radius.
- Current: `--ink` bg, `--on-ink` text.

### Dividers
- 1px `--border` for full rules, `color-mix(in oklab, var(--border) 60%, transparent)` for in-list dividers.
- Section dividers (CTA divider, footer top): 1px `--border`, no decoration.

## 5. Layout Principles

- **Spacing scale**: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 — all 4px multiples.
- **Page max-width**: 1200px main, 660px long-form (job description).
- **Grid**: filter rail 220px + 56px gutter + results column. Below 800px, stack.
- **Vertical rhythm**: header padding 32–48px top depending on page weight. Sections 24–32px apart.
- **Empty space is structural**, not optional. If a layout feels tight, remove an element before adding more padding.

## 6. Depth & Elevation

- **Default**: flat. Elevation comes from hairline rules and whitespace, not shadows.
- **One exception**: chip-popover floats on `0 8px 24px rgba(0,0,0,0.08), 0 1px 3px rgba(0,0,0,0.06)` — this is the only place a soft shadow appears.
- No card backgrounds. No elevation gradients. No glassmorphism.

## 7. Motion & Interaction

- Hover transitions: 80–120ms ease.
- Reveal/hover-shift: max 1px translateY, 14px padding shift, 3px stripe inset. Nothing else moves.
- No spinners — inline "Searching…" text only.
- No skeleton states (yet). The page renders empty, then populates fast.
- Reduced motion: respect `prefers-reduced-motion: reduce` — disable transitions only, layout stays.

## 8. Do's and Don'ts

✅ Use mono uppercase for **metadata only** — counts, captions, tag-style labels.
✅ Reach for hairlines and whitespace before borders or shadows.
✅ Demote secondary actions (text-link, muted) instead of styling them louder.
✅ Right-align numeric counts with `tabular-nums`.
✅ Use `·` glyph (middot) as the meta separator, not `|` or `,`.
✅ Truncate with `text-overflow: ellipsis` only when the truncated string would still be useful — otherwise wrap.
✅ Default to two-line stacked rows for list density. Single-line rows only when meta fits comfortably (≤ ~30% width).

❌ Don't use yellow as a text colour or button fill.
❌ Don't size meta below 11px on desktop.
❌ Don't render serif body in uppercase.
❌ Don't add background fills to badges or rail blocks.
❌ Don't render every line in `var(--mono)` — that becomes a Bloomberg terminal, not a job board.
❌ Don't add icon decorations to CTAs unless they carry semantic weight (e.g. ✨ on the Tailor-CV CTA earns its keep).
❌ Don't use full-width buttons inside content rails — they read as wizard footers.
❌ Don't redesign the same surface twice in one session — write the spec, then implement once.

## 9. Example Snippets

### Result row (canonical)

```html
<li class="result-item">
  <a href="/jobs/..." class="result-link">
    <div class="result-title">Senior Backend Engineer</div>
    <div class="result-meta">Datadog · Paris · 5d ago · Remote-EU</div>
  </a>
</li>
```

```css
.result-link {
  display: block;
  padding: 14px 0;
  text-decoration: none;
  color: var(--fg);
  border-bottom: 1px solid color-mix(in oklab, var(--border) 60%, transparent);
  transition: padding 120ms ease, box-shadow 120ms ease;
}
.result-link:hover {
  box-shadow: inset 3px 0 0 var(--accent);
  padding-left: 14px;
}
.result-title {
  font-size: 16px;
  font-weight: 500;
  letter-spacing: -0.005em;
  line-height: 1.3;
}
.result-meta {
  font-size: 13px;
  color: var(--muted);
  margin-top: 4px;
  line-height: 1.5;
}
```

### Filter chip

```html
<button class="chip chip-active" aria-haspopup="listbox" aria-expanded="false">
  Country: <strong>France</strong>
  <span class="chip-pill">+2</span>
  <span class="chip-caret">▾</span>
</button>
```

### Active filter pill

```html
<button class="active-pill">
  <span class="pill-facet">Country</span>
  <span class="pill-value">France</span>
  <span class="pill-x">×</span>
</button>
```

## Notes for agents

- All tokens are defined in `site/src/styles/global.css :root`. Reuse them; never inline a hex.
- Component CSS lives next to the component (Astro `<style>` block) when it's page-specific, in `global.css` when it's reused.
- Per-page spec deviations require a Do/Don't update here first.
- When in doubt: take a thing away, not add a thing.
