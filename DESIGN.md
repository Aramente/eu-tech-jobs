---
name: "eu-tech-jobs"
version: 0.2.0
description: "Live wire for the EU tech labor market. Terminal density, mono-forward, monochrome with a single red signal."
tags: [terminal, dense, monochrome, data-instrument]
target_audiences: [job-seeker, developer, recruiter]
status: draft
---

# eu-tech-jobs — Design System

Hand this to an agent before any visual work. Implementation that fights the spec is wrong; if a rule below blocks something obviously good, edit the spec, then ship.

## 1. Visual Theme & Atmosphere

**Live wire for the EU tech labor market.** The site reads like a terminal plugged into something live: 12,178 rows, refreshed daily, scrolling past you in mono. Density is the tell. Restraint is the texture. Red is the signal. The data is the design — chrome stays out of the way, and the page never apologises for being a list of facts.

**Anchors** (in priority order):
1. **Bloomberg Terminal** — column rhythm, mono-forward, status strip as identity.
2. **news.ycombinator** — stubborn density, no decoration, type does the work.
3. **RemoteOK** — single-line job rows, salary in the row, no logos.
4. **Reuters wire** — the feeling of a feed that won't stop.

**Foil** — break character on the long-form job article only: shift to serif H1 + Inter body at reading width. The article is the wire story you clicked into.

**Anti-anchors** (not us): Linear, Stripe, Pinterest-style cards, indie-blog cream-on-charcoal, anything that uses Inter Tight.

## 2. Color Palette & Roles

```
--paper       #f4f1ea   page background, warm off-white (paper, not beige)
--ink         #0a0a0a   primary text and borders, true near-black
--ink-soft    #1a1a1a   alt for inverted backgrounds
--rule        #d6d2c7   hairline dividers, table rules, input bottoms
--muted       #5a5a52   meta, captions, secondary text
--signal      #d72638   reserved single-purpose red — see usage rules
--row-hover   #ece8de   subtle warm highlight, used sparingly
```

Dark mode flips `--paper`/`--ink`/`--ink-soft`/`--row-hover`; `--signal` and `--rule` shift slightly cooler. Spec ships with light mode for v0.2.

**Usage rules**
- Primary CTAs: `--ink` background, `--paper` text. No exceptions.
- Body: `--ink` on `--paper`. Borders: `--rule`.
- `--signal` red is reserved for **time-sensitive data only**: "NEW" badge on jobs ≤24h, salary-disclosed pill, the wordmark mark, hot-company indicator. Never decoration. Never UI chrome (no red borders, no red focus rings, no red links). If the bit it marks isn't time-or-money-sensitive, it's not red.
- No yellow anywhere. The previous EU-flag yellow was decoration; we ban decorative colour entirely.
- No background fills on rows or cards beyond `--row-hover` for explicit hover.

## 3. Typography Rules

Three families. Each owns one role and never crosses.

```
--display     "Instrument Serif", "Tiempos Headline", Georgia, serif
--mono        "JetBrains Mono", ui-monospace, "SF Mono", monospace
--body        "Inter", -apple-system, BlinkMacSystemFont, system-ui, sans-serif
```

Loaded via Google Fonts CDN: `Instrument+Serif:wght@400`, `JetBrains+Mono:wght@400;500;600`, `Inter:wght@400;500;600;700`.

**Role contract — do not cross**
- `--display` (Instrument Serif): the wordmark only. One word, one place. Anywhere else is wrong.
- `--mono` (JetBrains Mono): all UI chrome — status strip, filter labels, table headers, result-row meta column, badges, captions, counts, pagination, button text on small buttons. The site IS mono until proven otherwise.
- `--body` (Inter): job description article body, result-row title, result-row company-location column, page lede where one exists.

**Type scale (4 stops, modular)**
- 11px — captions, mono meta, badges
- 13px — secondary text, filter labels, status strip
- 15px — body and result-row title
- 17px — long-form body (job description), section subhead
- 22px — long-form H1 (job description page only — the foil)
- 40px — wordmark

