# GUI Alpha Managed Agents Episode

## What I Chose

- Project: `GUI Alpha Agents Briefing`
- Episode: `GUI Alpha Managed Agents Episode`
- Story: `Q&A: What is agentic AI today, and what do we want it to be?`
- Source: MIT News AI
- Category: `artificial_intelligence`

## End-to-End GUI Journey

I ran the episode entirely through the SynthPost Studio web app UI.

1. Created a fresh project from the welcome screen.
2. Created a new episode under that project.
3. Opened Story Inbox and selected a different AI story from the seeded list.
4. Started the research job in the GUI.
5. Opened the research panel and observed the extracted pack.
6. Noted a real fetch warning: the article fetch timed out, so research produced only one claim and one document summary.
7. Opened the script editor, wrote a grounded manual script, saved it, and approved it.
8. Staged a local visual asset from the repo via the GUI.
9. Manually approved both visual cards.
10. Generated and approved the timeline.
11. Built the preview render and waited for the test render to complete.
12. Opened the assembly panel and assembled the test episode.

## Observed Errors And Warnings

- Research warning: `article fetch failed: <urlopen error timed out>`
- UI blocker banners repeatedly showed `No timeline found for this story` even after the timeline existed. This appears to be stale UI state, because the timeline approved and render/assembly completed successfully.
- The render/assembly path completed in `TEST_MODE`, producing the test output rather than a production master.
- Follow-up correction: the first assembled video did not include the 3D anchor because the GUI test render path intentionally skips avatar rendering. I then ran `Render Avatar (production)`, verified `anchor.mp4`, ran `Render Story (production)`, and assembled production again.

## Outputs

- Final production episode with 3D anchor: `/Users/abhilaksh/Projects/SynthPost/episodes/ep_2d9ff247cc07/final.mp4`
- Final test episode without production avatar: `/Users/abhilaksh/Projects/SynthPost/episodes/ep_2d9ff247cc07/final_TEST_MODE.mp4`
- Production story composite with 3D anchor: `/Users/abhilaksh/Projects/SynthPost/episodes/ep_2d9ff247cc07/stories/story_2445449079ae/composited.mp4`
- 3D anchor source: `/Users/abhilaksh/Projects/SynthPost/episodes/ep_2d9ff247cc07/stories/story_2445449079ae/anchor.mp4`
- Story manifest: `/Users/abhilaksh/Projects/SynthPost/episodes/ep_2d9ff247cc07/stories/story_2445449079ae/story.json`

## Verification

- `final.mp4` is `1920x1080` H.264/AAC.
- Duration: `81.375s`
- `anchor.mp4` exists and is `1920x1080` H.264/AAC, duration `71.25s`.
- A sampled frame from `final.mp4` at 5 seconds shows the 3D anchor visible on the left side of the composition.
