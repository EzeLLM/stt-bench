# Web ranking workspace (piece 1 of 4)

Status: implemented (simplified from the first draft). Not committed.

## Context: the two-stage pipeline

The owner picks a model in two stages:

1. **Web (quality).** Fast iteration. Listen to a recording, read each model's transcript, rank them, and shortlist the best candidates.
2. **Phone (deployment).** Run only the shortlisted candidates on a physical iPhone and read latency, memory, thermal and power evidence. The final choice combines both.

This spec covers only stage 1's workspace. The other pieces get their own specs:

| # | Piece | Status |
|---|---|---|
| 1 | Web ranking workspace + shortlist (this spec) | drafting |
| 2 | Shortlist → iPhone experiment handoff | not started |
| 3 | Native app built, signed and run on device | not started; Xcode is present on this Mac, build has never run |
| 4 | Final decision view (quality beside phone readings, no blended score) | not started; replaces the Compare leaderboard |

## Goals

- Per recording, in order: **audio**, then **transcript cards**, then rank them by dragging (or keyboard / number keys).
- **Target text is a toggle**, off by default. Off: raw transcripts only, so the text cannot bias the ranking. On: the frozen reference is shown and each card shows a word diff (character diff selectable) against it.
- **Everything is saved server-side.** Closing the tab, reloading or switching machines loses nothing: ranks, tie flags, ratings, comments, selected recording, toggles and the shortlist.
- After locking, a **Shortlist** view summarizes locked human rankings per model across recordings and lets the owner mark candidates to advance to the phone.

## Non-goals

- No change to scoring, WER/CER, rescoring, metric versions or the experiment/job model.
- No reference-less experiments. Verified target text stays mandatory when a recording is added; the toggle only hides it in this view.
- No leaderboard redesign (that is piece 4). The Compare page is left untouched by this spec.
- No composite or blended score anywhere.
- No iPhone code (pieces 2–3).

## Constraints carried from the project

- Blind until lock: identities, WER and timings stay hidden; lock still requires faithfulness, readability and rank for every output (`reviews.py:141-147`). Unchanged.
- Preserve evidence: locked reviews stay immutable; shortlist changes are append-only events, never overwrites.
- No example results in production storage; fixtures only in isolated test storage.
- Audio stays local; no external requests.

## UX

### Layout (per recording)

- Left: recording queue with a state dot per recording (unranked / partly ranked / ranked / locked) and J/K navigation as today.
- Top of main pane: audio player (existing `AudioPlayer`), pinned while scrolling.
- Toolbar: experiment selector; **Target text** toggle; diff mode (word / character) shown only when target text is on.
- Target text on: reference panel above the cards, with revision badge, plus diff rendering on each card via the existing `Diff` component and the `alignment` / `character_alignment` already returned by `GET /reviews/{id}`.
- Cards: anonymous label (Output 1…), transcript (raw or diff), rank position number, compact 1–5 chips for faithfulness and readability, comment field, and the detail ratings from the existing inspector.

### Ranking

- Ranked cards form an ordered list, best on top; unranked cards sit in a tray below. Drag a card into the list or reorder within it.
- **Tie with card above** toggle on each ranked card (except the first). Ranks use competition numbering (1, 1, 3), which the backend already accepts (`rank` ≥ 1, ≤ number of outputs).
- Keyboard: focus a card, Space to pick up, ↑/↓ to move, Space to drop; pressing a digit also sets that rank. Existing shortcuts (1–5 faithfulness, ↑↓ focus, J/K recording) keep working.
- Each change auto-saves through the existing `PUT /reviews/{id}` queue (the serialized save chain in `Review.tsx` is kept). The Lock button lists exactly what is missing ("Output 2: readability").

### Shortlist view (after reviews are locked)

- Table per experiment, one row per model: locked-review count, mean rank, number of first places, mean faithfulness and readability. WER/CER may appear as a separate, labelled automated column since reviews are locked by then.
- Per-row **Advance to phone** toggle with an optional note. Coverage is shown beside it (how many recordings this model was ranked on), because ranks from different recording sets are not comparable.
- Models never ranked or with failures are shown as such, never hidden.

## Data and API (as built)

Kept deliberately small:

- Migration to `user_version = 3` adds one table, `candidates(experiment_id, model_id, advanced, note, updated_at)`, upserted per (experiment, model). The shortlist is an owner selection, not scientific evidence, so it is not append-only.
- `GET /experiments/{id}/shortlist` returns per-model aggregates from locked reviews only (reviews, mean rank, first places, mean faithfulness/readability) plus the candidate flag and note. `PUT /experiments/{id}/candidates/{model_id}` saves the flag.
- Ranks, ratings and comments keep using the existing review endpoints unchanged.
- View preferences (target-text toggle, diff mode, last recording per experiment) are browser `localStorage` conveniences. Anything that is data is saved on the server.
- Drag and drop uses native HTML5 events with a plain drag handle (a `<button>` does not start a drag in Chrome), plus ↑/↓ buttons and Shift+↑/↓ for keyboard users. No new dependency.
- Tied cards share a rank, so their relative order is not stored and they reload sorted by label.

## Testing

- Backend (pytest, isolated storage): migration from v2 to v3 preserves data; candidate events are append-only with latest-wins; shortlist aggregates use only locked reviews and handle ties; unlocked reviews are excluded; workspace round-trip.
- Frontend unit logic (rank-from-order, ties, partial ranking, reorder): extracted as pure functions and tested with Playwright's runner or a small TS test, whichever the project already supports.
- Playwright: five-output review with target text off then on; drag ranking, keyboard ranking, tie toggle, reload persistence, lock, shortlist toggle, plus a narrow viewport.
- Manual browser verification with real audio playback and diffs, recorded before the work is called done. Synthetic fixtures are labelled as such.
- Standard checks from `AGENTS.md`: `.venv/bin/pytest -q`, `.venv/bin/ruff check services tests scripts`, `npm --prefix apps/web build`, `npm --prefix apps/web test`.

## Assumptions to confirm during review

- Review stays blind while ranking; names appear only after lock.
- Compare is not touched until piece 4.
- A single owner uses the app, so last-write-wins for UI state is acceptable.
