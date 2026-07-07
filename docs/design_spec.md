# Design Specification — "How Fast Does New York Fix It?"

**An interactive map of 311 resolution-time probabilities, tract by tract, across all five boroughs.**

Version 1.0 · Static SPA · Vanilla HTML/CSS/JS + MapLibre GL JS · No build step

---

## 0. Design thesis (read this first)

This is a data-journalism piece disguised as a tool. The single design idea that everything
else serves: **the map answers "how fast?", the panel answers "how sure?"**. The map is a
dark, cinematic canvas where a single probability — *chance your request is resolved within
the selected time window* — glows tract by tract. Clicking a tract opens a "resolution
ladder": nine cumulative probability bars that read top-to-bottom like a countdown, with
uncertainty rendered as soft fades, never error bars with caps.

One recommended design. No options menus in this document. Dark theme, one accent color,
one choropleth ramp, one chart form.

---

## 1. Visual identity

### 1.1 Theme: dark

Use the dark theme. Rationale: the choropleth is the hero, and a luminance-encoded ramp
(dim = slow, bright = fast) reads instantly against near-black. It also photographs
beautifully on a projector. Basemap: **CARTO Dark Matter (no labels)** raster tiles
(`https://basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}@2x.png`, free, no key; include the
required CARTO/OSM attribution) with CARTO's `dark_only_labels` raster layer placed **above**
the choropleth so street/neighborhood names float on top of the color.

### 1.2 Core palette

