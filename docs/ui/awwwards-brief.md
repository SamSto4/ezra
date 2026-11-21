# Ezra UI v2: design brief from Awwwards references

*2026-11-21. The references were pulled with the Awwwards MCP server (`search_sites`, `get_site_details`, `create_design_brief`, `capture_live_site`, `get_motion_dna`). These are patterns to learn from, not to copy: no copy, imagery, layout or identity is reused.*

## References

| Site | Award | Why it's relevant | What we take |
|---|---|---|---|
| **Cerebrium** (cerebrium.ai) | Site of the Day, Developer Award (score 7.39) | Infrastructure for voice agents and LLMs, with an observability story | Telemetry panels with segmented tabs and mono axis labels; small uppercase "eyebrow" labels with a dot; one accent used sparingly; dark sections that feel engineered, not decorated |
| **Linea Prompt** (lineaprompt.com) | Honorable Mention | A prompt tool whose site is built around "a single line of light threads the whole workflow", plus a ⌘K palette | **The line** as the signature move; an **audit ledger** (mono timestamps, `→` destinations, version tags) for history; numbered cards; generous whitespace |
| **Serus** (serus.ai) | Honorable Mention | A personal privacy AI agent | Calm restraint, an icon-row of capabilities, product shown at full size |
| **Koval SEO Console** (kovalseo.com) | Nominee | A console-style tool | Minimal, typographic, microinteractions only where they confirm an action |

Measured motion (`get_motion_dna`): Linea and Cerebrium use **Lenis** for smooth scroll and CSS keyframes, with no scroll-pinning. Serus runs 72 CSS keyframes with short UI timings (25th percentile 280 ms). None of them hijack the content. The motion lives in small, precise confirmations.

## Why v1 read as sloppy

- Glass, blur and glow everywhere, so nothing stood out (Awwwards juries reject "glass applied everywhere").
- Serif type used for data and labels, so numbers didn't line up and the pages felt soft.
- No transitions between views: content snapped in, and refetches made the page jump.
- The trace was a loose list, not a ledger, so reading it took effort.

## Direction

**A precise, quiet control room.** Dark navy ink, hairline panels, mono telemetry, serif only for page titles. **One line of light** runs through the agent pipeline, and a pulse travels to whichever agent is working right now. It's the one decorative idea, and it carries meaning.

- **Surfaces:** three ink levels instead of glass. Blur stays only on the floating ask bar.
- **Type:** serif for H1 and H2; sans for the interface; mono for every number, id, model and timestamp (tabular figures).
- **Labels:** 11 px uppercase mono eyebrows with a colored dot.
- **Agent colors:** unchanged (Intake blue, Code Joe violet, Builder green, Tester cyan, Guardian amber), now used only on dots, the line and thin accents.
- **Trace:** an audit ledger. Time · agent · what happened · model · tokens · cost, in fixed columns. A row expands smoothly to show the prompt version, the injected context and the reply.
- **Motion** (design-engineer rules):
  - view changes crossfade through the View Transitions API (about 200 ms)
  - rows that are new since the last look fade in once, with a 30 ms stagger, never on every refresh
  - presses scale to 0.97; hover effects only on devices with a fine pointer
  - the line's pulse is a CSS animation of `transform` only, so it runs off the main thread
  - under reduced motion, everything resolves to its final state
- **No WebGL.** Data never waits for an animation.

---

## v3 (2026-11-21): Volt and the orbit

The user's feedback on v2 was that it was smooth, but still felt AI-generic and lacked something unique.
- **Colors, type and shapes now come from the user's own design system, Volt:** a quiet ground with lines first, cobalt (`#5b82ff`) for actions and selection, Volt lime (`#c6f432`) only for "working right now", Space Grotesk for headings with Inter for text, and pill buttons. This drops the blue-purple gradients and the serif-on-navy look, which are common AI-product tropes.
- **Agents are told apart by two-letter monograms** (EZ, CJ, BU, TE, CK, GU), not a rainbow of hues.
- **Signature: the Ezra orbit.** Ezra sits at the center, with its agents as pads around it. Each pad shows live figures (calls, cost, model). A lime packet travels a spoke while that agent works. This adapts Strike Drive's hub map ("live figures on every pad"; Awwwards nominee) into flat SVG, with no WebGL.
- **Fuller coverage of what Ezra can do:**
  - a System page (routing and prices, loop limits, the D-002 verdict table in plain words, the decision log, money saved by caching)
  - the branch diff on each task
  - loop counters (fix rounds, correction cycles, reviews, HOLDs, calls)
  - each verdict explained with its rule
  - a lower budget cap for a run
  - a custom extension when approving a HOLD
  - cost per successful task, with a trend line, on Home
