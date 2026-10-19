# Measurement and evaluation contract

## Dataset and preprocessing

Actual project evaluations use only the owner's recordings and manually verified references. Tests generate tones/silence and short text examples in isolated storage; they are not research results. The installed application contains no sample leaderboard.

Every original is content addressed by SHA-256. FFprobe records its source streams/format. FFmpeg decodes the first audio stream directly into mono 16 kHz signed 16-bit PCM WAV with metadata stripped and bitexact flags; originals remain untouched. Conversion arguments, FFmpeg version and the resulting hash are retained. Model adapters receive that exact canonical asset and record model-specific internal preparation through their pinned runtime and effective settings. A change of FFmpeg/runtime can alter bytes; hashes, not the word “canonical”, establish equality across experiments.

Silence is the fraction of canonical samples below about −60 dBFS; clipping is the fraction at absolute magnitude ≥32760. These are diagnostic observations, not speech detection. No default VAD, enhancement, loudness normalization or repeated preprocessing. The reference runners may perform their architecture's documented internal segmentation; Whisper uses sequential long-form generation, not the independent-chunk pipeline.

## Text metrics

`unicode-v2` applies NFC, whitespace folding, lowercase and Unicode punctuation-to-boundary replacement. Turkish `I → ı` and `İ → i` apply when the explicit language label contains `tr`, including `en+tr`. This is a documented whole-Latin-text casing policy: an unlabelled English pronoun in a Turkish-containing clip remains ambiguous. Strict metrics preserve case and punctuation. Generic `mixed` uses Unicode lowercase; use strict metrics when that ambiguity matters. No transliteration, Arabic alef folding, diacritic stripping or orthographic lexical substitutions occur.

Version 1 applied Turkish casing only for exactly `tr`. Persisted v1 results are retained; rescoring creates a v2 snapshot. A metric version is part of every saved evaluation, and changing code does not rewrite old scores.

WER tokenizes on whitespace and counts minimum Levenshtein substitutions, deletions and insertions. CER counts Unicode grapheme clusters, including internal normalized spaces. `WER=(S+D+I)/N`. Empty references have an undefined rate (`null`), with insertion counts retained. WER can exceed 100%; no clipping hides hallucinations. Strict and normalized metrics are separate.

Corpus rates sum edit counts and denominators across recordings. Accuracy uses the first measured repetition per recording; repeated inference is not treated as independent speech. Latency distributions use all successful measured repetitions. Failed/invalid attempts remain failures, never empty successful transcripts. A valid empty string from a model is a legitimate prediction and may incur deletions.

95% intervals resample recordings 1,000 times with a fixed seed and are unavailable below two recordings. Paired penalties resample matched recordings jointly. These are uncertainty descriptions of this personal dataset, not population-level claims about every speaker. Report category coverage, failure rates and unsupported-language exclusions before interpreting the table order.

## Reference and deployment comparisons

Lock checkpoint revision, per-file hashes, runtime version, precision by component, decoder/language settings, input hash and preprocessing. Automatic language identification is a different experimental condition from a forced hint. Parakeet v3/Ultra Arabic and Turkish pairs are excluded from supported-language aggregates.

The displayed paired penalty is `WER(deployment) − WER(reference)` on the same successful recordings. It is a deployment difference, not proof of quantization causality: backend, conversion, segmentation and decoding may differ. Inspect paired transcript changes. An installed manifest establishes byte identity; it does not establish conversion fidelity.

References have append-only revisions. Experiment snapshots retain their original verified text. Explicit rescoring uses current verified references and creates a separate evaluation snapshot. Finalized experiment inputs/results are immutable. Exports include each score snapshot and its raw reference/version.

## Human assessment

Initial reference editing does not show predictions. Blind review waits until all first-repetition jobs are terminal, then persists a random seed and anonymous mapping. Failed outputs are absent and remain visible as failures in the experiment; they are not ranked. If retry adds outputs, a new review session preserves the previous session rather than silently changing its mapping.

No model names, timing, automated error rates or family colors appear before lock. Human faithfulness, readability, meaning, proper nouns, technical vocabulary, hallucinations, missing words and comments are separate from WER. All outputs need faithfulness, readability and a rank to lock; ties share rank. The owner can inspect their own database, so this prevents accidental UI leakage rather than adversarial access.

## iPhone timing and conditions

Inference executes inside `NativeEngine`, which has no network/coordinator dependency. Assets and input audio are downloaded and verified before timing. ContinuousClock separates verification, model load, warmup and inference. New-engine loading is labelled with OS caches uncontrolled; reusing a loaded engine is explicit. App restart does not imply truly cold storage or ANE compilation.

Microphone capture is retained locally and measured separately. The current adapters implement **post-recording batch**, with no synthetic streaming partials or first-output time. Stop-to-result finalization includes preparation/loading/inference; model inference has its own clock. Sustained runs retain per-run context and thermal/memory observations before and after each call. Resident memory observations are not a peak-memory profiler.

Cancellation and deadlines are cooperative between backend calls. Core ML may not preempt an in-flight prediction; a cancelled or expired result must be rejected before success persistence. UI responsiveness, cancellation latency and resource behavior require real-device validation.

## Power profiling

Primary source: [Apple: Measuring your app's power use with Power Profiler](https://developer.apple.com/documentation/xcode/measuring-your-app-s-power-use-with-power-profiler), captured in `research/apple-power-profiler.json` on 2026-10-19.

Apple documents Power Profiler on iPhone with iOS 26+ and iPad with iPadOS 26+. Instruments can report overall-system battery energy per hour and app subsystem power-impact tracks. Power-impact values are device-model specific and must not be compared across different models. Charging makes overall-system power unavailable. Xcode pairing keeps Apple silicon awake, which affects controlled idle/sleep investigations.

For untethered collection, enable Developer Mode, Settings → Developer → Performance Trace, choose Power Profiler and your app, add the Performance Trace Control Center control, record, stop, and share the trace through Settings/AirDrop. Apple documents collection for up to ten hours. Retain the exact device, OS, build, battery/charging/Low Power Mode/thermal/display state and workload schedule.

Attach the original trace archive to its experiment. This app does not parse it into numerical energy. Battery percentage is an observation, never converted to joules per utterance. Reliable directly measured energy is unavailable in the built-in result schema. Use controlled, repeated comparisons on the same physical device, separating trace-derived system estimates from direct measurements.
