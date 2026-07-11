# Alpha Test Journey

## Topic Chosen

- Source: Google AI Blog
- Topic: `Expanding Managed Agents in Gemini API: background tasks, remote MCP and more`
- Article date: `July 7, 2026`
- Article URL: `https://blog.google/innovation-and-ai/technology/developers-tools/expanding-managed-agents-gemini-api`

## What I Observed

I used the seeded AI source list in the repo and picked the top-ranked Google AI Blog candidate from the `artificial_intelligence` category.

The live article confirmed the core story:

- background execution for async interactions
- remote MCP server integration
- custom function calling
- credential refresh across interactions

The browser surface for `127.0.0.1:5173` was unavailable in this session, so local UI verification was blocked by the browser URL policy. I still used the browser tooling to verify the surface behavior and then completed the production path through the repo pipeline.

## Production Steps

1. Seeded sources and ran discovery for the AI category.
2. Selected the top Google AI Blog candidate.
3. Created a new project and episode.
4. Built a research pack from the live article text.
5. Wrote a grounded 5-paragraph manual script.
6. Staged a local visual asset from the retained renderer assets.
7. Generated five section-specific visual cards from the script and approved them.
8. Rebuilt and approved the timeline so each section had a proper visual match.
9. Ran Avatar-Engine to render a real anchor clip with TTS narration and lipsync.
10. Built the renderer manifest again against the approved timeline and visuals.
11. Rendered the story and assembled the episode output.

## Notable Notes

- The pipeline emitted a `PydanticSerializationUnexpectedValue` warning while serializing the research pack status, but the run completed and the final render succeeded.
- The corrected render now includes an actual anchor clip, narration audio, and generated editorial visuals.
- The final episode output is a 720p H.264/AAC MP4, not a 4K render.

## Output Paths

- Final episode: `/Users/abhilaksh/Projects/SynthPost/episodes/ep_5851880d22cc/final.mp4`
- Story composite: `/Users/abhilaksh/Projects/SynthPost/episodes/ep_5851880d22cc/stories/story_b544fe5043c5/composited.mp4`
- Story manifest: `/Users/abhilaksh/Projects/SynthPost/episodes/ep_5851880d22cc/stories/story_b544fe5043c5/story.json`
