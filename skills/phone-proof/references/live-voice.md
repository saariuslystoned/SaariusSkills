# Live voice-to-voice proof with a nearby phone

Use this when the behavior under test is a spoken conversation between a person
and a realtime voice agent running in a phone app (barge-in, a consult while the
caller keeps talking, a long spoken reply, session survival). Pixels alone cannot
prove these; the proof is the timeline of spoken input against the agent's event
stream, backed by screenshots at the checkpoints.

## Rig

- **Speaker as the caller.** Put the phone next to the workstation speaker and
  speak test phrases with the OS text-to-speech (`say -v <voice> -r 160 "<phrase>"`
  on macOS). The phone's own microphone and echo cancellation stay in the loop,
  unlike injected audio.
- **Start slow and loud enough.** Roughly 160 words per minute at ~85% output volume
  was reliable. Faster speech or lower volume produced plausible but wrong
  transcriptions ("gateway" heard as "coke machine"). Check the transcript of the
  first phrase before trusting any run.
- **Log every utterance.** Wrap the speech command so it appends `say_start` and
  `say_end` records with millisecond UTC timestamps to the run's `events.jsonl`.
  Every latency claim ("reply stopped 2.4 s after the caller spoke") comes from
  these timestamps, not from memory.
- **Isolated backend.** When the app talks to a server you can build (a gateway or
  relay), run a private instance with its own config, state dir, and port.
  Reach it from the phone through `adb reverse tcp:<port> tcp:<port>` as an added
  endpoint, keep the user's existing entries, and put secrets in the process
  environment (config env substitution), never in the proof tree.
- **One app build, many server variants.** If the changes under test are
  server-side only, install one app build from a known commit and switch server
  variants underneath it. Record the APK digest once.

## Drive by events, not sleeps

- Point the server's structured log at a file inside the run dir and poll it for
  the event the next utterance depends on (tool call started, first reply audio,
  consult run finished) before speaking. Fixed sleeps land the second phrase
  before or after the window you meant to hit.
- Keep a compact per-run trace extracted from that log (event type, timestamps,
  errors), plus the durable conversation record from the app's or server's store
  (role, provenance, sequence, time). Ordering claims need the durable record;
  the server log usually carries event metadata only.
- Summarize each run into a table row (consult runs started or aborted, errors,
  cancellations, session closes, last spoken reply) so a matrix can be built
  from files, not recollection.

## Controls that keep runs honest

- **Vary the question between runs.** Repeating the same request back-to-back lets
  the agent answer from context or treat it as a progress check, so the path under
  test never runs.
- **Quiet room.** A cough or a nearby person talking changes the transcript. Ask
  for quiet during scripted runs. Mark contaminated runs `void_run` in
  `events.jsonl` with the reason and keep their traces; never delete them.
- **Human ear notes are observations.** When a person listening in the room
  reports what they heard, record it as `human_observation` next to the run.
  It supports the trace; it does not replace it.
- **Separate the voice model from the chat model.** Apps often show the text or
  agent model in their picker while the realtime voice model is configured
  elsewhere. Prove which realtime model ran (the loaded config per run, plus a
  model-specific behavior visible in the trace) before a person asks.

## Session hygiene

- Restarting the server drops the phone's session. Starting a voice session
  before the app reconnects can fail silently (the control stays idle). Retry
  until the accessibility tree shows the session is active (for example the
  button reads "End Talk"), and check that state before every run.
- Foldables can switch the active display mid-run when someone opens the phone.
  If a capture comes back black or tiny, re-run inventory before debugging the app.
- Pairing flows that require a setup code: generate it into a shell variable and
  type it with `adb shell input text "$CODE"`. Never write it to a file or print it.

## Restore

Record the original endpoint list and the active endpoint (capture plus tree
dump) before adding anything. At the end: switch back to the original active
endpoint, forget the added one, remove only the `adb reverse` rules you added,
stop the private server, and move its state dir (it holds pairing credentials)
out of the proof tree. Capture the restored list as the closing image.
