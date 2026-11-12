import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  EyeOff,
  GripVertical,
  LockKeyhole,
  PanelRight,
  ShieldCheck,
} from "lucide-react";
import {
  api,
  jsonBody,
  useResource,
  type Edit,
  type Experiment,
  type Job,
  type Rating,
  type Recording,
  type Review as ReviewData,
  type ShortlistModel,
} from "./api";
import { AudioPlayer, Badge, Empty, ErrorMessage } from "./ui";
import {
  moveTo,
  normalizeTies,
  orderFromRanks,
  ranksFromOrder,
  shift,
} from "./ranking";

const blankRating: Rating = {
  faithfulness: null,
  readability: null,
  rank: null,
  comment: "",
};

// View preferences only; ratings, ranks and the shortlist are always saved to the server.
const remembered = (key: string, fallback: string) => {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
};
const remember = (key: string, value: string) => {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage unavailable; the preference just will not persist */
  }
};

function Diff({
  edits,
  characters = false,
}: {
  edits: Edit[];
  characters?: boolean;
}) {
  const join = characters ? "" : " ";
  return (
    <p className="transcript diff" dir="auto">
      {edits.map((edit, i) => (
        <span key={i}>
          {edit.kind === "equal" ? (
            edit.hypothesis.join(join)
          ) : (
            <>
              <del className={edit.kind === "insert" ? "sr-only" : ""}>
                {edit.reference.join(join)}
              </del>
              {edit.hypothesis.length > 0 && (
                <mark className={edit.kind}>{edit.hypothesis.join(join)}</mark>
              )}
            </>
          )}
          {join}
        </span>
      ))}
    </p>
  );
}

function Chips({
  label,
  value,
  disabled,
  onPick,
}: {
  label: string;
  value: number | null | undefined;
  disabled: boolean;
  onPick: (value: number | null) => void;
}) {
  return (
    <div className="chips" role="radiogroup" aria-label={label}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          role="radio"
          aria-checked={value === n}
          aria-label={`${label} ${n}`}
          className={value === n ? "active" : ""}
          disabled={disabled}
          onClick={() => onPick(value === n ? null : n)}
        >
          {n}
        </button>
      ))}
    </div>
  );
}

