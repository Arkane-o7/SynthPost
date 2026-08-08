# Unattended production

SynthPost can use Hermes Agent as an overnight research and editorial employee
while SynthPost remains the production control plane. The result is a local,
versioned MP4 waiting for human review—not a published video.

## Operating contract

| Owner | Responsibilities |
|---|---|
| Hermes | Research-aware structured writing and visual-search recommendations through read-only web tools |
| SynthPost | SQLite state, stage scheduling, deterministic validation and approvals, rights policy, narration, media acquisition, timeline, rendering, assembly, QA, and recovery |
| Editor | Watch the full MP4, accept or reject it, and upload to YouTube manually outside the autonomous run |

There is deliberately no YouTube upload action in the autonomy API or Review
Queue. The run policy hard-codes `upload_enabled=false`, and the Hermes child
environment does not receive application or upload credentials.

## Before the night shift

1. Confirm Hermes is installed and authenticated:

   ```bash
   command -v hermes
   hermes status --all
   ```

2. Confirm narration, Avatar Engine, Remotion, FFmpeg, source search, and local
   storage with `make doctor`.
3. Start the complete stack with `make dev`. For unattended work where macOS
   might idle-sleep, use `caffeinate -i make dev`.
4. Keep that terminal and the worker supervisor running. Locking the screen is
   fine; system sleep suspends all workers. Do not close the laptop lid unless
   the Mac is in a powered external-display setup that remains awake.

The default Hermes configuration is:

```dotenv
SYNTHPOST_HERMES_BINARY=hermes
SYNTHPOST_HERMES_MODEL=
SYNTHPOST_HERMES_TOOLSETS=web
SYNTHPOST_HERMES_TIMEOUT_SECONDS=900
```

SynthPost requires the exact `SYNTHPOST_HERMES_TOOLSETS=web` setting for
unattended generation. Aliases, composites, plugins, `all`, and every local or
mutating toolset are rejected. Each call also ignores Hermes behavioral config,
rules, memory, skills, hooks, plugins, and MCP servers while retaining its saved
provider authentication. Set `SYNTHPOST_HERMES_MODEL` when you want an explicit
model instead of Hermes's isolated provider auto-resolution.

## Starting a run

Open an episode in Studio and choose **YOLO Produce**.

Hermes chooses the episode runtime after reading the completed research. The
adaptive window is 3–15 minutes in 30-second increments. It must explain the
choice, then write enough grounded narration to match it; SynthPost still
enforces the normal ±20% duration gate. Thin or repetitive research should
produce a shorter episode, while a dense, well-supported story can run longer.
Manual script generation remains fixed to the duration selected in Studio.

- With a selected story, the run starts from that story and reuses only current,
  valid artifacts.
- With an empty episode, discovery runs first and SynthPost selects the highest
  eligible editorial candidate.
- The initial release allows one story per autonomous episode. This prevents an
  unrelated story from silently blocking final assembly.
- Only one active or unreviewed autonomy run may own an episode at a time.

The stage path is discovery when needed, research, script, narration and visual
search, timeline, composition render, episode assembly, and final-video QA.
Narration and visual search may run in parallel; every other handoff is durable
and can resume from SQLite after the app or worker restarts.

## Automatic gates

- SynthPost—not Hermes—validates and approves generated scripts and timelines.
- Unattended media is green-tier, already-approved, free of review flags, and
  free of approval blockers. Yellow/red or unresolved assets remain visible in
  Studio but are excluded; presenter fallbacks keep the render safe.
- Transient provider, network, and renderer failures receive bounded retries.
  Deterministic validation failures stop at `needs_attention` rather than
  looping or weakening policy.
- The final MP4 must contain valid audio and video streams, survive a full
  FFmpeg decode, match the selected dimensions and frame rate, stay within the
  A/V duration tolerance, and pass loudness and true-peak limits. Sustained
  silence and black frames are reported as warnings for the human review.

## Morning review

The Review Queue shows active runs, failures, and videos ready for review. Each
successful run writes:

```text
episodes/<episode_id>/autonomy_runs/<run_id>/final.mp4
episodes/<episode_id>/autonomy_runs/<run_id>/final.qa.json
```

Watch the MP4 end-to-end. **Accept MP4** records the decision and removes it
from the open queue; it does not upload anything. **Reject & edit** records the
rejection and opens the normal Studio workflow. **Finder** reveals the exact
versioned file.

## Recovery and intervention

- A worker crash leaves the run and jobs in SQLite. On restart, stale leases are
  recovered and the autonomy reconciler continues from the last completed
  checkpoint.
- `Retry checkpoint` retries the failed stage without discarding earlier
  artifacts.
- `Stop shift` cancels queued work immediately. A running handler keeps a
  `cancel_requested` execution lease until it exits, then SynthPost restores
  the closest editable checkpoint and unlocks manual takeover. This prevents a
  second run or editor from racing code that is still unwinding.
- A failed QA report is preserved beside the MP4 so the reason remains
  inspectable. SynthPost never marks a failed file ready for review.
