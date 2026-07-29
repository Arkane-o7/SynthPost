# How Money Works — forensic reconstruction specification

Status: **analysis complete; no implementation performed**

Evidence: [18-video timestamp library](./EVIDENCE_LIBRARY.md)
Quantitative data: [corpus metrics](./analysis/corpus_metrics.json)
Contact sheets: [`frames/`](./frames/)
Narrator/chart/document motion strips: [`analysis/motion-strips/`](./analysis/motion-strips/)

## Deliverables index

| Required deliverable | Location |
|---|---|
| Videos and timestamped evidence | Evidence library; Parts VI and VII |
| Brand, colour, type, spacing | Part I |
| Narrator inventory, poses, animation | Part II |
| Writing, narration, hooks | Part III |
| Visual taxonomy and asset rules | Part IV |
| Template catalogue and measurements | Part V |
| Complete-section visual sequences | Part VI |
| Editing, pacing, and motion | Part VII |
| Transition library and matrix | Part VIII |
| Image sourcing/treatment | Part IX |
| Charts, maps, documents, statistics | Part X |
| Voice, music, mix, sound design | Part XI |
| Script-to-visual decision system | Part XII |
| Workflow and automation architecture | Part XIII |
| Minimum/manual asset library | Part XIV |
| Rights, limits, accuracy checklist | Part XV |
| 78-second prototype specification | Part XVI |

## Executive finding

The current How Money Works style is not “stock footage plus a PNG narrator.” It is a coherent **editorial research-desk theatre**:

1. The script starts with an apparent fact pattern.
2. It rapidly accumulates contradictions, examples, or absurd details.
3. Visuals alternate among **evidence**, **explanation**, **context**, and **commentary**.
4. A green graph-paper desk or cork investigation board makes unrelated assets feel authored by one publication.
5. The `$?`-headed suited presenter is an editorial voice, not a lip-synced anchor. It appears when the narration needs a bridge, judgement, joke, question, or explanation—not on every sentence.
6. A scene persists across a complete idea beat. Cards, highlights, chart lines, logos, props, and poses change *inside* that scene. The opening animation is not replayed for every sentence.
7. Most transitions are short and utilitarian. Taste comes from the sequence of visual roles and the quality of the selected evidence, not from elaborate effects.

