# SynthPost narration benchmark

Date: 2026-07-12

Purpose: derive original, reusable narration rules for SynthPost from a sample of
presenter-led Indian international-news explainers and India-focused technology
explainers. The goal is not to imitate an individual presenter or reproduce
phrasing. It is to identify structural traits that suit SynthPost's editorial
promise.

## Sample

Firstpost, eight captioned Vantage explainers:

1. [From Scarcity to Superpower: Story of India's Economic Rise](https://www.youtube.com/watch?v=rFlcD-E2vIs)
2. [India Hosts AI Impact Summit as Global Tech Leaders Gather](https://www.youtube.com/watch?v=AD7hlyQDWJM)
3. [How India Became A Tech Power in 78 Years](https://www.youtube.com/watch?v=gN0zFWOH_4g)
4. [How Budget 2026 Signals India's Bid for Strategic Autonomy](https://www.youtube.com/watch?v=9eIVfqDToCI)
5. [5 Things You Should Never Ask ChatGPT](https://www.youtube.com/watch?v=R7oChg73Ov4)
6. [Why Has India Joined the US-led Pax Silica Alliance?](https://www.youtube.com/watch?v=p4c8Lt4IU-U)
7. [India's New Nuclear Reactor Attains Criticality](https://www.youtube.com/watch?v=kbStU-FdqjA)
8. [Anthropic's New Claude Tools Spark Rout in IT Stocks](https://www.youtube.com/watch?v=CjyvBCiEFOs)

AIM Network, eight captioned explainers:

1. [India Launches First AI Governance Guidelines](https://www.youtube.com/watch?v=XcvwUNSCyvU)
2. [Microsoft's India AI Investment Explained](https://www.youtube.com/watch?v=F6tEwoddsy8)
3. [India and Japan's First AI Alliance](https://www.youtube.com/watch?v=dzLsVms4UW0)
4. [India's AI Hiring Surge Explained](https://www.youtube.com/watch?v=sHazRpApA7c)
5. [India at the Center of the AI War](https://www.youtube.com/watch?v=u94ln7zsN0o)
6. [India's AI Talent Shortage](https://www.youtube.com/watch?v=UvTQjwOdVqA)
7. [Indian Army Deploys Vidyut AI](https://www.youtube.com/watch?v=mSqkOHstGls)
8. [Indian Army Deploys Sarvam and CoRover.ai](https://www.youtube.com/watch?v=qg2bjXkxpCY)

Metrics are approximate because they were calculated from automatic caption
tracks. Caption segmentation can merge or split spoken sentences.

| Signal | Firstpost sample | AIM sample |
|---|---:|---:|
| Approximate average sentence length | 10.0 words | 14.3 words |
| Rhetorical questions per video | 4.6 | 5.6 |
| Second-person words per 1,000 | 11.3 | 7.3 |
| First-person plural words per 1,000 | 9.9 | 8.8 |
| Numeric tokens per 1,000 | 23.1 | 15.7 |

## Firstpost structural traits

- Opens rapidly with a concrete fact, scene, contrast or direct invitation.
- Uses short sentences and fragments to create broadcast rhythm.
- Places one emphatic sentence after a dense factual passage.
- Uses spoken pivots such as “but”, “now” and “so” to move the argument.
- Introduces numbers frequently, then turns them into scale or consequence.
- Uses rhetorical questions to announce the explanatory task.
- Places India inside a larger geopolitical or economic system.
- Maintains presenter authority through clear conclusions and direct transitions.

Risks SynthPost should not inherit: excessive certainty, manufactured conflict,
national triumphalism, repeated rhetorical questions and urgency unsupported by
the evidence.

## AIM structural traits

- Starts with the newest institutional, commercial or technical development.
- Carries more entities, figures and technical vocabulary per sentence.
- Explains an announcement through infrastructure, talent, capital and policy.
- Frequently converts a product or investment story into an India capability
  story.
- Uses contrast between headline ambition and implementation reality.
- Is comfortable describing stacks, systems and institutional architecture.
- Uses a conversational presenter voice while retaining trade-publication depth.

Risks SynthPost should not inherit: vendor framing, press-release dependence,
unexplained jargon, promotional calls to action and claims of national capability
that are not tested against execution evidence.

## SynthPost synthesis

SynthPost combines Firstpost's spoken clarity and pacing with AIM's technical and
institutional depth, under a broader technology-society editorial lens.

1. Open within 60 words on a concrete development, scene or contradiction.
2. Prefer 9–15-word spoken sentences in normal explainers.
3. Permit longer sentences only to connect causes, institutions or systems.
4. Pair every material number with scale, comparison or human consequence.
5. Define technical terms on first use without pausing for a textbook aside.
6. Use no more than one rhetorical question per major section.
7. Put India in the global system while avoiding boosterism.
8. Make the evidence-to-interpretation transition explicit.
9. State execution gaps, counter-evidence and unknowns in the present tense.
10. End each section by advancing to the next question rather than summarizing.

## Format-specific application

- **Signal:** short, decisive, development-first delivery.
- **Explained:** conversational systems explanation with alternating evidence and meaning.
- **Deep Dive:** thesis-led investigation, counter-evidence and scenarios.
- **India Builds:** documentary explanation of physical systems, institutions,
  money, capacity and execution over a 30–120 minute chaptered structure.

The executable version of these rules lives in
`editorial/charters/synthpost.v1.json` and is injected into script, long-form,
headline and visual-planning prompts.