| Token | Hex | Use |
|---|---|---|
| `--bg-0` | `#0B0E14` | Page background, behind map while loading |
| `--bg-1` | `#11151F` | Side panel background |
| `--bg-2` | `#1A2030` | Cards, chips (rest state), tooltip background at 92% opacity |
| `--line` | `#2A3244` | Hairline borders, dividers (1px) |
| `--text-1` | `#F2F4F8` | Primary text |
| `--text-2` | `#9AA3B5` | Secondary text, axis labels |
| `--text-3` | `#5C6577` | Tertiary/disabled, attribution |
| `--accent` | `#FFB84D` | Selection, interactive highlights, links, "play" button (warm amber — deliberately outside the choropleth ramp's hue range so selection never reads as data) |
| `--accent-soft` | `#FFB84D26` | Accent at 15% alpha for hover fills |
| `--good` | `#43D9A3` | "Strong local data" indicator |
| `--warn` | `#F5A97F` | "Limited local data" indicator |
| `--focus` | `#7AA7FF` | Keyboard focus rings only |

### 1.3 Choropleth ramp (the star)

A 7-step **viridis** ramp — perceptually uniform, colorblind-safe, and its dim-purple→
bright-yellow luminance arc means "brighter = faster" needs no explanation on a dark map.

Direction: **low probability = dark purple, high probability = bright yellow.**

| Break | Hex |
|---|---|
| 1 (slowest) | `#440154` |
| 2 | `#414487` |
| 3 | `#2A788E` |
| 4 | `#22A884` |
| 5 | `#7AD151` |
| 6 | `#BDDF26` |
| 7 (fastest) | `#FDE725` |

- **7 discrete classes, not continuous.** Discrete classes make the legend readable and let
  a lay audience say "my tract is in the second-fastest band." Class breaks are **fixed
  per metric** (see §3.3), not quantiles, so colors keep meaning as the user switches
  complaint types.
- Tract fill opacity `0.78` so the street grid ghosts through. Tract borders: `#0B0E14` at
  `0.4` opacity, 0.5px — just enough to separate tracts at high zoom, invisible zoomed out.
- No-data tracts (parks, airports, tracts with zero requests even after pooling): fill
  `#1A2030` at `0.5` opacity with a subtle diagonal-hatch feel via lower opacity; excluded
  from hover.

### 1.4 Typography

Two Google Fonts + system fallbacks. Load with `display=swap`, weights listed only.

- **Display / headline: `Fraunces`** (weights 600, 700; optical size axis on). The soft
  editorial serif is what makes it read NYT/Pudding rather than dashboard.
- **UI / body / numerals: `Inter`** (weights 400, 500, 600, 700). Apply
  `font-feature-settings: "tnum" 1, "ss01" 1;` wherever numbers align in columns or
  animate (count-ups must not jitter).
- Fallback stack: `Fraunces, Georgia, serif` and `Inter, -apple-system, "Segoe UI", Roboto, sans-serif`.

Type scale (desktop):

| Role | Font | Size/Line | Weight | Color |
|---|---|---|---|---|
| App title | Fraunces | 28/32px | 700 | `--text-1` |
| Subtitle | Inter | 14/20px | 400 | `--text-2` |
| Panel tract name | Fraunces | 22/28px | 600 | `--text-1` |
| Headline stat number | Inter (tnum) | 44/48px | 700 | ramp color of its class |
| Section labels (ALL CAPS) | Inter | 11/16px, +0.08em tracking | 600 | `--text-3` |
| Bar labels / body | Inter | 13/18px | 400–500 | `--text-2` |
| Tooltip | Inter | 12/16px | 500 | `--text-1` |

### 1.5 Mood

Nocturne city-data. Restraint everywhere except the ramp. No drop shadows heavier than
`0 8px 24px rgba(0,0,0,0.45)`, no gradients except uncertainty fades, corners 10px on
panels/cards, 999px on chips. Motion is calm: 200–300ms ease-out for UI, longer only for
the two hero animations (§8).

---

## 2. Layout

### 2.1 Desktop (≥1024px)

Full-bleed map; everything else floats above it. No document scroll.

```
┌────────────────────────────────────────────────────────────────────────┐
│ ┌───────────────────────────────┐                    ┌───────────────┐ │
│ │ HEADER CARD (floating)        │                    │ SIDE PANEL    │ │
│ │ 480px wide, top-left,         │                    │ 400px wide    │ │
│ │ 16px from top & left          │                    │ full height   │ │
│ └───────────────────────────────┘                    │ minus 16px    │ │
│                                                      │ top/bottom/   │ │
│                    MAP CANVAS                        │ right margins │ │
│                    (fills viewport)                  │               │ │
│                                                      │               │ │
│ ┌──────────────┐   ┌───────────────────────────┐     │               │ │
│ │ LEGEND       │   │ TIME SCRUBBER (centered   │     │               │ │
│ │ bottom-left  │   │ on remaining map width)   │     └───────────────┘ │
│ │ 16px margins │   │ 16px from bottom          │                       │
│ └──────────────┘   └───────────────────────────┘                       │
└────────────────────────────────────────────────────────────────────────┘
```

- **Map canvas**: `position: fixed; inset: 0`. Initial view: center `[-73.94, 40.70]`,
  zoom 9.7, pitch 0, maxBounds padded around NYC (`[-74.30, 40.45]` → `[-73.65, 40.95]`),
  minZoom 9, maxZoom 15.
- **Header card**: floating card, `--bg-1` at 88% opacity + `backdrop-filter: blur(12px)`,
  radius 12px, padding 20px 24px, max-width 480px. Contains title, subtitle, address
  search input (full card width, 40px tall, `--bg-2` fill, 8px radius), and the borough
  shortcut row (§5.6). Collapsible via a chevron to a 48px pill after first interaction.
- **Side panel**: fixed right, width 400px, 16px margins on top/right/bottom,
  `--bg-1` at 96% + blur(16px), radius 14px, inner padding 24px, own scroll
  (`overflow-y: auto`, styled 6px scrollbar). Hidden (translated `+420px`, 280ms
  ease-out) until a tract is selected. Close "×" 32×32px top-right.
- **Legend**: bottom-left, 16px margins, `--bg-1` at 88% + blur, radius 10px,
  padding 12px 16px, width ~260px. Seven 28×12px swatches in a row, 2px gaps,
  end labels beneath ("0%" left, "100%" right, plus midpoint), and above them a
  one-line dynamic caption (§7.3).
- **Time scrubber**: bottom-center of the map area (centered on viewport width minus the
  400px panel when panel is open — recenter with a 280ms transition). A segmented control,
  height 44px, radius 999px, `--bg-1` at 88% + blur, containing the 9 time bins as
  segments plus a ▶ play button on the left end (§5.4, §8.1).

### 2.2 Mobile (<768px) and tablet (768–1023px)

- Tablet: same as desktop but panel width 360px and header max-width 380px.
- Mobile: map fills viewport. Header collapses to a 56px top bar (title only, tap to
  expand search + boroughs as an overlay sheet). Legend shrinks to swatches + end labels
  only (no caption), bottom-left, above the scrubber. Time scrubber becomes a horizontally
  scrollable chip row pinned above the bottom sheet.
- **Side panel becomes a bottom sheet**: three detents — peek (88px: tract name +
  headline stat inline), half (55vh, default on tract tap), full (92vh). Drag handle
  36×4px, `--line`, centered, 8px from top. Radius 16px top corners only. Map gets
  `padding-bottom` equal to sheet height in `flyTo` calculations so the selected tract
  is never hidden under the sheet.
- Hover interactions don't exist on touch: first tap = select (no hover-preview state).

---

## 3. The choropleth

### 3.1 Default encoded metric

**P(resolved within 24 hours), all complaint types combined** — the posterior mean per
tract. "Will it be handled by this time tomorrow?" is the single most intuitive question,
splits NYC's distribution near its middle (good visual variance), and matches the default
scrubber position (§5.4: "Same day" segment active on load).

### 3.2 What the map always encodes

The map encodes exactly one number at all times:
**P(resolved within *T*) for complaint type *C***, where *T* comes from the time scrubber
and *C* from the complaint selector. Cumulative, never per-bin — cumulative probabilities
are monotone in *T*, so scrubbing the time control makes every tract *brighten,
never flicker*, which is the hero animation (§8.1). The 9 bins map to cumulative
thresholds: 3h → 24h → 48h → 3d → 7d → 14d → 20d → 31d → "eventually" (the ≥1-month bin's
cumulative view is "within 31 days"; the scrubber's last stop is labeled "31+ days" and
shows P(resolved at all within the study window), which pushes most of the city to yellow —
a satisfying end-of-scrub payoff).

### 3.3 Classing

7 fixed classes on probability: `0–20, 20–35, 35–50, 50–65, 65–80, 80–92, 92–100` (%).
Slightly compressed at the top because cumulative probabilities crowd toward 1. Fixed
breaks (not quantiles) mean color is comparable across complaint types and time
thresholds — essential for the scrub animation to mean anything. Implement as a MapLibre
`step` expression on `fill-color`; switching metric = one `setPaintProperty` call. Wrap the
underlying data swap so paint transitions use `fill-color-transition: {duration: 450, delay: 0}`
for a soft crossfade.

### 3.4 Data plumbing note for the engineer

Tract polygons: one GeoJSON (2020 census tracts, simplified to ~1:80k, quantized —
target ≤ 4 MB gzipped). Probability vectors: a separate `probs.json` keyed by GEOID:
`{geoid: {complaintKey: {cum: [9 floats], lo: [9], hi: [9], n: int, strength: 0|1|2}}}`.
On selector change, write the active cumulative value into each feature via
`map.setFeatureState` (keep paint expression reading from feature-state) — no GeoJSON
re-parse, transitions stay smooth.

---

## 4. The probability display (side panel)

### 4.1 Recommended chart: the **Resolution Ladder**

Nine horizontal **cumulative** bars, one per threshold, top (3 hours) to bottom (31+ days).
Each bar's total length = P(resolved by that time). The *increment* added by that time
window is rendered as a brighter cap segment at the right end of the bar, so a single
graphic carries both the cumulative read ("62% by tomorrow") and the distribution read
("the biggest jump happens on day 2–3"). This beats a PMF-bars-plus-S-curve pairing
because lay users get one chart, one direction of reading, and the cumulative framing
matches how people actually think ("by when?").

Bar geometry: track width = panel inner width (352px), bar height 18px, radius 4px,
10px vertical gap, background track `--bg-2`. Cumulative fill: the ramp color of the
bar's own class (§1.3) at full saturation; increment cap: same color lightened 25%
(or white at 35% overlay). Percentage label right-aligned inside the bar when fill ≥ 64px,
otherwise just outside in `--text-2`. Row label (left, 96px column): "3 hours",
"24 hours", "2 days", "3 days", "1 week", "2 weeks", "20 days", "31 days", "31+ days".

### 4.2 Credible intervals — soft fades, not whiskers

Render the 90% credible interval as a **soft horizontal gradient zone** at the tip of each
bar: solid fill ends at the lower bound, fades linearly to zero at the upper bound
(posterior mean marked by a 2px white tick at 80% opacity). Lay reading: "the solid part is
what we're confident about; the faded tip is the maybe." No caps, no I-beams, no "CI"
jargon. Label it once, in the ladder's footer, as: *"Faded bar ends show the plausible
range for each estimate."* On bars, a hover/tap reveals exact numbers in the tooltip:
"62% · plausible range 55–68%".

### 4.3 Panel layout (top to bottom, ASCII)

```
┌──────────────────────────────────────────────┐  400px wide, 24px padding
│  Census Tract 291 · Bedford-Stuyvesant    ×  │  Fraunces 22px + NTA name 13px --text-2
│  Brooklyn · 1,842 requests since 2025        │  meta line, Inter 12px --text-3
│  ────────────────────────────────────────    │  1px --line divider, 16px margins
│  COMPLAINT TYPE                              │  section label
│  (All) (Noise) (Heat/Hot Water) (Parking)…   │  chip row, wraps to 2 lines max + "More ▾"
│                                              │
│  ┌────────────────────────────────────────┐  │  headline stat card, --bg-2, 12px radius
│  │  62%                 ●●○ Good local    │  │  44px count-up number (class color)
│  │  chance it's resolved     data         │  │  + data-strength dots (§6)
│  │  within 24 hours                       │  │  caption Inter 13px --text-2
│  └────────────────────────────────────────┘  │
│                                              │
│  HOW LONG UNTIL IT'S RESOLVED?               │  section label
│  3 hours   ██████▓░ 34%                      │
│  24 hours  ███████████▓▓░ 62%   ← active     │  active row: --accent 1.5px left rule +
│  2 days    █████████████▓░ 71%               │    row bg --accent-soft (synced to scrubber)
│  3 days    ██████████████▓░ 76%              │
│  1 week    ████████████████▓░ 84%            │  ▓ = increment cap, ░ = CI fade
│  2 weeks   █████████████████▓░ 89%           │
│  20 days   ██████████████████░ 92%           │
│  31 days   ██████████████████▓░ 95%          │
│  31+ days  ███████████████████░ 98%          │
│  Faded bar ends show the plausible range.    │  footer, 11px --text-3
│                                              │
│  COMPARED TO                                 │  section label
│  This tract ▲62% · Brooklyn 57% · NYC 54%    │  comparison strip (§5.7)
│                                              │
│  ▸ How we estimate this                      │  disclosure → methods blurb (§7.5)
└──────────────────────────────────────────────┘
```

Comparison markers on the ladder itself: for the **active** threshold row only, draw two
1.5px vertical ticks over the bar — borough average (`--text-2`, solid) and citywide
(`--text-2`, dashed) — with a micro-legend in the "Compared to" strip. Only the active row,
to avoid tick soup.

---

## 5. Interactions

### 5.1 Hover (desktop only)
- Tract under cursor: `fill-opacity` → `0.95`, outline 1.5px `#FFFFFF` at 0.7 (MapLibre
  feature-state), plus the glow treatment in §8.2. Cursor: `pointer`.
- Tooltip follows cursor at +14px/+14px offset, flipping near edges. Contents (§7.4):
  tract name, active metric value, one-line CI. 240px max-width, `--bg-2` at 92% + blur,
  radius 8px, padding 10px 12px. Appears after 60ms delay, no exit animation.
- Hover never opens the panel. Hover is preview; click is commitment.

### 5.2 Click / select
- Click a tract: it becomes *selected* — persistent 2px `--accent` outline (glow per §8.2),
  panel slides in (280ms), map `flyTo` the tract with `padding: {right: 440}` (or bottom
  padding on mobile), zoom to fit tract with min 12 / max 13.5, duration 900ms.
- Clicking another tract retargets panel contents with a 150ms content crossfade
  (no panel close/open).
- Click empty water / press Esc / click "×": deselect, panel slides out, accent outline
  removed. Selection also drives a `?tract=GEOID` URL param for shareable links.

### 5.3 Complaint-type selector: **chips**, not a dropdown
Chips in the panel (and mirrored in the mobile sheet): the 6 most common citywide types +
"All" first, remainder behind a "More ▾" chip opening a small popover list. Chip: 28px
tall, 12px side padding, radius 999px, `--bg-2` fill, 1px `--line` border, Inter 12px 500.
Active chip: `--accent` border + `--accent-soft` fill + `--text-1`. Chips beat a dropdown
because the categories ARE the story (Noise resolves in hours; Street Condition takes
weeks) and one-tap switching invites the comparison. Chip selection updates *both* the
ladder and the map choropleth (§3.2) with the 450ms paint crossfade.

### 5.4 Time-increment selector: the **scrubber**
Bottom-center segmented control listing the 9 thresholds ("3h · 24h · 2d · 3d · 1w · 2w ·
20d · 31d · 31+"). Active segment: `--accent` text + 2px underline. Changing it re-encodes
the map (§3.2) and moves the active-row highlight in the ladder. Keyboard: ←/→ step it.
The ▶ button on its left end plays the auto-scrub animation (§8.1). Under the segments, a
one-line caption in 11px `--text-3`: current legend caption (§7.3) mirrored.

### 5.5 Address search
Header input, placeholder "Search an address or neighborhood…". Use Nominatim
(`format=jsonv2`, `viewbox` = NYC bounds, `bounded=1`, respect 1 req/s; debounce 400ms).
On result: `flyTo` (1100ms) and auto-select the containing tract via point-in-polygon
(precomputed tract bboxes → polygon test). Show a 12px `--accent` pin dot that fades out
after 2.5s.

### 5.6 Borough shortcuts
Five text buttons in the header card footer: "Manhattan Bronx Brooklyn Queens
Staten Island" + "All NYC". 12px Inter 600, `--text-2`, hover `--text-1`. Click:
`fitBounds` to the borough (900ms, ease default). Active borough underlined in `--accent`.

### 5.7 Comparison affordance
Always-on, zero-config: the panel's "Compared to" strip shows tract vs. borough vs.
citywide for the active threshold + complaint type, with a ▲/▼ glyph and "+5 pts vs.
Brooklyn" phrasing. The two reference ticks on the active ladder row (§4.3) carry the same
values graphically. No side-by-side tract pinning in v1 — it doubles UI complexity for a
feature demos rarely land.

### 5.8 Motion inventory (everything animated, nothing else)
- Panel slide in/out 280ms cubic-bezier(0.2, 0.8, 0.2, 1)
- Choropleth paint crossfade 450ms
- flyTo/fitBounds 900–1100ms
- Ladder bars: width transitions 500ms ease-out, staggered 40ms per row on first paint
- Headline number count-up 700ms (§8.3)
- Chip/scrubber state changes 150ms
- `prefers-reduced-motion`: kill stagger, count-ups, auto-scrub, intro fly-in; keep
  instant state changes.

---

## 6. Sparse data & the shrinkage story

Bayesian shrinkage, told honestly in plain words: when a tract has few observations for a
complaint type, its estimate leans on the neighborhood, then the borough.

### 6.1 The "data strength" indicator
Three dots (each 7px, 4px gaps) beside the headline stat, filled left to right, driven by
effective local sample size for the active tract × complaint combo (thresholds set at data
prep, e.g. n ≥ 150 / 25–149 / < 25):

- ●●● `--good` — label "Strong local data"
- ●●○ `--good` — "Good local data"
- ●○○ `--warn` — "Limited local data — estimate leans on Bedford-Stuyvesant and Brooklyn
  patterns" (label swaps in the actual NTA/borough names; second clause only at this level)

Tooltip on the dots (all levels): *"With only {n} requests of this type here, our model
blends this tract's history with its neighborhood and borough. Fewer local reports =
more blending, and a wider plausible range."*

### 6.2 Reinforcement, not decoration
- At ●○○, the ladder's CI fades get visibly long — the design lets uncertainty *show
  itself* rather than hiding it. Do not cap or shorten fades.
- At ●○○ the headline number also gains a "~" prefix ("~48%") — a tiny honesty cue.
- On the map, do **not** encode uncertainty (hatching/transparency kills the clean look);
  the map shows means, the panel shows doubt. The tooltip's CI line covers the gap.
- Zero-observation combos (probabilities fully borrowed): keep the ladder but add a
  banner strip above it, `--bg-2`, 12px text: *"No {complaint} requests recorded in this
  tract — showing the model's estimate based on {NTA} and {borough}."* Dots render ○○○.

---

## 7. Microcopy (exact strings)

### 7.1 Title & subtitle
- Title: **How Fast Does New York Fix It?**
- Subtitle: *Tap any census tract to see the odds a 311 request gets resolved — in hours,
  days, or a month — based on millions of real service requests.*

### 7.2 Section labels (panel)
`COMPLAINT TYPE` · `HOW LONG UNTIL IT'S RESOLVED?` · `COMPARED TO`

### 7.3 Legend caption (dynamic template)
**"Chance a {complaint} request is resolved within {time}"** — e.g. "Chance a noise
complaint is resolved within 24 hours". With "All" selected: "Chance a 311 request is
resolved within 24 hours". End labels: `0%` and `100%`; center label `50%`.

### 7.4 Tooltip template (hover)
```
{Tract name} · {NTA name}
{62%} chance resolved within {24 hours}
Plausible range {55–68%} · {1,842} requests
```
Line 1: 12px 600 `--text-1`. Line 2: value in class color, 13px 700. Line 3: 11px `--text-3`.

### 7.5 "How we estimate this" (disclosure body, ≤90 words)
> Every dot on this map starts with real 311 requests and how long each one took to close.
> Because some tracts have thousands of requests and others only a handful, we use a
> statistical model that lets small tracts borrow strength from their neighborhood and
> borough — so a quiet block still gets a fair estimate instead of a noisy one. The faded
> ends of each bar show the plausible range: the less local data, the wider the range.
> Resolution times come from the city's own records of when requests were closed.

Followed by: `Data: NYC Open Data, 311 Service Requests · Model: Bayesian hierarchical
(tract → neighborhood → borough) · Not affiliated with the City of New York.`

### 7.6 Misc
- Search placeholder: `Search an address or neighborhood…`
- Search no-result: `Couldn't find that in New York City — try a street + borough.`
- Loading overlay: `Loading 2,300 census tracts…`
- Panel empty (desktop, pre-selection, shown as a small centered hint on the map's right
  edge instead of an empty panel): `Click any tract to see its resolution odds.`
- Play button aria-label: `Play the resolution timeline`

---

## 8. Wow factor — prioritized (do these in order)

1. **The time-scrub "city lights up" animation (▶).** Press play: the scrubber steps
   through all 9 thresholds, ~1.4s per step, and because the metric is cumulative every
   tract only ever brightens — purple Staten Island backwaters catch fire to yellow as the
   week ticks by, while slow tracts visibly lag. The legend caption updates each step.
   This is the single biggest presentation moment; it turns the dataset into a narrative.
   Cost: trivial (a setInterval over the existing scrubber handler + the 450ms paint
   crossfade already specced).
2. **Intro fly-in with choropleth reveal.** On load: basemap at zoom 8.5 over the harbor,
   1.8s `flyTo` to the resting view while tract fills fade from 0 → 0.78 opacity with a
   200ms delay. One `flyTo` + one opacity transition; feels like a title sequence.
   Skipped on `prefers-reduced-motion` and on repeat visits (localStorage flag).
3. **Headline count-up + ladder stagger.** On tract select, the big percentage counts
   0 → value in 700ms (ease-out, tabular numerals) while ladder bars grow left-to-right
   with a 40ms/row stagger. Cheap, and makes every click feel responsive and alive.
4. **Hover glow.** Hovered/selected tract gets a soft luminous edge: MapLibre `line`
   layer, `line-color` `#FFFFFF` (hover) / `--accent` (selected), `line-width` 2,
   `line-blur` 4, drawn under a crisp 1.5px line of the same color. Reads as neon on the
   dark basemap. Two extra layers, no per-frame work.
5. **Shareable deep links.** `?tract=GEOID&type=noise&t=24h` restores full state on load —
   lets the presenter open pre-staged "story" tracts instantly during the talk, and lets
   the audience pull up their own block on their phones. ~30 lines of URL plumbing.

---

## 9. Accessibility & performance notes

- All controls keyboard-reachable; scrubber = radiogroup with arrow keys; focus ring 2px
  `--focus` offset 2px. Chips are `role="radio"` within a radiogroup.
- Contrast: all text tokens ≥ 4.5:1 on their backgrounds (verified for the values above).
  Ramp classes are distinguished by luminance, so grayscale/CVD-safe.
- Ladder has a visually-hidden table equivalent for screen readers.
- GeoJSON simplification (mapshaper, `-simplify 8% keep-shapes`) + gzip; lazy-load
  `probs.json` for non-"All" complaint types if it exceeds ~3 MB gzipped (split per type).
- Target: first paint < 1.5s on hotel Wi-Fi; interaction jank-free at 60fps (all metric
  switches via feature-state/paint, never re-adding sources).

---

## 10. Implementation checklist (top to bottom)

1. Scaffold `index.html`, `style.css`, `app.js`; define all CSS custom properties from §1.2;
   load Fraunces + Inter.
2. Data prep: simplified tract GeoJSON (GEOID, tract label, NTA name, borough) +
   `probs.json` per §3.4 (cumulative vectors, 90% CI bounds, n, strength 0–2, plus
   borough/citywide reference vectors per complaint type).
3. MapLibre map: CARTO dark_nolabels raster source + tracts fill layer + tract-border line
   layer + dark_only_labels raster on top; bounds, zoom limits per §2.1; attribution.
4. Choropleth: 7-class `step` expression on feature-state per §1.3/§3.3; feature-state
   writer for (complaint, threshold) switches; 450ms paint crossfade.
5. Hover: feature-state hover flag, glow line layers (§8.4), tooltip with §7.4 template.
6. Click/select: accent glow, `flyTo` with panel padding, Esc/water-click deselect,
   URL param sync (§5.2, §8.5).
7. Header card: title/subtitle (§7.1), Nominatim search (§5.5), borough `fitBounds`
   buttons (§5.6), collapse-to-pill behavior.
8. Side panel: build §4.3 top-to-bottom — header block, complaint chips, headline stat
   card with count-up + data-strength dots (§6.1), Resolution Ladder with CI fades
   (§4.1–4.2), active-row sync + comparison ticks, "Compared to" strip, methods
   disclosure (§7.5).
9. Time scrubber: segmented control + keyboard arrows + legend/ladder sync (§5.4).
10. Legend with dynamic caption template (§7.3).
11. Sparse-data states: strength thresholds, "~" prefix, zero-data banner (§6).
12. Animations: intro fly-in, ▶ auto-scrub, count-up, ladder stagger,
    `prefers-reduced-motion` guards (§5.8, §8).
13. Mobile: bottom sheet with 3 detents, chip-row scrubber, collapsed header (§2.2).
14. A11y pass (§9): roles, focus rings, hidden table, contrast check.
15. QA: throttled-network load test, 60fps scrub check, share-link restore, no-data
    tract hover exclusion, projector check (dark room + bright room).
