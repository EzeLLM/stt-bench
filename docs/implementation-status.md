# Implementation and evidence ledger

Date: 2026-10-19. Host: Linux x86-64, Python3.12, Node24, FFmpeg7.1.5; 4 CPU equivalents available. No Apple hardware/SDK. The project is a working portable research build with experimental native source, **not completion of every master-prompt acceptance gate**.

| Capability | Implemented | Exercised here | Mac / iPhone |
|---|---|---|---|
| Lossless bulk audio import, metadata/hashes/diagnostics | Yes | Real FFmpeg WAV/M4A/MP3/FLAC/AIFF/CAF fixtures; corruption/duplicates | Unrun on Mac |
| Library, tags/filtering, waveform/playback, RTL editor | Yes | Real browser/API import/edit/verify/history and narrow viewport | Browser only; no iOS UI validation |
| Append-only references, CAS conflicts, recovery drafts | Yes | Concurrent-response regression and browser failed-save/navigation recovery | Native not applicable |
| WER/CER/alignment/Unicode/corpus statistics | Yes | Known-count, Turkish/Arabic/mixed text, empty reference, aggregation and paired calculations | Portable engine |
| SQLite migrations, frozen jobs, leases, retry/cancel | Yes | Transaction/state/recovery/failure tests | Native client lifecycle unrun |
| Original Whisper Turbo reference | Yes; installed | Weights verified, actual Linux CPU short/31s synthetic runs, full coordinator-worker-score round trip | Mac/iPhone unrun |
| Qwen 0.6B and 1.7B original weights | Yes; installed | Official qwen-asr 0.0.6, actual Linux CPU synthetic silence | Mac/iPhone unrun |
| Parakeet v3 original / Ultra TDT core | Yes; installed | Transformers 5.20.1, Linux CPU; Ultra explicitly no auxiliary VAD, not Photon parity | Mac/iPhone unrun |
| NeMo / MLX Audio optional adapters | Source | Primary API inspection; no real invocation | Unrun |
| Blind ratings/ranking/ties/lock/diff | Yes | Identity hiding, incomplete-set/retry session regression; five-output browser flow | Desktop browser |
| Compare/drilldown/paired penalties/exports/rescoring | Yes | API and browser workflows; original score immutability | Portable backend |
| LAN pairing/device ownership/hash/idempotency | Yes | API tests, wrong-device/hash/duplicate rejection | Real LAN/phone unrun |
| Swift WhisperKit/FluidAudio engine + CLI | Source | Pinned API/static review only | **Build unrun** |
| SwiftUI home/cache/batch/microphone/sustained/results | Source | Static review only | **Build/device unrun** |
| Offline inference and local SQLite outbox | Source/protocol | Protocol tested; on-device operation unrun | **Unvalidated** |
| Memory/thermal/timing observations | Source | Distribution logic and protocol; no device measurements | **Unvalidated** |
| Instruments artifact preservation | Yes | Upload/context/immutability/API tests; Apple docs inspected | Actual trace collection unrun |
| Genuine streaming / Qwen iOS / causal conversion diagnosis | No complete integration | Explicit limitations | Remaining work |
| Owner-data accuracy / independent parity / iPhone efficiency study | No data/hardware | None; no invented numbers | Required external study |

## Verification commands

See `validation.md` for final recorded commands/outcomes. The opt-in actual model test is separate from the portable suite, which normally skips it. Synthetic transcripts in browser tests are explicitly labelled fixtures and stored in a fresh temporary database. Production storage contains installed model assets and an empty recording library.

## Independent review

One read-only fresh-context review identified reference response/CAS, blind-review completeness, native attempt recovery, source-level Swift actor/exclusivity and native cancellation/capability issues. The portable regressions were observed failing and then passing. Native corrections are source changes, not a claim of successful Apple compilation. No push, deployment, publication or physical-device run is inferred from this review.

## Design and plan

`architecture.md` is the living spec. `superpowers/plans/2026-10-19-stt-lab.md` is the execution checklist. The user's instruction to create the plan and execute it supplied the execution scope; no extra design-approval gate was imposed. The existing cloud checkout was used without a worktree.
