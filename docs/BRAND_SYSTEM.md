# SynthPost Brand System

SynthPost uses a high-contrast editorial identity: warm paper, black ink, a
serif wordmark, and moving broadcast ribbons. The system is implemented as
code-native React, CSS, and SVG so it remains sharp in the Studio and at video
resolution without loading remote assets.

## Identity

- Wordmark: `SynthPost.` with a red signal period.
- Seal: a white editorial `S` reversed out of an ink-black circle.
- Tagline: `The signal. The story.`
- Ribbon copy: short operational phrases such as `Verified source` and
  `Broadcasting live`; ribbons are decorative and never carry essential UI
  information.
- Surfaces: ink black and warm off-white rather than cool blue-black and pure
  white. The Studio remains dark to preserve the control-room workflow.

## Genre colour

| Canonical genre | Ribbon treatment | Common aliases |
| --- | --- | --- |
| World | signal red → deep red | politics, geopolitics, global, international |
| Technology | cobalt → violet | tech, AI, science |
| Finance | turquoise → emerald | business, markets, economy |
| Culture | signal pink → berry | entertainment, internet culture, media |
| Climate | green → teal | environment, energy |
| General | signal red → crimson | unmatched categories |

The Studio mapping lives in `web/src/brand/identity.ts`. The renderer mapping
lives in `compositor/remotion_renderer/src/styles/brand.ts`. Keep both mappings
equivalent when adding a genre; this small duplication avoids coupling the
browser bundle to the renderer package.

## Components

- Studio wordmark and seal: `web/src/components/BrandMark.tsx`
- Studio ticker ribbon: `web/src/components/BrandRibbon.tsx`
- Renderer ribbon: `compositor/remotion_renderer/src/components/BrandRibbon.tsx`
- Renderer wordmark: `compositor/remotion_renderer/src/components/LogoBug.tsx`
- Renderer lower third: `compositor/remotion_renderer/src/components/LowerThird.tsx`

Ribbon elements use `aria-hidden` or `pointerEvents: none`. Do not place
controls, source attribution, or required text inside them. Motion respects
`prefers-reduced-motion` in the Studio and is derived from Remotion frames in
rendered video, which keeps output deterministic.