The reconstruction target should be the **2025–26 system**, not an average of the entire catalogue. The 2021–23 videos reveal the channel’s enduring writing habits and evidence instinct, but their mostly full-screen stock/archival treatment is a legacy system. The transition is visible by comparing the footage-led [Meaningless Jobs opening](https://www.youtube.com/watch?v=uK3OBAxCi6k), the flat diagram language in [Money Laundering at 1:50](https://www.youtube.com/watch?v=0uLhh5GSxsQ&t=110s), the hybrid green-paper visuals in [Housing at 0:40](https://www.youtube.com/watch?v=1zjcZ661ups&t=40s), and the current persistent board in [Peter Thiel at 0:04](https://www.youtube.com/watch?v=_W3qPymBEBA&t=4s).

The single highest-impact correction for Meridian is therefore:

> Plan and render **idea beats**, not sentences. Keep a template alive for 5–18 seconds and mutate its contents. A new sentence does not imply a new template or a replayed entrance.

---

# Part I — brand identity

## 1. Visual identity

### 1.1 Core palette

Values below are estimates from sampled current frames, normalized for an implementation palette. The source videos contain texture, vignettes, colour grading, compression, and topic-specific variations.

| Role | Estimated value | Usage |
|---|---:|---|
| HMW primary green | `#187140` | Logo disc, brand tokens, small accents |
| Graph-paper mid green | `#488050` | Current default editorial desk |
| Graph-paper shadow green | `#305535` | Vignette, depth, edge falloff |
| Graph-paper highlight | `#578D5D` | Lit centre / raised surface |
| Deep green-black | `#0A1218` | Dark transitions and edge treatment |
| Cork base | `#AA815C` | Investigation-board surface |
| Cork highlight | `#CD9E72` | Lit cork fibres |
| Cork shadow | `#75402B` | Board edge / vignette |
| Wood frame dark | `#403425` | Chart/cork frame |
| Suit navy | `#1B283C` | Mascot body; cool counterweight |
| Paper white | `#EFF0EC` | Documents and headline clippings |
| Paper cream | `#FBF0DA` | Warm vintage/source cards |
| Ink | `#11151F` | Editorial serif text |
| Highlight yellow | `#F2E943` | Relevant document passage only |
| Pushpin/yarn red | `#D82E2E` | Investigation relationships and emphasis |
| Soft shadow | `rgba(10, 12, 12, .32)` | Paper/card separation |

The primary combination is **green + warm paper + black ink**. Cork/wood is a story-specific secondary world used for individuals, history, relationships, and “how did we get here?” investigations. The red is not a general accent; it belongs to physical evidence-board grammar. See the persistent green scene in [Big Tech at 1:02–1:16](https://www.youtube.com/watch?v=swtfbef3HhM&t=62s) and the cork network in [Peter Thiel at 3:20](https://www.youtube.com/watch?v=_W3qPymBEBA&t=200s).

### 1.2 Texture and material

The system is deliberately tactile:

- Green surfaces have a fine white grid, paper/fabric grain, a soft central light, and darker edges.
- Torn headlines have irregular lower edges, subtle wrinkles, newsprint noise, and a shallow shadow.
- Cork boards have wood frames, visible fibres, pushpins, red yarn, Polaroids, tape, and slightly inconsistent rotations.
- Charts are frequently placed inside thin wood frames rather than floating as raw browser screenshots.
- Documents sit among desk props—pencils, erasers, folders, photos, a cup rim, rulers, or frames—so the frame reads as a workspace rather than a slideshow.

This material treatment unifies low-resolution news clips, screenshots, generated charts, archival images, and cut-outs. The paper/document treatment is visible in [Silicon Valley at 3:10](https://www.youtube.com/watch?v=ShGT-fY7S98&t=190s); the current chart frame in [Big Tech at 1:26](https://www.youtube.com/watch?v=swtfbef3HhM&t=86s); and the relationship-board build in [Peter Thiel at 3:40](https://www.youtube.com/watch?v=_W3qPymBEBA&t=220s).

### 1.3 Typography

The exact font files are not public. The following is a close functional reconstruction, not a claim about the private source files.

| Function | Observed character | Recommended substitute | Weight |
|---|---|---|---|
| Torn news headline | Newspaper/editorial serif | `Newsreader`, `Libre Baskerville`, or `Georgia` | 650–800 |
| Source masthead | Compact publication mark | Preserve source logo where licensed; otherwise `Inter` | 600–700 |
| Kinetic question / statistic | Condensed bold sans | `Roboto Condensed`, `Archivo Narrow`, or `Anton` | 800–900 |
| Chart title | Neutral technical sans | `Arial`, `Inter`, or `Geist` | 600–700 |
| Chart axes/labels | Neutral technical sans | `Arial` or `Inter` | 400–600 |
| Handwritten board label | Casual marker/hand | `Patrick Hand` or `Kalam` | 400–600 |
| Legacy green-paper explanations | Condensed sans | `Roboto Condensed` | 700 |

Rules:

- Headline clippings use title case or source-original capitalization; they are not forcibly converted to all caps.
- Kinetic questions and short punchline fragments may use all caps, centred, with tight leading.
- Large numbers use tabular numerals where possible and include units in a smaller size.
- Text is normally one idea per card. The visual system does not dump a paragraph on screen except when showing a source document.
- In a 1920×1080 master, a single torn headline is approximately 42–64 px, chart titles 28–36 px, source labels 18–24 px, large statistics 96–160 px, and utility/source text 16–22 px.
- Headline leading is approximately 0.95–1.08; body/document annotation leading 1.2–1.4.
- Headline letter spacing is neutral to slightly tight (`-0.01em` to `-0.025em`); labels can use `0.04em`–`0.08em`.

Examples: editorial clipping at [Big Tech 0:02](https://www.youtube.com/watch?v=swtfbef3HhM&t=2s), kinetic contradiction at [AI and jobs 0:40](https://www.youtube.com/watch?v=MYB0SVTGRj4&t=40s), and large statistic at [Family fortunes 0:10](https://www.youtube.com/watch?v=Qb8tTA8Dmfo&t=10s).

### 1.4 Image framing and effects

- Full-screen footage is normally borderless and cropped to fill.
- Evidence assets receive a frame: torn paper, Polaroid, wood frame, browser/document page, or card.
- Cut-outs receive a soft 12–28 px shadow at 1080p; a hard white sticker outline is uncommon in the current serious mode and better reserved for jokes.
- Paper/card corner radii are effectively 0–8 px; the irregular torn edge matters more than rounded corners.
- Charts and board frames use square or minimally rounded corners.
- Shadows are soft and shallow: approximately `0 12px 28px rgba(0,0,0,.25)`, with an additional 1–2 px contact shadow.
- Perspective rotations are restrained, typically ±1.5° for primary documents and up to ±6° for secondary scraps/Polaroids.
- Background footage behind a headline is frequently blurred and darkened so the clipping reads instantly, as at [Big Tech 0:02](https://www.youtube.com/watch?v=swtfbef3HhM&t=2s).

### 1.5 Composition grid

Use a 16:9, 1920×1080 master.

- Action-safe margin: 64 px; title/source-safe margin: 96 px.
- Primary content grid: 12 columns, 64 px outer margins, 24 px gutters.
- Default editorial object area: x 6–94%, y 5–94%.
- A single headline card: x 10–90%, y 8–36%.
- A framed chart/document: x 10–90%, y 7–91%.
- Split explainer: evidence x 6–60%, mascot x 62–95%.
- Mascot alone: 55–92% of frame height; miniature comic use can fall to 15–35%.
- Source attribution stays in the lower 5–8% of the visual object, never in YouTube’s bottom-most player-safe strip.
- Negative space is directional: if the mascot points right, reserve the right-centre region for the referenced object.

The mascot/board relationship at [Peter Thiel 0:44–0:58](https://www.youtube.com/watch?v=_W3qPymBEBA&t=44s) and the chart/mascot relationship at [Oil 6:40–7:00](https://www.youtube.com/watch?v=e-2GoFws3yE&t=400s) demonstrate this directional layout.

### 1.6 Logo and watermark

The current mascot’s round green `$?` head is simultaneously character face and logo. This is stronger than a persistent corner watermark. Within the reviewed frames, a large permanent watermark is not the defining system; brand recall comes from the green surface, paper language, and recurring mascot. For Meridian, use its own original symbol/head and do not copy the `$?` mark.

---

# Part II — narrator character system

## 2. What the mascot actually is

The current character is a **logo-headed, suited human-body cut-out system**. It is not a conventional talking avatar:

- The head is a flat circular logo locked to the neck/body.
- There is no mouth animation or facial lip sync.
- Expressiveness comes from full-body pose, hand gesture, scale, placement, nearby props, and timing.
- Several appearances show actual changes in arm/body position, indicating either short keyed live-action/green-screen clips or multiple pose clips—not one static PNG with only a bounce.
- Pose changes usually occur by a fast cut or short blurred transition inside a persistent background.
- The character can be miniaturised, placed inside a scene, made to point at a chart, or used as part of a visual joke.

The transition from arms-crossed to shrug at [Big Tech 1:12–1:14](https://www.youtube.com/watch?v=swtfbef3HhM&t=72s), the multiple poses on one board at [Peter Thiel 0:44–0:58](https://www.youtube.com/watch?v=_W3qPymBEBA&t=44s), and the miniature covered-car gag at [Car market 1:14](https://www.youtube.com/watch?v=mUBBqAjVuco&t=74s) rule out “one static narrator PNG” as an adequate reconstruction.

## 3. Minimum narrator asset library

### Core body clips/poses

1. Neutral, arms at sides, front-facing.
2. Neutral, one hand lightly raised.
3. Arms crossed / sceptical hold.
4. Open-palms shrug, low.
5. Open-palms shrug, high/wide.
6. Point up-left.
7. Point up-right.
8. Point horizontally left.
9. Point horizontally right.
10. Point down toward a chart/value.
11. One index finger raised (“one important thing”).
12. Hand on chin / thinking.
13. Hands clasped in front / transition.
14. Palms pressed / pleading or mock-prayer.
15. Facepalm.
16. Looking/leaning left.
17. Looking/leaning right.
18. Seated neutral.
19. Seated explaining.
20. Crouched/miniature interaction.
21. Peeking from behind a card/object.
22. Holding a document.
23. Holding or revealing a prop.
24. Walking/entering two-step clip.
25. Exit/duck/fall clip for punchlines.

### Head/symbol variants

26. Standard Meridian logo head.
27. Question/confusion variant.
28. Alarm/concern variant.
29. Positive/approval variant.
30. Topic-specific temporary head swap for a visual joke.
31. Small icon head for background characters.

Unlike a face-led avatar, these should remain graphically simple. Emotional meaning comes mainly from pose and context.

### Accessories and scene interactions

32. Speech bubble: neutral.
33. Speech bubble: distressed/hand-drawn.
34. Thought bubble.
35. Pointer/laser pointer.
36. Clipboard/document.
37. Money/cash/coin props.
38. Laptop/desk.
39. Projector/whiteboard.
40. Chair/stool.
41. Product pedestal/reveal cover.
42. Magnifying glass/investigation prop.
43. Chart labels/arrows that the hand can track.
44. Costume variants only when the story requires a role: lab coat, safety vest, historical suit, casual creator. These are jokes/roles, not routine randomisation.

### Required motion variants

Each core pose needs:

- a 6–12 frame entry at 24/30 fps;
- a 2–5 second usable hold or subtle live-body idle;
- one compatible gesture clip;
- a 6–10 frame exit;
- clean alpha;
- a consistent neck/head attachment point;
- hand and prop occlusion mattes where interaction demands them.

## 4. Pose selection grammar

| Narrative trigger | Pose | Placement | Typical duration | Example |
|---|---|---|---:|---|
| “The obvious explanation is…” | Neutral/explaining | 25–35% from left or right | 5–9 s | [Big Tech 1:12](https://www.youtube.com/watch?v=swtfbef3HhM&t=72s) |
| Contradiction / “but” | Arms crossed → shrug | Centre or opposite evidence | 6–10 s | [Big Tech 1:12–1:14](https://www.youtube.com/watch?v=swtfbef3HhM&t=72s) |
| Key claim / one caveat | Index finger raised | Lower corner, pointing into negative space | 4–7 s | [Big Tech 1:50](https://www.youtube.com/watch?v=swtfbef3HhM&t=110s) |
| Interpret a chart | Point at line/value | Beside chart, not over data | 5–12 s | [Oil 6:50](https://www.youtube.com/watch?v=e-2GoFws3yE&t=410s) |
| Uncertainty | Hand on chin | Lower third | 4–7 s | [Big Tech 1:56](https://www.youtube.com/watch?v=swtfbef3HhM&t=116s) |
| Absurd list | Pose changes as objects accumulate | Centre/lower third | 10–18 s | [Peter Thiel 0:44–0:58](https://www.youtube.com/watch?v=_W3qPymBEBA&t=44s) |
| Punchline | Facepalm, miniaturise, costume, prop | Context-specific | 2–6 s | [Consumption 0:50](https://www.youtube.com/watch?v=aw7ayuTZxi0&t=50s) |
| New section | Neutral entry | Clean board/room | 4–8 s | [Car market 2:32](https://www.youtube.com/watch?v=mUBBqAjVuco&t=152s) |
| Abstract mechanism | Presenter + diagram | Edge of diagram | 8–16 s | [AI/jobs 1:10](https://www.youtube.com/watch?v=MYB0SVTGRj4&t=70s) |

Do not summon the mascot merely because the visual planner has no asset. It is not a fallback. In current videos, evidence-heavy runs can remain mascot-free for 30–90 seconds. A reasonable target is **0.8–1.6 entrances per minute**, with clustering around conceptual bridges.

## 5. Character animation specification

- Entry: 180–360 ms, usually vertical spring, slide, or rapid scale with directional blur.
- Exit: 140–300 ms, hard cut or reversed slide/duck.
- Pose cut: 0–120 ms if comic; 160–240 ms blur/whip if explanatory.
- Idle: 1–3% scale drift or a true short body clip; avoid perpetual bobbing.
- Overshoot: 3–7%, cubic/back easing.
- Head follows body translation/scale exactly; no independent float.
- Head may have a very small counter-rotation (≤2°) to keep it graphic.
- Long holds need either a pose change, hand motion, nearby object reveal, or camera push every 3–6 seconds.
- Lip sync should **not** be used for the HMW-like system. It changes the character from editorial symbol to talking avatar and competes with the dry narration.

Technical recommendation: record or animate a modular full-body actor library on chroma/alpha, then attach the original Meridian symbol as a tracked head layer. Store each clip with `anchorPoint`, `lookDirection`, `handTargets`, `compatibleProps`, `entryVariants`, and `exitVariants`. Static transparent PNGs are acceptable for miniature jokes and quick reaction holds; the core explaining poses should be short alpha-video clips.

---

# Part III — writing and narration

## 6. Quantitative voice profile

- Weighted average: **196.7 WPM** across 4:19:31.
- Median per-video rate: **196.0 WPM**.
- Median reliable sentence: **21 words**.
- Current examples cluster around 189–201 WPM.
- Median detected pause: **0.34–0.36 seconds**; pauses over one second are rare.
- Questions occur selectively. Reliable captions show roughly 1–3 questions per 1,000 words in most videos, with the abstract 2021 “Meaningless Jobs” video at 4.5/1,000. Auto-caption punctuation undercounts six videos.

The result feels brisk because the narration has little dead air, but it remains intelligible through clear syntax, emphatic nouns/numbers, and visual rest beats.

## 7. Script voice

The narrator is:

- informed but conversational;
- sceptical of fashionable explanations;
- comfortable addressing the viewer as “you”;
- dry rather than gag-heavy;
- willing to make a judgement, then qualify it;
- specific with names, numbers, dates, and causal mechanisms;
- self-aware about recurring topics and production circumstances;
- more interested in the contradiction behind the headline than the headline itself.

The humour is primarily:

- **understatement** after an extreme fact;
- **over-specificity** in a list;
- a parenthetical caveat;
- a visual comparison;
- a mild insult aimed at institutions or hype;
- delayed callback;
- the narrator implicating himself (“as a former finance bro…”);
- literalising a metaphor visually.

Examples include the accumulation of eccentric details before the central “why?” in [Peter Thiel 0:00–1:20](https://www.youtube.com/watch?v=_W3qPymBEBA), the morale aside in [Big Tech 0:28](https://www.youtube.com/watch?v=swtfbef3HhM&t=28s), and the fast-food industry’s “confusing” response to ideal conditions in [McRecession 0:00–1:00](https://www.youtube.com/watch?v=Baj7AINpqXA).

## 8. Story architecture

### 8.1 Current opening formula

1. **Concrete anomaly (0–8 s).** Start on a name, event, number, or behaviour—not a generic topic definition.
2. **Evidence pile (8–35 s).** Add 3–8 examples quickly.
3. **Dry comment (20–45 s).** Release pressure and establish voice.
4. **Escalation (30–70 s).** Show that the apparent story is bigger or stranger.
5. **Central contradiction/question (45–90 s).** “If X is true, why is Y happening?”
6. **Promise of mechanism (70–120 s).** State what must be understood, not merely what happened.
7. **First argument.** Usually begins around 1:15–2:00 in current long videos; older 10-minute videos often enter it around 1:20 after a legacy logo bumper.

Peter Thiel spends the opening accumulating apparently unrelated behaviours before asking why the publicity is deliberate; Big Tech counts layoffs before revealing headcount recovery; oil recounts repeated reversals before asking why sophisticated markets keep responding. These are the same structural move in three topics: [Thiel](https://www.youtube.com/watch?v=_W3qPymBEBA), [Big Tech](https://www.youtube.com/watch?v=swtfbef3HhM), [Oil](https://www.youtube.com/watch?v=e-2GoFws3yE).

### 8.2 Body formula

Each section should do four jobs:

1. Make a claim.
2. Show the mechanism or historical cause.
3. Present evidence or a counterexample.
4. Resolve the local question while opening the next one.

Sections average roughly **75–150 seconds** in current long videos. Inside a section, use 3–7 idea beats of 8–25 seconds. A section does not need a visible title every time; visual-world changes and transition phrases often provide enough structure.

### 8.3 Conclusion formula

1. Return to the opening contradiction.
2. Separate the sensational explanation from the durable mechanism.
3. State the implication for companies, workers, consumers, investors, or institutions.
4. Admit the principal uncertainty.
5. End on a concise judgement or ironic restatement—not a motivational speech.
6. Keep CTA short and tonally separate.

## 9. Reusable writing formulas

### Contradiction hook

> `[Actor/system] has done [surprising measurable thing].`
> `That should mean [obvious outcome].`
> `Instead, [opposite outcome].`
> `So either [common explanation] is wrong, or [deeper mechanism] matters more.`

### Company introduction

> Start with a recent operational result, compare it with the firm’s historical norm, add one competitor/industry comparison, then ask what changed in the underlying business.

### Individual introduction

> Accumulate a highly specific list of actions; contrast public eccentricity with private power/resources; ask whether the behaviour is random or instrumental.

### Historical context

> Begin at the first decision that makes the present outcome possible. Use a timeline of incentives and constraints, not a biography or chronology for its own sake.

### Economic explanation

> Define the actors and what each wants; show the transaction/constraint; change one variable; demonstrate the second-order effect; then return to the real case.

### Statistic reveal

> Establish the denominator before the number. State the number once, compare it to an intuitive baseline, explain why the comparison matters, then show the source.

### Counterargument

> “The obvious explanation is X, and it does explain A. It does not explain B.” Follow with the missing mechanism.

### Joke

> Keep the spoken line dry. Let the visual perform the exaggeration. Do not add a second spoken punchline explaining the first.

### Section transition

> Close the previous local question, identify the remaining contradiction, then change the visual world. Avoid “Now let’s talk about…”.

## 10. Script constraints for Meridian

- 190–205 WPM target, adjusted downward to 180–195 for dense technical/mechanism passages.
- 18–24 word median sentence.
- Paragraph/beat: 45–90 spoken words.
- Section: 250–450 words for a 12–18 minute video.
- One genuine rhetorical question every 45–90 seconds; do not turn every transition into a question.
- One dry joke/aside every 30–60 seconds, with a stronger visual punchline every 60–120 seconds.
- Explicit visual phrases such as “as you can see” should be rare. The reviewed narration normally remains intelligible as audio while the parallel visual plan provides evidence, context, or irony.
- Introduce the premise within 10 seconds.
- Reveal the central contradiction within 45–90 seconds.
- Begin the first causal argument within 90–120 seconds.
- Every factual section needs at least one evidence visual; every abstract section needs a model/diagram or concrete example.
- Do not write explicit template commands into narration. Visual direction belongs in a parallel beat plan.

---

# Part IV — visual taxonomy and selection rules

## 11. Complete visual taxonomy

| Category | Trigger | Duration | Treatment | Function |
|---|---|---:|---|---|
| Full-screen news footage | Recent event/person/company | 2–7 s | Crop to fill; retain useful chyron | Authority/context |
| Archival footage | Historical event/process | 3–9 s | Native B&W/colour; modest crop | Time/place authenticity |
| Stock footage | Generic action/environment | 2–6 s | Use sparingly; literal or metaphorical | Rhythm/context |
| Company/product footage | Named firm/product | 2–7 s | Beauty shot, factory, store, advert | Specificity |
| Interview clip | Expert/actor/primary figure | 3–10 s | Usually full screen | Voice/character/evidence |
| Headline clipping | Claim has a public source | 4–10 s | Torn paper, source label, shadow | Evidence |
| Headline stack | Repetition/pattern | 6–14 s | Accumulate 2–6 cards | Scale/pattern |
| Document/report | Formal evidence | 7–16 s | Desk, page, yellow highlight | Proof |
| Website/social screenshot | Platform behaviour/public statement | 4–10 s | Browser/card/phone crop | Evidence or humour |
| Framed chart | Trend/comparison | 7–15 s | Wood frame; animate series | Explanation/proof |
| Large statistic | One decisive number | 3–7 s | Large numerals + baseline | Emphasis |
| Map | Location, flow, geopolitical constraint | 6–15 s | Minimal labels; progressive reveal | Orientation/mechanism |
| Timeline | Causal sequence | 8–20 s | Nodes/cards reveal incrementally | History/causality |
| Relationship board | People/institutions/network | 10–30 s | Cork, pins, string | Investigation/system |
| Diagram | Abstract financial/legal mechanism | 8–20 s | Icons, arrows, staged build | Explanation |
| Comparison screen | Two systems/options | 6–12 s | Balanced columns or board cards | Contrast |
| Portrait card | Introduce/return to person | 4–9 s | Polaroid/cut-out + label | Character |
| Logo/product montage | List of companies/brands | 4–10 s | Tokens accumulate around narrator | Compression |
| Cut-out collage | Many actors/objects | 5–12 s | Shadows, depth, controlled overlap | System or joke |
| Mascot explainer | Interpretation/bridge | 5–12 s | Beside evidence/diagram | Editorial voice |
| Mascot reaction | Joke/doubt/understatement | 2–6 s | Strong pose; minimal text | Tone |
| Meme/reaction image | Punchline or cultural shorthand | 1.5–4 s | Abrupt; deliberately low polish possible | Humour |
| Kinetic text | Central question/short phrase | 2–6 s | Condensed bold; one phrase | Structural emphasis |
| Section-reset room | New conceptual chapter | 4–10 s | Sparse wall/board/projector | Breath/transition |
| Sponsor panel | Ad read | Variable | Clearly different but brand-compatible | Commercial |

### Visual-role rule

Before choosing a template, classify the beat:

- **Illustrate**: show the thing being described.
- **Prove**: show the source, data, document, quote, or primary footage.
- **Explain**: show the relationship/mechanism.
- **Orient**: establish person, place, time, or company.
- **Comment**: mascot reaction, metaphor, or ironic image.
- **Reset**: low-density shot, footage, or section transition.

The current channel rotates these roles. Generic explainers fail because they choose only “illustrate.” The document highlight in [Silicon Valley 3:10](https://www.youtube.com/watch?v=ShGT-fY7S98&t=190s) proves; the chart in [Consumption 1:34](https://www.youtube.com/watch?v=aw7ayuTZxi0&t=94s) explains; the facepalm at [0:50](https://www.youtube.com/watch?v=aw7ayuTZxi0&t=50s) comments.

## 12. Asset-selection rules

### Named company

Priority: current company footage → product/store/factory → official logo/product cut-out → source headline → mascot only if interpretation is needed.

### Named person

Priority: primary interview/action footage → labelled portrait card → event/archival footage → relationship board. Avoid repeating one headshot.

### Statistic

If one number is the point, use a statistic scene. If change over time matters, use a chart. If the number is contested or central to credibility, show the source document after the reveal.

### Country/location

Use establishing footage when atmosphere matters; use a map only when geography changes the mechanism (routes, borders, resources, exposure). A flag alone is an accent, not an explanation.

### Historical event

Use archival footage/photo first, then timeline only when ordering matters. Preserve imperfect quality when it signals authenticity.

### Abstract concept

Use a transactional diagram, physical metaphor, staged room, or mascot interaction. Do not search stock footage for the abstract noun.

### Joke/sarcasm

Use mascot, literalised metaphor, low-resolution meme, or an absurdly formal chart/diagram. The visual may contradict or exaggerate narration.

### Source/quote

Show the source name, enough page context to establish authenticity, then highlight only the relevant line(s). Do not display a fabricated “quote card” when a real document exists.

---

# Part V — recurring template catalogue

All dimensions below are percentages of a 1920×1080 frame. Durations are editorial ranges, not fixed constants.

## T01 — Single torn headline

**Purpose:** establish one sourced claim.

**Inputs:** source, headline, optional date, optional background footage/image.

**Layout:** headline paper x 8–92%, y 8–34%; blurred/darkened footage fills frame; source centred above headline; paper shadow 12–24 px.

**Behaviour:** card slides/drops in over 240–360 ms; hold 4–8 s; optional 2% camera push. Do not animate every word.

**Selection:** a claim is important enough to source but not part of a repeated pattern.

**Evidence:** [Big Tech 0:02](https://www.youtube.com/watch?v=swtfbef3HhM&t=2s).

## T02 — Accumulating headline stack

**Purpose:** prove repetition, saturation, or industry-wide scope.

**Inputs:** 2–6 headlines, source labels, optional cut-out/mascot.

**Layout:** green desk; cards occupy x 8–92%, y 8–82%, each rotated ±1.5° and vertically staggered.

**Behaviour:** first card establishes scene; subsequent cards enter every 0.7–2.0 s. The background and prior cards persist. Final composition holds 2–4 s.

**Selection:** narration contains a list of comparable events.

**Evidence:** [Big Tech 0:14–0:28](https://www.youtube.com/watch?v=swtfbef3HhM&t=14s).

## T03 — Editorial desk document highlight

**Purpose:** prove a precise claim.

**Inputs:** document page, source, highlight boxes/lines, optional portrait, props.

**Layout:** page x 12–88%, y 5–96%; desk visible at edges; portrait/prop occupies no more than 25% and must not cover highlighted text.

**Behaviour:** document/page replaces the previous desk object with a 250–450 ms paper sweep; relevant line receives a 0.6–1.5 s yellow marker reveal; slow 2–5% push-in.

**Selection:** primary report, paper, filing, study, court order, or quoted paragraph is central.

**Evidence:** [Silicon Valley 3:10–3:16](https://www.youtube.com/watch?v=ShGT-fY7S98&t=190s).

## T04 — Wood-framed chart

**Purpose:** show trend, comparison, or contradiction.

**Inputs:** title, axes, 1–5 series, source, annotations, endpoint labels.

**Layout:** frame x 8–92%, y 6–94%; plot x 15–87%, y 17–82%; title y 10–17%; source y 84–89%.

**Behaviour:** board enters/settles; axes and grid already present; series draw left-to-right over 2.5–5.5 s; labels pop after lines; hold 2–6 s; mascot may enter after the data is visible.

**Selection:** time/sequence or comparison is essential.

**Evidence:** [Big Tech 1:26–1:34](https://www.youtube.com/watch?v=swtfbef3HhM&t=86s), [Consumption 1:32–1:40](https://www.youtube.com/watch?v=aw7ayuTZxi0&t=92s).

## T05 — Large statistic

**Purpose:** emphasise one result.

**Inputs:** value, unit, comparison/base, source.

**Layout:** number x 8–92%, centred or left-aligned; value 9–16% frame height; supporting phrase 3–5%; source 1.5–2%.

**Behaviour:** count/scale only if mathematically meaningful; otherwise a direct pop/slide. Add one comparison object, not decorative clutter.

**Evidence:** [Family fortunes 0:10](https://www.youtube.com/watch?v=Qb8tTA8Dmfo&t=10s).

## T06 — Portrait dossier

**Purpose:** introduce a person and retain identity.

**Inputs:** portrait(s), name, age/date/role, one or two relevant artefacts.

**Layout:** Polaroid/photo x 8–42%, secondary evidence x 45–92%; cork or green desk.

**Behaviour:** portrait pins/slides in first; label follows; later evidence attaches to the existing dossier.

**Evidence:** [Peter Thiel 0:04](https://www.youtube.com/watch?v=_W3qPymBEBA&t=4s).

## T07 — Cork relationship board

**Purpose:** reveal a network or investigation.

**Inputs:** people, institutions, places, flags, labelled nodes, typed edges, evidence snippets.

**Layout:** full cork board inside 3–5% wood frame; nodes occupy a legible graph with at least 70 px separation at 1080p.

**Behaviour:** central node first; related nodes pin in; red string draws between established nodes; camera reframes/pushes as graph expands. Build over 12–30 s; do not reset between sentences.

**Evidence:** [Peter Thiel 3:20–4:20](https://www.youtube.com/watch?v=_W3qPymBEBA&t=200s).

## T08 — Timeline board

**Purpose:** show causal chronology.

**Inputs:** dated nodes, events, images, phase labels.

**Layout:** horizontal or serpentine track inside cork/green workspace; 3–7 nodes visible; older nodes can compress.

**Behaviour:** new node reveals every 1.0–3.0 s in sync with narrated event; connecting line appears after node; camera pans only when track exceeds safe area.

**Evidence:** [Peter Thiel 3:40](https://www.youtube.com/watch?v=_W3qPymBEBA&t=220s).

## T09 — Transaction/mechanism diagram

**Purpose:** explain abstract legal, financial, or economic flow.

**Inputs:** actors, objects, arrows, labels, states before/after.

**Layout:** 2–5 nodes; 15% minimum whitespace; arrows never cross labels.

**Behaviour:** introduce actors before arrows; animate one transaction/change at a time; retain previous state in muted form if comparison matters.

**Evidence:** legacy foundation at [Money laundering 1:50–3:00](https://www.youtube.com/watch?v=0uLhh5GSxsQ&t=110s).

## T10 — Mascot beside evidence

**Purpose:** interpret a chart/document/headline.

**Inputs:** evidence template, pose, pointing target, optional speech bubble.

**Layout:** evidence 58–74% width; mascot 25–38%, placed opposite target. Never cover axes/source/highlight.

**Behaviour:** evidence completes first; mascot enters 180–360 ms later; pose changes without re-entering the entire layout.

**Evidence:** [Oil 6:40–7:00](https://www.youtube.com/watch?v=e-2GoFws3yE&t=400s).

## T11 — Mascot + accumulating tokens

**Purpose:** compress a list of companies, investments, products, or actors.

**Inputs:** mascot, 3–10 logo/image tokens, ordering.

**Layout:** mascot centre/lower third; tokens fill negative space with consistent circles/cards.

**Behaviour:** one token per spoken item; tokens remain; pose changes after a semantic cluster, not every token.

**Evidence:** [Peter Thiel 0:44–1:06](https://www.youtube.com/watch?v=_W3qPymBEBA&t=44s).

## T12 — Full-screen primary footage

**Purpose:** establish reality, person, place, process, or emotional texture.

**Inputs:** clip, in/out points, attribution if necessary.

**Layout:** fill; preserve useful original lower-third when it establishes source; crop only safe areas.

**Behaviour:** hard cut or 140–240 ms dissolve; use 2–7 s excerpts; allow 8–12 s when the clip itself makes the point.

**Evidence:** [Oil 0:50](https://www.youtube.com/watch?v=e-2GoFws3yE&t=50s), [Big Short 0:10](https://www.youtube.com/watch?v=3xC1a5r0zNY&t=10s).

## T13 — Source/footage montage

**Purpose:** establish event scale or historical memory.

**Inputs:** 3–8 clips with coherent subject/era.

**Behaviour:** 1.5–4 s per clip; cut on syntax, action, or musical beat; do not use random stock simply to increase cut count.

**Evidence:** [Big Short 0:00–0:36](https://www.youtube.com/watch?v=3xC1a5r0zNY).

## T14 — Product/company beauty beat

**Purpose:** give a named object/company physical specificity and visual rest.

**Inputs:** product/store/factory clip, optional logo.

**Behaviour:** clean full-screen shot 3–7 s; mild push/pan; follow with evidence or commentary rather than another generic beauty shot.

**Evidence:** [Car market 1:04](https://www.youtube.com/watch?v=mUBBqAjVuco&t=64s).

## T15 — Cut-out system collage

**Purpose:** show many actors or make a mechanism tangible.

**Inputs:** cut-outs, background, labels/props, depth order.

**Layout:** three depth planes; 6–12% object overlap; one dominant focal object.

**Behaviour:** build objects in causal order; small parallax; camera remains stable until composition completes.

**Evidence:** [Big Tech 0:30](https://www.youtube.com/watch?v=swtfbef3HhM&t=30s), [Consumption 0:40](https://www.youtube.com/watch?v=aw7ayuTZxi0&t=40s).

## T16 — Visual punchline

**Purpose:** release tension, sharpen commentary, create recall.

**Inputs:** dry narration cue, mascot/reaction image, literalised metaphor, optional one-line bubble.

**Behaviour:** abrupt 1.5–5 s interruption; minimal setup; exit immediately after comprehension. Do not explain the joke on screen.

**Evidence:** [Car market 1:14](https://www.youtube.com/watch?v=mUBBqAjVuco&t=74s), [McRecession 0:20](https://www.youtube.com/watch?v=Baj7AINpqXA&t=20s).

## T17 — Kinetic question/section thesis

**Purpose:** crystallise the contradiction.

**Inputs:** 5–14 words, optional background footage/mascot silhouette.

**Layout:** centred, 70–84% max width; 2–4 lines; strong line-break logic.

**Behaviour:** phrase reveals by clause or direct cut; 2–6 s; avoid typewriter effects.

**Evidence:** [AI/jobs 0:40](https://www.youtube.com/watch?v=MYB0SVTGRj4&t=40s).

## T18 — Comparison board

**Purpose:** compare two systems, periods, companies, or outcomes.

**Inputs:** left/right labels, metrics, visuals, decisive difference.

**Layout:** 46/46 split with 8% gutter or one shared chart; identical scale.

**Behaviour:** establish baseline, add second case, then highlight difference.

**Evidence:** [Family fortunes 0:30](https://www.youtube.com/watch?v=Qb8tTA8Dmfo&t=30s).

## T19 — Website/social card

**Purpose:** show a public statement, platform behaviour, or cultural artefact.

**Inputs:** screenshot, author/source, date, relevant crop.

**Behaviour:** crop aggressively to relevant content; retain enough UI for authenticity; highlight or zoom instead of rereading the whole page.

**Evidence:** [Silicon Valley 2:30](https://www.youtube.com/watch?v=ShGT-fY7S98&t=150s).

## T20 — Sparse room/stage

**Purpose:** begin a section, stage an interaction, or make an abstract idea theatrical.

**Inputs:** wall/floor, mascot, one prop, optional guest cut-out.

**Behaviour:** mascot enters first or last depending on reveal; objects slide/roll in; 6–16 s.

**Evidence:** [Car market 2:32–2:34](https://www.youtube.com/watch?v=mUBBqAjVuco&t=152s), [McRecession 2:10](https://www.youtube.com/watch?v=Baj7AINpqXA&t=130s).

## T21 — Map/route

**Purpose:** explain geography that changes economics.

**Inputs:** base map, highlighted regions, route/arrows, labels, data/source.

**Layout:** desaturated base, 1–3 active colours, labels outside dense regions.

**Behaviour:** location highlight → route/constraint → consequence. Camera changes only for scale shift.

## T22 — List/checklist

**Purpose:** enumerate a short model or set of conditions.

**Inputs:** 3–5 items, optional background/diagram.

**Behaviour:** one item per spoken clause; previous items remain; no more than seven words/item.

**Evidence:** [EVE 2:20](https://www.youtube.com/watch?v=m6j_UsGJnkQ&t=140s).

## T23 — Legacy logo bumper

This appears around 1:00–1:40 in many 2021–22 videos ([EVE 1:00](https://www.youtube.com/watch?v=m6j_UsGJnkQ&t=60s), [Money laundering 1:00](https://www.youtube.com/watch?v=0uLhh5GSxsQ&t=60s)). It should **not** be recreated for the current Meridian grammar. Current videos cold-open and maintain momentum.

---

# Part VI — shot-level visual sequencing

The tables below use 2-second review sheets and caption timing. Narration is paraphrased to avoid reproducing scripts.

## 13. Sequence A — Big Tech opening, 0:00–1:36

| Time | Narration beat | Visual/template | Mascot | Motion/transition | Purpose |
|---|---|---|---|---|---|
| 0:00–0:02 | Meta announces another layoff | Zuckerberg event footage (T12) | — | Hard cut cold open | Person/reality |
| 0:02–0:14 | 8,000 jobs / 10% workforce | Single Yahoo headline over blurred footage (T01) | — | Paper drop, subtle hold push | Evidence |
| 0:14–0:24 | Earlier layoffs pile up | Headline stack on graph paper (T02) | — | Cards accumulate, prior cards persist | Pattern/scale |
| 0:24–0:30 | “Year of efficiency” and more cuts | More NBC/CNBC cards | — | Two quick additions | Escalation |
| 0:30–0:38 | Morale aside | Morale headline → office-worker composite (T15) | — | Card clears into cut-out gag | Commentary |
| 0:38–0:44 | Total layoffs versus starting headcount | Source/document with yellow emphasis | — | Quick paper replacement | Proof |
| 0:44–0:50 | Other companies are similar/worse | Framed tech-layoff tracker (T04) | — | Chart replaces office scene | Generalise |
| 0:50–1:00 | Industry/AI-spending context | Trader/presenter/news/logo footage montage (T13) | — | 2–4 s hard cuts | Context/rhythm |
| 1:00–1:02 | Spending surge | CNBC chart clip | — | Hard cut | Authority |
| 1:02–1:12 | Oracle layoffs and AI spending | Single headline on green (T01) | — | Card holds ~10 s | Evidence/rest |
| 1:12–1:16 | Apparent explanation | Green presenter scene (T10) | Arms crossed → shrug | Blurred pop-in; pose cut | Interpretation |
| 1:16–1:20 | Automation/jobs imagery | News typing footage | — | Hard cut | Literal illustration |
| 1:20–1:24 | “Good news/inconvenient truth” pivot | Mascot over footage | Open palms | Fast composite | Tone/pivot |
| 1:24–1:26 | Named executive/platform | Phone/social image | — | Hard cut | Specificity |
| 1:26–1:36 | Headcounts recovered | Framed multi-line chart (T04) | — | Page/board settles; lines draw left-to-right; labels hold | Core contradiction |

Why it works: six visual roles rotate in 96 seconds, but only about ten macro templates appear. Internal cards, highlights, and chart lines create pace without replaying entrance animations.

## 14. Sequence B — Peter Thiel opening, 0:00–1:36

| Time | Narration beat | Visual/template | Mascot | Motion/transition | Purpose |
|---|---|---|---|---|---|
| 0:00–0:04 | Establish Thiel as unusual | Two interview/event clips | — | Hard cuts | Person |
| 0:04–0:10 | First recent activities | Cork portrait dossier (T06) | — | Polaroid and event card pin in | Begin evidence pile |
| 0:10–0:18 | Enhanced Games, giving pledge, media essay | Headline/cards/manga accumulate | — | Board persists; objects added | Absurd specificity |
| 0:18–0:20 | Wealth context | Net-worth chart pinned on board | — | Card replacement | Stakes |
| 0:20–0:34 | Public remarks/tour | Interview and lecture footage | — | 3–6 s cuts | Primary evidence |
| 0:34–0:40 | Documented claim | Source page with yellow passage | — | Page/push-in/highlight | Proof |
| 0:40–0:44 | Dry comparison/punchline | Greta footage | — | Abrupt cut | Humour |
| 0:44–0:50 | “All within one year” interpretation | Mascot over completed board | Pointing → clasped | Blurred entry; pose cut | Editorial voice |
| 0:50–0:58 | Time-management/strangeness aside | Same board, new poses | Open palm / explaining | Background remains | Commentary |
| 0:58–1:08 | Companies/investments list | Logo tokens accumulate around mascot (T11) | Explaining | One token per item | Compress list |
| 1:08–1:12 | PayPal/early success | Archival image | — | Hard cut | Historical specificity |
| 1:12–1:20 | Networks/connections | Boardroom footage | — | Hard cut/hold | Power/stakes |
| 1:20–1:36 | Public-profile change | Interviews, headline, factory/event footage | — | 2–6 s montage | Move from “strange” to “why” |

Why it works: the opening is a visual investigation. The mascot does not replace evidence; it appears only after the board has earned an editorial interpretation.

## 15. Sequence C — Car-market passage, 1:00–2:36

| Time | Narration beat | Visual/template | Mascot | Motion/transition | Purpose |
|---|---|---|---|---|---|
| 1:00–1:04 | Luxury-brand headline | Torn clipping | — | Hold | Evidence |
| 1:04–1:08 | Ferrari | Product beauty footage | — | Clean hard cut | Specificity/rest |
| 1:08–1:12 | Share decline | CNBC footage | — | Hard cut | Proof |
| 1:12–1:14 | Commentary on trend | Mascot over news | Pointing | Fast composite | Interpret |
| 1:14–1:20 | Product/punchline | Covered-car stage → reveal | Seated miniature → standing | Prop reveal, pose changes | Humour |
| 1:20–1:24 | Honda loss | News/company footage | — | Hard cuts | Expand evidence |
| 1:24–1:30 | Historical performance | Framed line chart | — | Line draw, hold | Explain |
| 1:30–1:48 | Stellantis/consumer stress | Factory, company, borrower footage | — | 2–5 s montage | Context |
| 1:48–2:00 | Company decisions | Stellantis/Ford/news footage | — | Hard cuts | Mechanism |
| 2:00–2:12 | EV/China comparison | BYD/event/news footage | — | 2–4 s cuts | Counterexample |
| 2:12–2:18 | Channel callback | Mascot + earlier thumbnails/cars | Pointing/explaining | Collage accumulates | Continuity/humour |
| 2:18–2:32 | Historical manufacturing shift | Archival/factory footage | — | Longer 4–6 s shots | Serious reset |
| 2:32–2:36 | New explanatory section | Sparse showroom | Neutral; guest/car added | Blurred mascot entry; objects slide in | Stage mechanism |

Why it works: the miniature-car gag is surrounded by sourced footage and a chart. Humour never becomes the sole information channel.

## 16. Sequence D — Big Short opening, 0:00–1:36

| Time | Narration beat | Visual/template | Mascot | Motion/transition | Purpose |
|---|---|---|---|---|---|
| 0:00–0:10 | 2008 crisis context | Trading, markets, office montage | — | Rapid hard cuts | Historical stakes |
| 0:10–0:20 | Government response | Bush address | — | Longer hold | Authority/time |
| 0:20–0:36 | Predictions and fraud context | Lecture/interview footage | — | 4–8 s holds | Explanation/authority |
| 0:36–0:42 | Housing system | Aerial neighbourhood footage | — | Hard cut | Orient |
| 0:42–1:00 | Film introduces traders | Big Short clips | — | Character-driven montage | Cultural reference |
| 1:00–1:12 | Film’s accuracy | Director/actor interview | — | Interview/film alternation | Credibility |
| 1:12–1:28 | Finance as plot | Film office/trading scenes | — | 2–5 s cuts | Illustration |
| 1:28–1:36 | Contrast with another finance film | Wolf of Wall Street footage | — | Abrupt comparison cut | Punchline/transition |

This older sequence lacks the current desk and mascot, but it demonstrates the same editorial rule: choose clips that make the argument, not generic finance footage.

---

# Part VII — editing rhythm and motion design

## 17. Pacing measurements

### Measured

- Corpus runtime: 4:19:31.
- Narration: 196.7 weighted WPM.
- Conservative hard cuts: 7.7/min across corpus; 8.9/min in the five most current sampled videos.
- Median detected hard-cut interval: 3.37 s.
- Current manual opening samples: 10–16 meaningful visual changes/min.
- Current major template changes: 4–7/min.

### Editorial target

| Event | Target |
|---|---:|
| Full-screen footage shot | 2.5–6 s |
| Headline card | 4–9 s |
| Document scene | 8–16 s |
| Chart scene | 8–15 s |
| Persistent collage/board | 10–30 s |
| New internal reveal | Every 1.5–4 s during a build |
| Mascot appearance | 4–12 s, occasionally 15–20 s |
| Mascot re-entry | Roughly every 40–75 s, topic-dependent |
| Major template transition | Every 9–15 s average |
| Visual punchline | 1–2 per minute |
| Animated text/highlight/label events | 2–5 per minute, usually clustered inside evidence scenes |
| Deliberately static/rest shot | 4–10 s after a dense run |

The target is not a metronomic cut every three seconds. Dense builds alternate with rests. A ten-second headline can follow a rapid montage, as at [Big Tech 1:02](https://www.youtube.com/watch?v=swtfbef3HhM&t=62s).

## 18. Motion vocabulary

### Hard cut

Default between footage, evidence, or a decisive tonal change. It keeps the voice brisk and prevents motion design from becoming the subject.

### Paper drop/slide

For headlines, documents, and photos. Duration 240–420 ms; 10–30 px settle; 2–5° initial rotation; ease-out/back with small overshoot.

### Blur whip

For mascot and large-object entrances. Duration 180–320 ms; directional blur tied to travel direction; opacity reaches 100% by roughly 65% of motion.

### Progressive build

For headline stacks, relationship boards, lists, diagrams, and collages. The scene persists while one new object appears every 0.7–3 s.

### Chart line reveal

Axes/grid exist first; lines draw left-to-right in 2.5–5.5 s; endpoint labels pop 100–250 ms after the series; hold 2–6 s. Demonstrated at [Big Tech 1:26](https://www.youtube.com/watch?v=swtfbef3HhM&t=86s).

### Marker highlight

Yellow line/rectangle grows left-to-right across exact source text in 0.6–1.5 s; if multiple lines, stagger 0.2–0.5 s. Demonstrated at [Silicon Valley 3:12](https://www.youtube.com/watch?v=ShGT-fY7S98&t=192s).

### Ken Burns / push-in

Still images and documents use 2–6% scale over 4–12 s. The move should be almost unconscious.

### Parallax

Desk/corkboard/collage foreground moves 1–3%, middle 0.5–1.5%, background static or 0.25%. Avoid continuous floating.

### Object reveal

Props uncover products, nodes, or consequences. The covered Ferrari/mascot sequence at [Car market 1:14](https://www.youtube.com/watch?v=mUBBqAjVuco&t=74s) is a strong example.

### Deliberate stillness

After a dense build, allow a source card, interview clip, or completed chart to hold. Readability is part of pacing.

## 19. Motion constraints

- Never replay a template’s entrance because the subtitle/sentence changed.
- Never apply the same bounce to every asset.
- No persistent camera shake.
- Motion blur is transitional, not atmospheric.
- Text should not type word-by-word unless the source itself is being typed.
- Avoid auto-panning every still.
- A visual build must have causal or rhetorical order.
- The renderer must preserve object state across all lines belonging to the same beat.

---

# Part VIII — transition system

## 20. Transition library

| ID | Transition | Duration | Easing | Use |
|---|---|---:|---|---|
| TR01 | Editorial hard cut | 0–2 frames | Linear | Default evidence/footage change |
| TR02 | Short dissolve | 140–260 ms | Ease-in-out | Similar archival shots / tonal softness |
| TR03 | Paper drop | 240–420 ms | `cubic-bezier(.16,1,.3,1)` + 4% overshoot | Headline/photo entry |
| TR04 | Paper sweep/replace | 260–480 ms | Ease-out | Document-to-document / desk object change |
| TR05 | Blurred pop-up | 180–320 ms | Back-out | Mascot entry |
| TR06 | Side whip | 180–300 ms | Expo-out | Mascot/object/board lateral change |
| TR07 | Push into evidence | 350–700 ms | Cubic-in-out | Footage/image → document/chart |
| TR08 | Pull back to system | 450–800 ms | Cubic-in-out | Detail/document → board/network |
| TR09 | Prop wipe | 250–550 ms | Physical/ease-out | Page, folder, car cover, hand, object |
| TR10 | Graphic match cut | 0–180 ms | Linear/ease-out | Similar shapes/logos/faces |
| TR11 | Punchline interruption | 0–100 ms | Linear | Meme/reaction/absurd composite |
| TR12 | Section breath | 250–500 ms fade or clean cut | Ease-in-out | Sparse room/title/new chapter |

Most transitions are TR01, TR03, TR04, and TR05. Context-sensitive props create novelty without requiring a large effect library.

## 21. Transition matrix

| From → To | Preferred | Alternate | Avoid |
|---|---|---|---|
| Footage → footage | TR01 | TR02 | Large wipe |
| Footage → headline | TR03 over blurred footage | TR01 | Full-screen spin |
| Headline → headline stack | Persistent scene + TR03 | TR04 | Resetting background |
| Headline → chart | TR01 or TR07 | TR04 | Mascot-first detour |
| Chart → mascot | Mascot TR05 over held chart | TR01 | Rebuilding chart |
| Mascot → document | TR04/TR01 | TR06 | Long crossfade |
| Document → image/footage | TR01 | TR07 reverse | Decorative wipe |
| Image → headline | TR03 | TR01 | Page curl unless physical desk |
| Footage → meme | TR11 | TR01 | Dissolve |
| Meme → serious evidence | TR01 + audio reset | TR12 | Extended gag transition |
| Timeline → map | TR08 then TR07 | TR01 | Simultaneous dense morph |
| Map → chart | TR07 | TR01 | Arbitrary 3D rotation |
| Statistic → reaction mascot | TR05 | TR11 | Slow dissolve |
| Section reset → footage | TR01 | TR02 | Replay of logo bumper |

Sound accompaniment should be restrained: paper impacts for TR03/04, a soft whoosh for TR05/06/07, a click/pin for relationship nodes, and a single comedic impact for TR11.

---

# Part IX — asset treatment

## 22. Image and video sourcing

### Selection hierarchy

1. Primary-source footage/document.
2. Reputable news footage/headline/report.
3. Official company/product/event material.
4. Archival material with real historical specificity.
5. Original chart/diagram derived from a cited source.
6. Stock footage only when it contributes an action, place, or emotional texture unavailable above.
7. Meme/reaction asset only for a deliberate tonal function.

The channel’s strongest sequences pair an argument with recognisable evidence: Thiel interviews and documents, Big Tech layoff headlines and headcount chart, car-company coverage and product/factory footage. The weakest thing a reconstruction could do is replace that with polished but generic “business people in an office” stock.

### Treatment rules

- Preserve source identity when credibility matters.
- Crop aggressively to the relevant subject; do not display unused webpage chrome.
- Use full-frame footage at native aspect where possible; pillarbox only when the source’s vertical format is itself meaningful.
- News lower-thirds may remain if they identify outlet/context; otherwise crop.
- Archival imperfections are acceptable and often valuable.
- Desaturate only to establish period or create a controlled collage; do not impose one LUT on every source.
- Match heterogeneous cut-outs with common shadow, modest grain, and shared background—not by flattening all colours.
- Use 2–5% slow push on still sources.
- For evidence pages, show context first and highlight second.
- For humour, deliberately rough compositing can be more effective than seamless photorealism, but the focal joke must read in under one second.

## 23. Keeping heterogeneous media coherent

The coherence stack should be:

1. shared green/cork visual world;
2. consistent paper/frame material;
3. consistent shadow/depth;
4. consistent transition speed;
5. repeated mascot/logo;
6. recurrent serif/sans typography pair;
7. consistent source-attribution placement;
8. light global grain/vignette only at the final composite.

Do not colour-grade primary news footage so aggressively that it appears fabricated.

---

# Part X — data, maps, documents, and text

## 24. Chart specification

- Use line charts for time series, bars for categorical comparisons, slope/dumbbell for before/after, and stacked bars only when composition is the story.
- Plot background: `#F4F3EE`; frame: warm wood; surrounding field: graph-paper green.
- Axes: `#20251F`, 2 px at 1080p.
- Grid: `#D7D9D4`, 1 px, 35–55% opacity.
- Primary series: `#27824C`, 4–6 px.
- Secondary series: muted blue `#4E7BA6`, ochre `#C68A2B`, red only for loss/risk.
- Labels: 22–28 px; title 30–38 px; source 16–20 px.
- Maximum five visible series; directly label endpoints instead of relying only on a legend.
- Animate series in narrative order, not all at once.
- Use a mascot only after the relevant line/value exists.
- Annotate turning points with one short phrase, not a paragraph.

## 25. Map specification

- Use an original low-detail vector base map.
- Land `#D8D8CF`, water `#C8D6D2`, borders `#6A716A`.
- Active country/region green; risk/conflict red/ochre; inactive regions 35–50% saturation.
- Reveal location, then route/resource/border, then consequence.
- Use 1.5–3 px routes and arrowheads that remain legible at mobile size.
- Avoid flags as fills unless the visual point is national comparison.
- Cite geographic/data source in lower edge.

## 26. Document/headline specification

Document sequence:

1. Show the full page for 0.5–1.5 s.
2. Crop/push to the relevant paragraph.
3. Animate one highlight at a time.
4. Hold the completed highlight for at least 1.5 s.
5. Preserve source/publication/title.

Headline sequence:

1. Source at top.
2. Headline in editorial serif.
3. Date only if chronology matters.
4. Use torn edge and paper shadow.
5. Stack headlines only to prove a pattern.

## 27. Statistics

- Number first, unit second, meaning third.
- Use a comparison object or baseline when the raw number lacks intuitive scale.
- Number height 10–15% of frame.
- Unit 35–55% of number size.
- Hold 3–6 s.
- Avoid odometer counting for a static measured value; reserve count-up for accumulation over time.
- A source appears at 1.5–2% frame height and remains legible.

---

# Part XI — audio and narration

## 28. Voice

The narrator is a male voice with an Australian/Antipodean accent, dry conversational delivery, controlled pitch, and limited theatrical “YouTube voice.” Key properties:

- ~197 WPM;
- short clause pauses, median ~0.35 s;
- emphasis on numbers, names, contrast words, and the final noun of a punchline;
- mild pitch rise on genuine rhetorical questions;
- downward, matter-of-fact delivery on jokes;
- longer pause only before a central contradiction or section-level implication;
- sarcasm is carried by timing and understatement, not exaggerated character acting.

Meridian should use one fixed voice identity. Do not change the speaker or voice profile between renders. Keep pronunciation dictionaries for company/person names.

## 29. Mix measurements and recommendations

Measured representative integrated loudness: -17.6 to -19.4 LUFS; LRA 3.4–6.7 LU; peaks varied from +0.18 to -2.87 dBTP in source review copies.

Recommended delivery master:

- Integrated: -16 to -14 LUFS depending platform strategy.
- True peak: ≤ -1.0 dBTP.
- Voice high-pass: 70–90 Hz.
- Gentle cut: 180–300 Hz if muddy.
- Presence: +1–3 dB around 2.5–4.5 kHz if required.
- De-esser: 5–8 kHz, 2–5 dB reduction.
- Compression: 2.5:1–4:1, 3–6 dB gain reduction, 10–30 ms attack, 60–140 ms release.
- Music under narration: typically 18–26 dB below voice; reduce another 2–4 dB during dense evidence.
- Use automation rather than one static music level.

## 30. Music and effects

- Underscore: restrained documentary/electronic/quirky percussion; low harmonic density.
- Change cue at section transitions, not every template.
- Serious evidence: reduce percussion and novelty effects.
- Humour: one short sting, muted thump, click, or record-like interruption; never a barrage.
- Paper/card: soft paper hit and air movement.
- Pushpin/string: click/tack.
- Chart line: nearly inaudible pencil/electronic tick; endpoint label may receive one soft click.
- Mascot entry: 150–300 ms whoosh/pop.
- News montage: preserve short source audio only when intelligible and legally usable; duck narration/music intentionally.
- Use room tone under very sparse scenes so cuts do not feel digitally empty.

---

# Part XII — complete production grammar

## 31. Script-to-visual decision tree

```text
START BEAT
│
├─ Is this a sourced factual claim?
│  ├─ One claim → headline or document
│  ├─ Repeated pattern → accumulating headline stack
│  ├─ Trend/comparison → chart
│  └─ Event/person captured on video → primary/news footage
│
├─ Is this explaining a mechanism?
│  ├─ Actors transact → diagram
│  ├─ Events cause later events → timeline
│  ├─ Geography constrains outcome → map
│  ├─ Many people/institutions interact → relationship board
│  └─ Two cases differ → comparison board
│
├─ Is this introducing an entity?
│  ├─ Person → portrait dossier + primary footage
│  ├─ Company/product → official/product footage + logo
│  └─ Place/period → establishing/archival footage
│
├─ Is this editorial interpretation?
│  ├─ Caveat/uncertainty → thinking mascot
│  ├─ Contradiction → arms-crossed → shrug
│  ├─ Key point → pointing/index pose
│  └─ Bridge/new section → neutral explainer/stage
│
├─ Is this a joke or ironic aside?
│  ├─ Literal metaphor available → visual punchline composite
│  ├─ Character reaction works → mascot reaction
│  └─ Cultural shorthand works → brief meme/reaction
│
└─ Has the sequence become visually monotonous?
   ├─ 2+ static cards → use footage
   ├─ 20+ seconds footage → use evidence/diagram
   ├─ 60+ seconds without editorial voice → consider mascot
   └─ dense 15+ second build → insert 4–8 second rest
```

## 32. Global sequencing constraints

1. Segment script into idea beats, not sentences.
2. Assign each beat one primary visual role and an optional secondary role.
3. Preserve a scene until the role, subject, time, location, or mechanism changes.
4. Allow 2–8 internal events inside one scene.
5. Do not use the same macro template three times in a row.
6. Do not use generic stock for a claim that has available primary evidence.
7. After two evidence-heavy beats, include explanation, context, commentary, or rest.
8. After a joke, return to evidence within 2–8 seconds.
9. A chart must be motivated by narration and remain until the listener understands the relevant comparison.
10. A mascot entrance must have an editorial action: point, question, judge, bridge, or joke.
11. Keep the opening denser than the median body section.
12. Reduce visual density before the conclusion.

## 33. Beat schema

```json
{
  "beat_id": "b012",
  "start_sec": 86.0,
  "end_sec": 98.0,
  "narrative_function": "reveal_contradiction",
  "visual_role": "explain_and_prove",
  "claim": "Headcount has recovered despite repeated layoffs",
  "entities": ["Meta", "Amazon", "Google"],
  "source_ids": ["src_headcount_dataset"],
  "tone": "dry_surprise",
  "scene_id": "headcount_chart",
  "template": "framed_line_chart",
  "internal_events": [
    {"at": 0.0, "action": "show_axes"},
    {"at": 0.7, "action": "draw_series", "target": "Meta"},
    {"at": 1.8, "action": "draw_series", "target": "Amazon"},
    {"at": 2.9, "action": "draw_series", "target": "Google"},
    {"at": 5.2, "action": "show_endpoint_labels"}
  ],
  "mascot": null,
  "transition_in": "paper_sweep",
  "transition_out": "hard_cut",
  "audio_cue": "subtle_chart_ticks"
}
```

### Trigger-routing table

| Narration trigger | Primary route | Secondary route |
|---|---|---|
| Company first mentioned | Product/store/factory or primary company footage | Logo/portrait dossier |
| Person first mentioned | Primary footage or labelled portrait | Relationship board |
| Country/place | Establishing footage | Map only if geography affects mechanism |
| Statistic | Large statistic if one value matters | Chart if change/comparison matters |
| Money/cost/debt | Transaction diagram, product/receipt, or chart | Literal money image only for a joke |
| Date/year | Archival footage or timeline node | Kinetic date only at a major historical turn |
| Historical event | Archival footage/photo | Timeline when sequence matters |
| Document/source | Full-page context → crop → highlight | Torn headline for one public claim |
| Abstract mechanism | Diagram, staged metaphor, or comparison | Mascot explains beside it |
| Joke/sarcasm | Visual punchline or reaction mascot | Abrupt meme/reaction |
| Doubt/uncertainty | Thinking/sceptical mascot | Competing evidence cards |
| Contradiction | Comparison/chart or evidence juxtaposition | Arms-crossed → shrug |
| Serious turn | Remove joke props, reduce music and density | Longer primary footage/document hold |
| New section | Resolve prior question, sparse reset or new visual world | Short kinetic thesis |
| Conclusion | Return to opening motif/board/chart | Low-density mascot or footage; no new visual system |

The critical `scene_id` allows several sentences/caption segments to share one persistent composition.

---

# Part XIII — production workflow and automation architecture

## 34. Full workflow

1. **Editorial thesis:** writer states the central contradiction and durable mechanism.
2. **Research pack:** gather primary documents, reputable reports, current footage, historical material, and data.
3. **Script:** write narration without template chatter.
4. **Claim/source pass:** bind factual claims to source IDs and exact excerpts.
5. **Beat segmentation:** divide narration into 5–25 second idea beats.
6. **Visual-role pass:** choose prove/explain/orient/illustrate/comment/reset.
7. **Global art-direction pass:** select visual world(s), density curve, recurring metaphors, narrator frequency, and section rhythm.
8. **Storyboard:** select templates and internal events with timestamps.
9. **Asset acquisition:** resolve footage, screenshots, documents, charts, cut-outs, and rights.
10. **Narrator direction:** choose pose/clip/placement only where editorially motivated.
11. **Animation:** render persistent scenes and internal reveals.
12. **Voice/music/SFX:** fixed narrator voice, section-level music plan, sparse effects.
13. **Editorial review:** verify claim/visual agreement, joke tone, readability, repetition, and rights.
14. **Render QA:** inspect mobile legibility, safe margins, scene continuity, audio loudness, dropped/duplicated frames.

## 35. Automated architecture

```text
Research Pack + Script
        │
        ▼
Claim/Source Binder
        │
        ▼
Semantic Beat Segmenter
        │
        ▼
Global Story & Art Director
        │
        ├── density curve
        ├── visual motifs
        ├── narrator budget
        └── section worlds
        ▼
Beat Visual Planner
        │
        ├── visual role
        ├── template
        ├── internal events
        ├── pose/placement
        └── transition
        ▼
Asset Resolver + Rights Metadata
        │
        ├── primary footage
        ├── documents/headlines
        ├── charts/maps
        └── cut-outs/props
        ▼
Continuity-Aware Scene Renderer
        │
        ├── persistent scene state
        ├── layered motion
        └── audio cues
        ▼
Editorial/Technical QA
```

### Required modules

- `StoryDirector`: reasons over the entire script; prevents locally plausible but globally repetitive choices.
- `BeatSegmenter`: groups captions/sentences into persistent idea beats.
- `EvidenceResolver`: maps claim IDs to real documents/headlines/footage.
- `TemplateSelector`: chooses from T01–T22 using visual role and recent-history penalties.
- `NarratorDirector`: pose, gaze, scale, position, and appearance budget.
- `ChartDirector`: converts cited structured data into chart instructions.
- `TransitionDirector`: uses transition matrix, not random effects.
- `SceneState`: keeps background/assets alive across internal events.
- `TasteQA`: flags repeated templates, excessive mascot, generic stock, illegible evidence, unjustified charts, and jokes during sensitive material.

### Human judgement that should remain

- selecting the central contradiction;
- deciding whether a source is genuinely strong;
- deciding when humour is appropriate;
- choosing the best archival/primary clip;
- editing a joke so it does not overstay;
- final chart annotation and framing;
- rights/fair-use decisions;
- approving the complete story rhythm.

---

# Part XIV — required original assets

## 36. Smallest convincing library

### Visual worlds

1. Green graph-paper desk with 3 lighting variants.
2. Cork investigation board with wood frame.
3. Sparse neutral room/stage.
4. Dark projection room.
5. Paper/document prop pack.

### Templates

The minimum high-impact set is T01–T17 plus T20. Maps and specialist diagrams can follow. A convincing first release needs:

- headline single/stack;
- document highlight;
- framed chart;
- statistic;
- portrait dossier;
- relationship board;
- timeline;
- mechanism diagram;
- mascot beside evidence;
- token list;
- footage;
- montage;
- company/product;
- collage;
- punchline;
- kinetic thesis;
- comparison;
- sparse stage.

### Narrator

At minimum: 12 core poses/clips—neutral, explaining, arms crossed, low shrug, high shrug, four pointing directions, index-up, thinking, facepalm—plus miniature/seated variant, consistent tracked head, and three entry/exit families.

### Props

Torn paper, Polaroids, pushpins, string, folders, pencil, marker highlight, wood chart frame, speech/thought bubbles, pointer, chair, projector, reveal cover, laptop, document frame, logo/token holders.

## 37. Assets requiring manual creation

- Original Meridian mascot/logo-head and all body clips.
- Original green/cork textures and physical props.
- Torn-paper masks and paper-shadow system.
- Wood chart frame.
- Original sound-effect pack.
- Original music or licensed library.
- Original chart/map visual language.
- Original title/end treatment.
- Rights-cleared or licensed footage library.
- A pose/prop tracking dataset for narrator placement.

---

# Part XV — reconstruction accuracy and rights

## 38. What can be reproduced closely

- beat-level pacing;
- evidence/explanation/commentary rotation;
- green paper/cork material logic;
- headline/document/chart grammar;
- chart-line and highlight reveals;
- narrator timing, scale, placement, and pose logic;
- short transition vocabulary;
- dry contradiction-led script structure;
- density/rest pattern;
- source-forward editorial framing.

## 39. What must be approximated

- exact private fonts;
- original After Effects/project-file timing curves;
- original mascot actor/body footage;
- exact music and SFX stems;
- proprietary desk/cork textures;
- unlisted source/licensing decisions;
- fine colour/kerning from 360p review copies.

## 40. Public/commercial-use warning

Do not copy:

- the `$?` logo;
- How Money Works name/wordmark;
- the exact logo-headed character art/body library;
- exact thumbnails;
- channel-specific music/SFX;
- proprietary template source files;
- third-party news/film/archival footage without an appropriate licence or defensible use;
- source articles beyond what is legally appropriate.

For Meridian, reproduce the **editorial grammar**, not the trade dress. Use an original symbol, original narrator silhouette/costume language, a differentiated green/neutral palette, original textures, and licensed/original assets.

## 41. Reconstruction-accuracy checklist

### Story

- [ ] Opens with a concrete anomaly within 8 seconds.
- [ ] Central contradiction appears by 90 seconds.
- [ ] First causal mechanism begins by 120 seconds.
- [ ] Each section makes, proves, and interprets a claim.
- [ ] Conclusion returns to the opening question.

### Visuals

- [ ] Every beat has a declared visual role.
- [ ] No template resets merely because a sentence changed.
- [ ] Real evidence is preferred over generic stock.
- [ ] Source pages show context before highlight.
- [ ] Charts remain long enough to understand.
- [ ] No three consecutive beats use the same template.
- [ ] A dense run is followed by visual rest.

### Narrator

- [ ] Every entrance performs an editorial action.
- [ ] Pose direction matches nearby content.
- [ ] Mascot never covers data/source text.
- [ ] Appearances are clustered by idea, not sentence.
- [ ] No lip sync.
- [ ] One fixed voice identity across the video/channel.

### Motion

- [ ] Entry animations occur once per scene.
- [ ] Internal events mutate persistent scene state.
- [ ] Effects match object material.
- [ ] Hard cuts remain the default.
- [ ] Highlights, chart lines, and labels appear in narrative order.

### Audio

- [ ] Voice is intelligible and stable.
- [ ] Music automation follows sections.
- [ ] Effects are sparse.
- [ ] True peak ≤ -1 dBTP.
- [ ] Mobile-speaker check passes.

### Rights and QA

- [ ] All assets have source/licence metadata.
- [ ] Quotes/data match cited sources.
- [ ] Text is legible at 375 px preview width.
- [ ] No safe-area collisions.
- [ ] No repeated or dropped entrance frames.
- [ ] Humour is appropriate to subject.

---

# Part XVI — proposed 60–90 second prototype

## 42. Prototype: “The open-source AI paradox” — 78 seconds

Purpose: test the entire grammar without building a full video.

### Story

Open with the contradiction that leading closed-model labs publicly describe open models as unsafe while depending on open research, open tooling, and rapidly commoditising infrastructure. The prototype should not claim that the companies are literally “scared” without evidence; it should frame what incentives make open models strategically uncomfortable.

### Beat plan

| Time | Narration function | Visual |
|---|---|---|
| 0:00–0:06 | Concrete anomaly | Two primary-source headline clippings on blurred lab/company footage |
| 0:06–0:16 | Evidence pile | Green desk; 3–4 open-model release cards accumulate |
| 0:16–0:22 | Dry contradiction | Mascot arms-crossed, then shrug; one short speech-bubble visual joke |
| 0:22–0:34 | Define market change | Framed chart: closed/open benchmark gap narrows; lines reveal |
| 0:34–0:43 | Explain mechanism | Simple three-node diagram: research → weights/tooling → lower switching cost |
| 0:43–0:52 | Counterargument | Primary source document/page; highlight real safety/cost limitation |
| 0:52–1:03 | Strategic implication | Company-logo tokens accumulate around pointing mascot; tokens change position as moat shifts |
| 1:03–1:12 | Historical/context reset | Brief archival/current datacentre and developer footage montage |
| 1:12–1:18 | Thesis | Sparse green scene with one kinetic line: “The threat is not better AI. It is interchangeable AI.” |

### Required test assets

- 4 real, licensed/allowable headline/document screenshots;
- one sourced benchmark dataset;
- one original mechanism diagram;
- 3–5 short licensed footage clips;
- four narrator clips: arms-crossed, shrug, pointing, neutral;
- one visual punchline;
- one chart;
- paper/marker/whoosh/pin SFX;
- restrained 78-second music edit.

### Pass criteria

- No template intro repeats within a beat.
- Narrator is large enough to read but appears for less than 25% of runtime.
- At least one visual proves, one explains, one orients, and one comments.
- Chart is comprehensible without pausing.
- The joke resolves within four seconds.
- Narration remains one fixed voice at ~195 WPM.
- The result feels like an authored financial editorial, not a news broadcast or slideshow.

---

# Final reconstruction assessment

The highest-impact details are:

1. contradiction-led writing backed by real evidence;
2. visual-role rotation instead of literal sentence illustration;
3. persistent beat-level scenes with internal reveals;
4. tactile green/cork editorial worlds;
5. a pose-driven symbolic narrator used selectively;
6. progressive charts/documents that let the viewer discover the claim;
7. short hard transitions and carefully timed rests;
8. dry visual humour that never replaces the argument.

If Meridian implements only colours, a suit PNG, and stock footage, it will feel like a generic explainer. If it implements the beat grammar, evidence discipline, persistent scene state, narrator direction, and density curve—even with an original visual identity—it can achieve the same level of editorial coherence without copying proprietary assets.