function Shortlist({
  experimentId,
  recordingCount,
}: {
  experimentId: string;
  recordingCount: number;
}) {
  const [models, setModels] = useState<ShortlistModel[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    void api<{ models: ShortlistModel[] }>(
      `/experiments/${experimentId}/shortlist`,
    )
      .then((data) => {
        if (alive) setModels(data.models);
      })
      .catch((e) => setError(String(e)));
    return () => {
      alive = false;
    };
  }, [experimentId]);
  const save = async (model: ShortlistModel, change: Partial<ShortlistModel>) => {
    const next = { ...model, ...change };
    setModels((rows) => rows.map((m) => (m.model_id === model.model_id ? next : m)));
    try {
      await api(`/experiments/${experimentId}/candidates/${model.model_id}`, {
        method: "PUT",
        body: jsonBody({ advanced: next.advanced, note: next.note }),
      });
      setError("");
    } catch (e) {
      setError(String(e));
    }
  };
  const fixed = (value: number | null) => (value == null ? "—" : value.toFixed(2));
  return (
    <section className="analysis-section">
      <ErrorMessage error={error} />
      <p className="help">
        Built from locked reviews only. Mean rank is lower-is-better and is only
        comparable between models reviewed on the same recordings. Mark the
        models to test on the iPhone; choices are saved immediately.
      </p>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Model</th>
              <th>Reviewed</th>
              <th>Mean rank</th>
              <th>1st places</th>
              <th>Faithfulness</th>
              <th>Readability</th>
              <th>Advance to phone</th>
              <th>Note</th>
            </tr>
          </thead>
          <tbody>
            {models.map((m) => (
              <tr key={m.model_id}>
                <td>{m.model_id}</td>
                <td className="mono">
                  {m.reviews} / {recordingCount}
                </td>
                <td className="mono">{fixed(m.mean_rank)}</td>
                <td className="mono">{m.first_places}</td>
                <td className="mono">{fixed(m.mean_faithfulness)}</td>
                <td className="mono">{fixed(m.mean_readability)}</td>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`Advance ${m.model_id} to phone`}
                    checked={m.advanced}
                    onChange={(e) => void save(m, { advanced: e.target.checked })}
                  />
                </td>
                <td>
                  <input
                    aria-label={`${m.model_id} note`}
                    defaultValue={m.note}
                    onBlur={(e) => {
                      if (e.target.value !== m.note)
                        void save(m, { note: e.target.value });
                    }}
                    placeholder="Why / why not"
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function Review() {
  const experiments = useResource<Experiment[]>("/experiments", []);
  const recordings = useResource<Recording[]>("/recordings", []);
  const [experimentId, setExperimentId] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [recordingId, setRecordingId] = useState("");
  const [review, setReview] = useState<ReviewData | null>(null);
  const [ratings, setRatings] = useState<Record<string, Rating>>({});
  const [ranked, setRanked] = useState<string[]>([]);
  const [tied, setTied] = useState<Set<string>>(new Set());
  const [dragging, setDragging] = useState("");
  // The ref drives drop logic; state only styles the UI (re-rendering inside dragstart can cancel a drag).
  const dragRef = useRef("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [view, setView] = useState<"rank" | "shortlist">("rank");
  const [showTarget, setShowTarget] = useState(
    remembered("stt-lab-show-target", "0") === "1",
  );
  const [mode, setMode] = useState(remembered("stt-lab-diff-mode", "word"));
  const [focused, setFocused] = useState(0);
  const [inspector, setInspector] = useState(false);
  const [busy, setBusy] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sessionGeneration = useRef(0);
  const saveChain = useRef(Promise.resolve());
  const ratingsRef = useRef<Record<string, Rating>>({});
  const selectedExperiment =
    experimentId ||
    experiments.data.find((e) => (e.counts.succeeded || 0) > 0)?.id ||
    "";
  const shownMode = showTarget ? mode : "raw";
  useEffect(() => {
    let alive = true;
    if (!selectedExperiment) {
      setJobs([]);
      return;
    }
    setRecordingId(remembered(`stt-lab-review-recording:${selectedExperiment}`, ""));
    void api<Job[]>(`/experiments/${selectedExperiment}/jobs`)
      .then((rows) => {
        if (alive) setJobs(rows);
      })
      .catch((e) => setError(String(e)));
    return () => {
      alive = false;
    };
  }, [selectedExperiment]);
  const eligibleIds = new Set(
    jobs
      .filter((j) => j.state === "succeeded" && j.repetition === 0)
      .map((j) => j.recording_id),
  );
  const queue = recordings.data.filter((r) => eligibleIds.has(r.id));
  const selectedRecording = queue.find((r) => r.id === recordingId) || queue[0];
  const chooseRecording = (id: string) => {
    setRecordingId(id);
    remember(`stt-lab-review-recording:${selectedExperiment}`, id);
  };
  useEffect(() => {
    const generation = ++sessionGeneration.current;
    if (timer.current) clearTimeout(timer.current);
    setReview(null);
    setRatings({});
    setRanked([]);
    setTied(new Set());
    ratingsRef.current = {};
    setFocused(0);
    if (!selectedRecording || !selectedExperiment) return;
    void api<ReviewData>("/reviews", {
      method: "POST",
      body: jsonBody({
        experiment_id: selectedExperiment,
        recording_id: selectedRecording.id,
      }),
    })
      .then((data) => {
        if (sessionGeneration.current === generation) {
          const order = orderFromRanks(
            data.outputs.map((o) => o.id),
            Object.fromEntries(
              Object.entries(data.ratings).map(([id, r]) => [id, r.rank]),
            ),
          );
          setReview(data);
          setRatings(data.ratings);
          setRanked(order.ranked);
          setTied(order.tied);
          ratingsRef.current = data.ratings;
          setSaved(data.locked ? "Review locked" : "Progress saved");
          setError("");
        }
      })
      .catch((e) => setError(String(e)));
  }, [selectedExperiment, selectedRecording?.id, refreshToken]);
  const persist = useCallback(
    (values: Record<string, Rating>, session: ReviewData) => {
      const generation = sessionGeneration.current;
      const next = saveChain.current.then(async () => {
        try {
          if (generation === sessionGeneration.current) setSaved("Saving…");
          await api(`/reviews/${session.id}`, {
            method: "PUT",
            body: jsonBody({ ratings: values }),
          });
          if (generation === sessionGeneration.current) {
            setSaved("Progress saved");
            setError("");
          }
        } catch (e) {
          if (generation === sessionGeneration.current) setError(String(e));
          throw e;
        }
      });
      saveChain.current = next.catch(() => {});
      return next;
    },
    [],
  );
  const rate = useCallback(
    (
      id: string,
      key: keyof Rating,
      value: number | string | boolean | null,
    ) => {
      if (!review || review.locked) return;
      const base = ratingsRef.current[id] || blankRating;
      const next = { ...ratingsRef.current, [id]: { ...base, [key]: value } };
      ratingsRef.current = next;
      setRatings(next);
      void persist(next, review).catch(() => {});
    },
    [review, persist],
  );
  // The explicit order is the source of truth while editing; ranks are derived and saved.
  const commitOrder = useCallback(
    (nextRanked: string[], nextTied: Set<string>) => {
      if (!review || review.locked) return;
      const cleanTies = normalizeTies(nextRanked, nextTied);
      const ranks = ranksFromOrder(nextRanked, cleanTies);
      const next = Object.fromEntries(
        review.outputs.map((o) => [
          o.id,
          { ...(ratingsRef.current[o.id] || blankRating), rank: ranks[o.id] ?? null },
        ]),
      );
      ratingsRef.current = next;
      setRatings(next);
      setRanked(nextRanked);
      setTied(cleanTies);
      void persist(next, review).catch(() => {});
    },
    [review, persist],
  );
  const navigate = useCallback(
    (delta: number) => {
      const index = queue.findIndex((r) => r.id === selectedRecording?.id);
      const target = queue[index + delta];
      if (target) chooseRecording(target.id);
    },
    [queue, selectedRecording?.id],
  );
  useEffect(() => {
    const handle = (e: KeyboardEvent) => {
      if (
        (e.target as HTMLElement).closest(
          "input, textarea, select, [contenteditable]",
        )
      )
        return;
      const focusedId = review?.outputs[focused]?.id;
      if (e.shiftKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
        if (focusedId && ranked.includes(focusedId)) {
          e.preventDefault();
          commitOrder(shift(ranked, focusedId, e.key === "ArrowUp" ? -1 : 1), tied);
        }
        return;
      }
      if (e.key.toLowerCase() === "j") navigate(1);
      if (e.key.toLowerCase() === "k") navigate(-1);
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setFocused((v) => Math.min(v + 1, (review?.outputs.length || 1) - 1));
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setFocused((v) => Math.max(0, v - 1));
      }
      if (/^[1-5]$/.test(e.key) && focusedId)
        rate(focusedId, "faithfulness", Number(e.key));
    };
    window.addEventListener("keydown", handle);
    return () => window.removeEventListener("keydown", handle);
  }, [focused, review, navigate, rate, ranked, tied, commitOrder]);
  const reference = selectedRecording
    ? jobs.find((j) => j.recording_id === selectedRecording.id)?.snapshot
        .reference
    : null;
  const locked = !!review?.locked;
  const missing = review
    ? review.outputs.flatMap((o) => {
        const r = ratings[o.id];
        const gaps = [
          !r?.rank && "rank",
          !r?.faithfulness && "faithfulness",
          !r?.readability && "readability",
        ].filter(Boolean);
        return gaps.length ? [`${o.id}: ${gaps.join(", ")}`] : [];
      })
    : [];
  const unranked = review
    ? review.outputs.map((o) => o.id).filter((id) => !ranked.includes(id))
    : [];
  const renderCard = (id: string, position: number | null) => {
    const output = review!.outputs.find((o) => o.id === id)!;
    const index = review!.outputs.indexOf(output);
    const rating = ratings[id];
    const isTied = position !== null && position > 0 && tied.has(id);
    return (
      <article
        key={id}
        className={`output-row ${focused === index ? "focused" : ""} ${dragging === id ? "dragging" : ""}`}
        onClick={() => setFocused(index)}
        onDragOver={(e) => {
          if (dragRef.current && position !== null) e.preventDefault();
        }}
        onDrop={(e) => {
          if (!dragRef.current || position === null) return;
          e.preventDefault();
          e.stopPropagation();
          commitOrder(moveTo(ranked, dragRef.current, id), tied);
          dragRef.current = "";
          setDragging("");
        }}
      >
        <div className="output-heading">
          {!locked && (
            <span
              role="img"
              className="drag-handle"
              title="Drag to rank"
              aria-label={`Drag ${id}`}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData("text/plain", id);
                e.dataTransfer.effectAllowed = "move";
                const card = (e.currentTarget as HTMLElement).closest("article");
                if (card) e.dataTransfer.setDragImage(card, 16, 16);
                dragRef.current = id;
                setTimeout(() => setDragging(id), 0);
              }}
              onDragEnd={() => {
                dragRef.current = "";
                setDragging("");
              }}
            >
              <GripVertical size={16} />
            </span>
          )}
          <strong>{id}</strong>
          {locked && output.model_id && <Badge>{output.model_id}</Badge>}
          <span className="muted small">
            {rating?.rank ? `Rank ${rating.rank}` : "Unranked"}
          </span>
          {!locked && position !== null && (
            <span className="rank-controls">
              <button
                type="button"
                className="icon-button"
                aria-label={`Move ${id} up`}
                disabled={position === 0}
                onClick={() => commitOrder(shift(ranked, id, -1), tied)}
              >
                <ArrowUp size={14} />
              </button>
              <button
                type="button"
                className="icon-button"
                aria-label={`Move ${id} down`}
                disabled={position === ranked.length - 1}
                onClick={() => commitOrder(shift(ranked, id, 1), tied)}
              >
                <ArrowDown size={14} />
              </button>
              {position > 0 && (
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    aria-label={`${id} ties with the card above`}
                    checked={isTied}
                    onChange={(e) => {
                      const next = new Set(tied);
                      if (e.target.checked) next.add(id);
                      else next.delete(id);
                      commitOrder(ranked, next);
                    }}
                  />
                  Tie with above
                </label>
              )}
              <button
                type="button"
                className="button secondary small-button"
                onClick={() => {
                  const next = new Set(tied);
                  next.delete(id);
                  commitOrder(
                    ranked.filter((x) => x !== id),
                    next,
                  );
                }}
              >
                Unrank
              </button>
            </span>
          )}
          {!locked && position === null && (
            <button
              type="button"
              className="button secondary small-button"
              onClick={() => commitOrder([...ranked, id], tied)}
            >
              Add to ranking
            </button>
          )}
        </div>
        {shownMode === "raw" ? (
          <p className="transcript" dir="auto">
            {output.text || <em className="muted">Empty transcription</em>}
          </p>
        ) : (
          <Diff
            edits={
              shownMode === "word" ? output.alignment : output.character_alignment
            }
            characters={shownMode === "character"}
          />
        )}
        <div className="rating-controls">
          <div>
            <span className="chips-label">Faithfulness</span>
            <Chips
              label={`${id} Faithfulness`}
              value={rating?.faithfulness}
              disabled={locked}
              onPick={(v) => rate(id, "faithfulness", v)}
            />
          </div>
          <div>
            <span className="chips-label">Readability</span>
            <Chips
              label={`${id} Readability`}
              value={rating?.readability}
              disabled={locked}
              onPick={(v) => rate(id, "readability", v)}
            />
          </div>
          <label className="comment-label">
            Comment
            <input
              aria-label={`${id} comment`}
              disabled={locked}
              value={rating?.comment || ""}
              onChange={(e) => rate(id, "comment", e.target.value)}
              placeholder="Meaning, vocabulary, missing words…"
            />
          </label>
        </div>
      </article>
    );
  };
  return (
    <div className="workspace review-workspace">
      <div className="page-header">
        <div>
          <div className="breadcrumb">
            ASSESSMENT <span>/</span> HUMAN JUDGMENT
          </div>
          <h1>Transcript review</h1>
          <p>
            Listen first, then rank the transcripts. Identities are revealed
            after you lock.
          </p>
        </div>
        <Badge tone="success">
          <ShieldCheck size={13} />{" "}
          {review?.locked ? "Identities revealed" : "Blind assessment"}
        </Badge>
      </div>
      <ErrorMessage error={error || experiments.error} />
      {error && (
        <button
          className="button secondary small-button"
          onClick={() => setRefreshToken((value) => value + 1)}
        >
          Refresh blind output set
        </button>
      )}
      {!selectedExperiment || !queue.length ? (
        <Empty icon={EyeOff} title="A fair review starts with real outputs">
          Complete an experiment with successful transcriptions.
          <br />
          The lab will randomize their order and hide models, scores and
          timings.
        </Empty>
      ) : (
        <>
          <div className="review-toolbar">
            <select
              aria-label="Review experiment"
              value={selectedExperiment}
              onChange={(e) => {
                setExperimentId(e.target.value);
                setRecordingId("");
              }}
            >
              {experiments.data.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.name}
                </option>
              ))}
            </select>
            <div className="segmented">
              {(
                [
                  ["rank", "Rank"],
                  ["shortlist", "Shortlist"],
                ] as const
              ).map(([value, title]) => (
                <button
                  key={value}
                  className={view === value ? "active" : ""}
                  onClick={() => setView(value)}
                >
                  {title}
                </button>
              ))}
            </div>
            {view === "rank" && (
              <>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={showTarget}
                    onChange={(e) => {
                      setShowTarget(e.target.checked);
                      remember("stt-lab-show-target", e.target.checked ? "1" : "0");
                    }}
                  />
                  Target text
                </label>
                {showTarget && (
                  <div className="segmented">
                    {[
                      ["word", "Word diff"],
                      ["character", "Character diff"],
                      ["raw", "Raw text"],
                    ].map(([value, title]) => (
                      <button
                        key={value}
                        className={mode === value ? "active" : ""}
                        onClick={() => {
                          setMode(value);
                          remember("stt-lab-diff-mode", value);
                        }}
                      >
                        {title}
                      </button>
                    ))}
                  </div>
                )}
                <button
                  className="icon-button"
                  aria-label="Toggle review details"
                  onClick={() => setInspector(!inspector)}
                >
                  <PanelRight size={17} />
                </button>
              </>
            )}
          </div>
          {view === "shortlist" ? (
            <Shortlist
              experimentId={selectedExperiment}
              recordingCount={queue.length}
            />
          ) : (
            <div className={`review-body ${inspector ? "details-open" : ""}`}>
              <aside className="review-queue">
                <div className="section-label">
                  RECORDINGS <span>{queue.length}</span>
                </div>
                {queue.map((r, index) => (
                  <button
                    key={r.id}
                    className={r.id === selectedRecording?.id ? "active" : ""}
                    onClick={() => chooseRecording(r.id)}
                  >
                    <span className="queue-index">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span>
                      <strong>{r.name}</strong>
                      <small>
                        {r.language.toUpperCase()} · {r.tags.slice(0, 1).join("")}
                      </small>
                    </span>
                  </button>
                ))}
              </aside>
              <main className="comparison-main">
                {selectedRecording && (
                  <>
                    <div className="review-recording-title">
                      <h2>{selectedRecording.name}</h2>
                      <div className="button-row">
                        <button
                          aria-label="Previous recording"
                          className="icon-button"
                          disabled={queue[0]?.id === selectedRecording.id}
                          onClick={() => navigate(-1)}
                        >
                          <ArrowLeft size={16} />
                        </button>
                        <button
                          aria-label="Next recording"
                          className="icon-button"
                          disabled={
                            queue[queue.length - 1]?.id === selectedRecording.id
                          }
                          onClick={() => navigate(1)}
                        >
                          <ArrowRight size={16} />
                        </button>
                      </div>
                    </div>
                    <AudioPlayer
                      key={selectedRecording.id}
                      recording={selectedRecording}
                    />
                    {showTarget && (
                      <section className="review-reference">
                        <div className="section-label">
                          FROZEN VERIFIED REFERENCE{" "}
                          <Badge>revision {reference?.revision}</Badge>
                        </div>
                        <p className="transcript" dir="auto">
                          {reference?.text ||
                            "(Verified silence / empty reference)"}
                        </p>
                      </section>
                    )}
                  </>
                )}
                {review ? (
                  <div className="output-list">
                    <div className="section-label">
                      RANKING · BEST FIRST <span>{ranked.length}</span>
                    </div>
                    <div
                      className={`rank-list ${dragging ? "drop-ready" : ""}`}
                      aria-label="Ranked outputs"
                      onDragOver={(e) => {
                        if (dragRef.current) e.preventDefault();
                      }}
                      onDrop={(e) => {
                        if (!dragRef.current) return;
                        e.preventDefault();
                        commitOrder(moveTo(ranked, dragRef.current, null), tied);
                        dragRef.current = "";
                        setDragging("");
                      }}
                    >
                      {ranked.length ? (
                        ranked.map((id, i) => renderCard(id, i))
                      ) : (
                        <p className="help rank-empty">
                          Drag outputs here, best first, or use “Add to ranking”.
                        </p>
                      )}
                    </div>
                    {(unranked.length > 0 || dragging) && (
                      <>
                        <div className="section-label">
                          UNRANKED <span>{unranked.length}</span>
                        </div>
                        <div
                          className={`rank-list tray ${dragging ? "drop-ready" : ""}`}
                          aria-label="Unranked outputs"
                          onDragOver={(e) => {
                            if (dragRef.current) e.preventDefault();
                          }}
                          onDrop={(e) => {
                            if (!dragRef.current) return;
                            e.preventDefault();
                            const dropped = dragRef.current;
                            const next = new Set(tied);
                            next.delete(dropped);
                            commitOrder(
                              ranked.filter((x) => x !== dropped),
                              next,
                            );
                            dragRef.current = "";
                            setDragging("");
                          }}
                        >
                          {unranked.map((id) => renderCard(id, null))}
                        </div>
                      </>
                    )}
                  </div>
                ) : (
                  <div className="loading">Preparing anonymous comparison…</div>
                )}
                <div className="review-footer">
                  <span className="small muted">
                    {saved} · drag or ↑↓ to rank · Shift+↑↓ moves the focused
                    card · 1–5 faithfulness · J/K recording
                  </span>
                  {review && !locked && (
                    <>
                      {missing.length > 0 && (
                        <span className="small warning-text" role="status">
                          To lock: {missing.join(" · ")}
                        </span>
                      )}
                      <button
                        className="button small-button"
                        disabled={busy || missing.length > 0}
                        onClick={async () => {
                          setBusy(true);
                          try {
                            await persist(ratings, review);
                            const done = await api<ReviewData>(
                              `/reviews/${review.id}/lock`,
                              { method: "POST" },
                            );
                            setReview(done);
                            setError("");
                            setSaved("Review locked");
                          } catch (e) {
                            setError(String(e));
                          } finally {
                            setBusy(false);
                          }
                        }}
                      >
                        <LockKeyhole size={14} /> Lock & reveal identities
                      </button>
                    </>
                  )}
                </div>
              </main>
              {inspector && (
                <aside className="review-details">
                  <div className="section-label">ASSESSMENT DETAILS</div>
                  <p className="help">
                    The same style is used for every anonymous output. Ranks can
                    tie. Automated scores and timings remain hidden until this
                    review is locked.
                  </p>
                  <div className="diff-legend">
                    <span>
                      <i className="substitute" /> Substitution
                    </span>
                    <span>
                      <i className="insert" /> Insertion
                    </span>
                    <span>
                      <i className="delete" /> Deletion
                    </span>
                  </div>
                  {review?.outputs[focused] && (
                    <>
                      <h3>{review.outputs[focused].id}</h3>
                      {[
                        ["semantic_preservation", "Semantic preservation"],
                        ["proper_nouns", "Proper nouns"],
                        ["technical_vocabulary", "Technical vocabulary"],
                      ].map(([key, title]) => (
                        <label key={key}>
                          {title}
                          <select
                            disabled={locked}
                            value={
                              ratings[review.outputs[focused].id]?.[
                                key as "proper_nouns"
                              ] || ""
                            }
                            onChange={(e) =>
                              rate(
                                review.outputs[focused].id,
                                key as keyof Rating,
                                e.target.value ? Number(e.target.value) : null,
                              )
                            }
                          >
                            <option value="">Not rated</option>
                            {[1, 2, 3, 4, 5].map((x) => (
                              <option key={x}>{x}</option>
                            ))}
                          </select>
                        </label>
                      ))}
                      {[
                        ["hallucination", "Hallucination observed"],
                        ["missing_words", "Missing words observed"],
                      ].map(([key, title]) => (
                        <label key={key} className="checkbox-label">
                          <input
                            type="checkbox"
                            disabled={locked}
                            checked={
                              !!ratings[review.outputs[focused].id]?.[
                                key as "hallucination"
                              ]
                            }
                            onChange={(e) =>
                              rate(
                                review.outputs[focused].id,
                                key as keyof Rating,
                                e.target.checked,
                              )
                            }
                          />
                          {title}
                        </label>
                      ))}
                    </>
                  )}
                </aside>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
