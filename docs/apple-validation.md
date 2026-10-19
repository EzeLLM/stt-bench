# Apple build and physical-device acceptance

**Unrun on this Linux host.** The native package and app are experimental source, including static-review fixes. A source review is not compiler or physical-device evidence. Do not publish native performance numbers until the gates below pass.

## Mac build

1. Install Xcode with iOS SDK, Swift 6+ and XcodeGen. Resolve `runners/apple-native/Package.swift` and preserve the generated `Package.resolved`; top-level dependency revisions and FluidAudio's binary checksum are pinned, but transitive resolution is not yet locked by an Apple build.
2. Run `swift test` and `swift build -c release` from `runners/apple-native`.
3. Generate `apps/ios/STTBenchmarkLab.xcodeproj` using `xcodegen generate`; choose your bundle identifier/signing team. Build for a physical device with iOS 17+.
4. Treat compiler/SDK incompatibilities as remaining integration work. The current source was checked against pinned upstream public APIs, but these commands have not run here.

## One checkpoint at a time

- Stage all compiled components and tokenizer/vocabulary assets, verify exact hashes, and register a new immutable manifest. Preserve requested compute units and actual encoder choice.
- Load and transcribe a known owner recording on Mac; compare the saved raw text with the original reference runtime under explicitly recorded settings. Do not infer parity from load success.
- Pair the phone over trusted LAN, install/cache the model, and cache all experiment recordings. Confirm input hashes match the coordinator.
- Disconnect Wi-Fi completely. Run the cached batch and record the result. Verify no network fallback, no model repair/download, no system/cloud speech fallback and no hidden host inference.
- Compare the phone's raw transcript with the same checkpoint/runtime on Mac and the original reference. Record any mismatch; do not blame quantization before checking conversion/decoder/windowing.

## Reliability and measurement

- Test clean install, app update, unloaded/new engine, reused engine, configured warmups and measured repetitions separately. OS/ANE caches are not controlled by app restart.
- Try cancellation during loading, warmups and inference, plus an intentionally short deadline. A noncooperative Core ML prediction may finish before cancellation can be observed; its late output must not enter success history.
- Test wrong checkpoint hashes, incomplete downloads, unavailable storage, corrupted input, lost Wi-Fi, process kill/restart, expired/reassigned job lease, duplicate sync and a retry with a new attempt ID. Keep old envelopes and export conflicts through Results.
- Exercise microphone recording after permissions denial/regrant, capture interruption, and rapid start/stop. Current mode is post-recording batch, not genuine streaming. Validate UI response on the main thread and stop-to-final timestamps on hardware.
- Run sustained owner audio under fixed display brightness, orientation, charging/battery state and Low Power Mode. Retain per-run latency, memory observations, thermal transitions and failures. A before/after resident-memory sample is not a peak-memory guarantee; use Instruments Allocations/VM tools for peak behavior.
- Repeat randomized model order with a controlled cooldown protocol. Do not compare different thermal histories as if they were equivalent.

## Power

Follow the Apple Power Profiler instructions and limitations in `methodology.md`. On iOS 26+, use Instruments or untethered Developer Performance Trace. Preserve the original archive with experiment, run ordering and device conditions. There is no built-in numerical joules-per-inference estimate. Attach artifacts before finalizing the experiment; finalized evidence is immutable.

## Qwen

The iOS17 target does not integrate Qwen. The newer full Core ML runtime candidate requires iOS26+ and its own complete encoder/decoder/tokenizer implementation. Its publisher explicitly has not tested iPhone. An architecture-specific Swift adapter and real memory/parity study are required; copying MLX Python weights into the phone does not satisfy this gate. No proprietary SDK or paid runtime is used.