**Rules**
- Mono is sentence-case lowercase by default. **UPPERCASE** only on captions and badges (e.g. `5D · REMOTE-EU`, `NEW`, `EU-TECH-JOBS`).
- Letter-spacing on uppercase mono: 0.06em.
- All numerics use `font-variant-numeric: tabular-nums`.
- Body is 15/1.55. Long-form body 17/1.65, max-width 640px.
- Wordmark uses `--display` italic (Instrument Serif's italic is the move) at 40px / 1.0.

**Anti-patterns**
- ❌ Inter Tight (the v0.1 mistake — too generic).
- ❌ Mono italic — JetBrains Mono italic is heavy and noisy; never use.
- ❌ Mixing two font families in one line.
- ❌ Bold weight (700) outside the wordmark and Inter body `<strong>`.

## 4. Component Stylings

### Status strip (identity beat — every page)

A persistent mono strip below the masthead on every page:

```
EU-TECH-JOBS // 12,178 OPEN // 603 COMPANIES // UPDATED 04:12 UTC // 47 NEW TODAY
```

- `--mono` 13px / uppercase / 0.06em letter-spacing / `--ink` text on `--paper`.
- `//` separators in `--rule` color.
- `47 NEW TODAY` is the only `--signal` red bit (when count > 0).
- Padding: 8px 24px. Border-bottom: 1px `--rule`. Reads like a Reuters wire header, not a hero.
- Wraps on narrow viewports — never scrolls horizontally.

### Wordmark

`--display` italic 40px, `--ink`. One subtle move: dot the i in "tech" with `--signal` red. Nothing else carries the brand. The status strip beneath it does the rest.

### Result row (canonical density unit)

**Single line on desktop ≥720px**, three-column flex:
```
[ TITLE — flex:1 ]    [ COMPANY · LOCATION — flex:0 0 32% ]    [ META — flex:0 0 18%, right-aligned ]
```
- Title: `--body` 15/500/-0.005em / `--ink`. Single-line ellipsis truncation.
- Company-location: `--body` 14/400 / `--muted`. `·` separator in `--rule` color. Single-line ellipsis.
- Meta: `--mono` 11/uppercase/0.06em / `--muted`. Right-aligned. Single line. Format: `5D · REMOTE-EU` or `NEW · €80K · REMOTE-EU` (when salary disclosed).
- Salary in `--ink` (not muted) when present. `NEW` in `--signal` red when posted ≤24h.
- Padding: 10px 0. Divider: 1px `--rule` (full opacity, not the v0.1 60% softening — Bloomberg uses crisp rules).
- Hover: 2px `--ink` left bar appears, no padding shift, no transition delay. Cursor turns into a column-reader feel via `cursor: pointer`.
- Excerpt: off by default. Pagefind matches bold the matched word in the title only.

**Stacked at <720px**: title above, company-location middle, meta below. 6px gap. 12px padding.

### Buttons / CTAs

- **Primary** (Apply): `--ink` bg, `--paper` text, `--mono` 13/600 uppercase, padding 12/20, square (no radius — radius reads soft, we want hard). Hover: shifts to `--ink-soft`.
- **Secondary** (Tailor CV): transparent bg, `--ink` text, 1px `--ink` border, otherwise same shape and type. Hover: `--row-hover` fill.
- **Tertiary text-link**: `--mono` 12 / `--muted` / underline `--rule`. Hover: `--ink` + underline `--ink`.
- Focus ring: 2px `--ink` outline, 2px offset.

### Inputs

- **Search field**: bare. No border, no radius, no fill. Bottom-rule 1px `--rule`. Padding 8px 0. `--mono` 14 prompt: `> search…` with a leading `>` glyph. Focus: bottom-rule darkens to `--ink`.
- **Filter chips**: `--mono` 12 uppercase. Box: 1px `--rule`, 0 radius, padding 4/10. Active: `--ink` bg, `--paper` text. Hover: `--row-hover`. No round corners.

### Badges

Pure metadata text inside the result row's meta column. Not boxes. `--mono` 11 uppercase 0.06em `--muted`. `·` separator at `--rule` color. Exception: `NEW` and `€XXk` use `--signal` and `--ink` respectively as colour-only emphasis, no box.

### Filter rail (search page)

- 200px wide, 32px gutter (was 240/56 — too airy for terminal density).
- No border-right.
- Each facet block: top 1px `--rule`, mono uppercase 11/0.06em group head in `--muted`, list of options.
- Option row: checkbox + label + count, `font-variant-numeric: tabular-nums` on count, count right-aligned.
- "Clear all" is a small mono text-link demoted under the last block.

### Pagination

`--mono` 11 uppercase. 4/10 padding. 1px `--rule` border. No radius. Current page: `--ink` bg, `--paper` text.

### Dividers

1px `--rule` everywhere. No softening, no opacity reduction. Crisp rules are the look.

## 5. Layout Principles

- **Spacing scale**: 4 / 8 / 12 / 16 / 24 / 32 / 48. (Drop 64 — it's never the right answer here.)
- **Section gaps 32, block gaps 16, item gaps 8, inline gaps 4**. State this so agents stop guessing.
- **Page max-width**: 1280px main. 640px for long-form (job description).
- **Grid**: filter rail 200px + 32px gutter + results column. Below 720px: stack, results first, filter behind a `Filters` button (deferred to v0.3).
- **Density target**: 28+ result rows above the fold at 1440×900. If a layout produces fewer than 20, it's not dense enough.
- **Empty space is not the goal**. Ink rule density is. Bloomberg, not Apple Marketing.

## 6. Depth & Elevation

- **Flat. Always.** Elevation comes from rule contrast and `--row-hover` fills, never shadow.
- **No shadows anywhere.** The chip-popover dropped its shadow in v0.2 — it now sits on a 1px `--ink` border instead.
- **No card backgrounds**, no border-radius beyond what's already structural (none, in v0.2).

## 7. Motion & Interaction

- Hover transitions: 80ms ease, transform-only (`box-shadow`, `transform`, `border-color`). Never animate background colour or padding.
- No spinners. Inline mono "searching…" with blinking caret.
- No skeleton states.
- `prefers-reduced-motion: reduce` disables transitions; layout stays.
- Optional v0.3+: ticker bar of newest 5 jobs scrolls right-to-left on the home page. Honor reduced-motion by freezing the latest 5 in place.

## 8. Do's and Don'ts

✅ Default to `--mono`. Reach for `--body` Inter only on result-row titles + long-form article body.
✅ Use `--signal` red only for time-sensitive or money-sensitive data. Audit every red pixel by asking "what does this fact decay or expire?"
✅ Keep rows dense. 28+ per fold at desktop, or it's not the look.
✅ Crisp 1px rules. Never soften with opacity.
✅ Tabular numerals on every count.
✅ `//` separator in mono captions, `·` separator in body lines.
✅ Status strip on every page, top-of-fold, identical structure.

❌ No icons except `>` glyph in search field. (Unicode dot, middot, slash only.)
❌ No background fills. No card shells. No rounded corners.
❌ No hero blocks. No "Find your next role at…" lede. The data is the hero.
❌ No yellow. No teal. No second accent color.
❌ No Inter Tight. No DM Sans. No Geist. No "Linear-clone" fonts.
❌ No tables for job listings. `<ol class="results-list">` of `.result-link` items only.
❌ No motion on the page body — only ticker (when shipped) and hover-bar.
❌ No "explainer copy" above the fold. If a paragraph teaches the user how to use the page, delete it and fix the page.

## 9. Example Snippets

### Status strip

```html
<div class="status-strip">
  <span class="status-name">EU-TECH-JOBS</span>
  <span class="status-sep">//</span>
  <span><strong>12,178</strong> OPEN</span>
  <span class="status-sep">//</span>
  <span><strong>603</strong> COMPANIES</span>
  <span class="status-sep">//</span>
  <span>UPDATED 04:12 UTC</span>
  <span class="status-sep">//</span>
  <span class="status-new"><strong>47</strong> NEW TODAY</span>
</div>
```

### Result row

```html
<li class="result-item">
  <a href="/jobs/..." class="result-link">
    <span class="result-title">Senior Backend Engineer</span>
    <span class="result-org">Datadog · Paris</span>
    <span class="result-meta">5D · REMOTE-EU · €80K</span>
  </a>
</li>
```

```css
.result-link {
  display: grid;
  grid-template-columns: 1fr 32% 18%;
  gap: 16px;
  align-items: baseline;
  padding: 10px 0;
  border-bottom: 1px solid var(--rule);
  text-decoration: none;
  color: var(--ink);
  position: relative;
  transition: padding-left 80ms ease;
}
.result-link:hover { padding-left: 14px; }
.result-link::before {
  content: "";
  position: absolute; left: 0; top: 0; bottom: 0;
  width: 2px; background: var(--ink);
  opacity: 0; transition: opacity 80ms ease;
}
.result-link:hover::before { opacity: 1; }
.result-title {
  font: 500 15px/1.3 var(--body);
  letter-spacing: -0.005em;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.result-org {
  font: 400 14px/1.4 var(--body);
  color: var(--muted);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.result-meta {
  font: 500 11px/1.4 var(--mono);
  text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--muted);
  text-align: right;
  font-variant-numeric: tabular-nums;
}
```

## Notes for agents

- Tokens live in `site/src/styles/global.css :root`. Reuse; never inline a hex.
- The status strip is a real component — add it to `Base.astro` once, not page-by-page.
- Job article page (`/jobs/[slug]`) is the one **foil** — body shifts to `--body` Inter at long-form scale. Status strip and CTAs stay terminal.
- When in doubt, take a thing away. Then take another thing away.
