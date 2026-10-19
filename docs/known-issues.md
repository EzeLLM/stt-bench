# Known issues and remaining work

## External validation gates

- No macOS/Xcode/Swift compiler, Apple Silicon, Neural Engine or physical iPhone in this Linux environment. Native source has **not been compiled or executed**. Its package graph, signing, SDK APIs, offline tokenizer loading, memory pressure, cancellation behavior and UI all require the Mac/device checklist.
- No owner speech was supplied. No model accuracy conclusions, language rankings, quantization penalties or iPhone measurements exist. Synthetic silence smoke tests exposed Whisper hallucinated text; those outputs are retained only as test evidence, not an evaluation leaderboard.
- All five original-weight families are installed with verified file hashes and executed on Linux CPU synthetic silence. Ultra uses a distinct TDT-core/no-VAD condition: six auxiliary VAD tensors are deliberately excluded, and NVIDIA v3 processor/generation descriptors are included with per-file provenance. Its published Photon segmentation/runtime is not reproduced. Independent owner-data parity is unvalidated. Optional NeMo/MLX adapters and all converted Apple variants remain unexecuted.
- No conversion has been independently validated against its reference on owner data. Qwen 0.6B Fluid Core ML has a published discrepancy and stale loader instructions. Newer Qwen 1.7B conversion is promising publisher evidence, not verified iPhone support.

## Functional limitations

- The native iOS17 app integrates source adapters for WhisperKit and FluidAudio only. Qwen iOS requires a separate architecture adapter and likely a newer OS target. The newer full Core ML candidate is tracked in the registry rather than enabled under an incorrect backend.
- Microphone mode is honestly post-recording batch. True streaming partials/end-of-speech detection are not implemented by this app. The UI never fakes them.
- Native deadlines/cancellation are checked between backend calls and before success; an in-flight Core ML prediction may not be preemptible. Physical responsiveness/cancellation latency remains untested.
- Device result synchronization authenticates ownership, revision and audio hash. The coordinator cannot independently attest that a modified client really used the claimed hardware. This is a personal trusted-client lab, not a remote-attestation service.
- Offline jobs have finite server leases. Very long disconnection can let another claimant invalidate the old attempt; local envelopes remain exportable for investigation instead of being silently attached to a new attempt.
- Native local evidence export is a SQLite snapshot; it does not automatically reconcile a conflicted job into a finalized server experiment. Audio/model assets remain in the app's storage and on the coordinator.
- Model installation UI verifies progress per completed file, not byte-level resume. A failed file restarts; previously verified files are reused. Asset storage and native download UI still need device testing.
- Error annotations are subjective flags/comments and automated alignments. Arbitrary timestamp/span annotation editing is not implemented.
- Profile archives can be attached/exported; trace parsing and numerical energy integration are not implemented. No API invents energy from battery percentage.
- The UI supports category/language filtering and side-by-side implementation evidence. There is no automatic causal diagnosis that attributes loss uniquely to quantization.
- Browser-local recovery depends on local storage availability. If storage is disabled/full, the editor still attempts server saves and uses a before-unload warning; copy unsaved text before leaving after an error. Recovery text is private local browser data and is cleared after successful save or explicit server-reference selection.

## Review findings addressed

- Exact saved reference revisions are now serialized in the write transaction, preventing a concurrent writer's CAS revision from being adopted.
- Blind review waits for terminal first repetitions and creates a separate session if retries change the output set; existing evidence remains intact.
- Turkish-containing explicit mixed labels use documented Turkish casing in normalization v2. Strict metrics remain available for ambiguous English/Turkish Latin text.
- Human-review language/tag filters now match the selected recording set.
- Native journal keys include attempt identities and retain previous envelopes; source-level actor/exclusivity corrections were applied.
- Native capability validation runs on every request, including engine reuse; cancelled/expired output is rejected before success persistence. These native changes still require compiler/device tests.

## Infrastructure/design tooling

Hugging Face and GitHub access now work after the user's network update. Superdesign's login endpoint continued returning HTTP403; no canvas design was created. The actual React UI was implemented and inspected locally, including desktop review and narrow-screen library screenshots. This tooling failure does not imply the application is deployed or Apple-validated.
