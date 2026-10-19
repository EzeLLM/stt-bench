import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Eye,
  EyeOff,
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
} from "./api";
import { AudioPlayer, Badge, Empty, ErrorMessage } from "./ui";

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

export default function Review() {
  const experiments = useResource<Experiment[]>("/experiments", []);
  const recordings = useResource<Recording[]>("/recordings", []);
  const [experimentId, setExperimentId] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [recordingId, setRecordingId] = useState("");
  const [review, setReview] = useState<ReviewData | null>(null);
  const [ratings, setRatings] = useState<Record<string, Rating>>({});
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [mode, setMode] = useState("raw");
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
  useEffect(() => {
    let alive = true;
    if (!selectedExperiment) {
      setJobs([]);
      return;
    }
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
  useEffect(() => {
    const generation = ++sessionGeneration.current;
    if (timer.current) clearTimeout(timer.current);
    setReview(null);
    setRatings({});
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
          setReview(data);
          setRatings(data.ratings);
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
      const base = ratingsRef.current[id] || {
        faithfulness: null,
        readability: null,
        rank: null,
        comment: "",
      };
      const next = { ...ratingsRef.current, [id]: { ...base, [key]: value } };
      ratingsRef.current = next;
      setRatings(next);
      void persist(next, review).catch(() => {});
    },
    [review, persist],
  );
  const navigate = useCallback(
    (delta: number) => {
      const index = queue.findIndex((r) => r.id === selectedRecording?.id);
      const target = queue[index + delta];
      if (target) setRecordingId(target.id);
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
      if (/^[1-5]$/.test(e.key) && review?.outputs[focused])
        rate(review.outputs[focused].id, "faithfulness", Number(e.key));
    };
    window.addEventListener("keydown", handle);
    return () => window.removeEventListener("keydown", handle);
  }, [focused, review, navigate, rate]);
  const reference = selectedRecording
    ? jobs.find((j) => j.recording_id === selectedRecording.id)?.snapshot
        .reference
    : null;
  return (
    <div className="workspace review-workspace">
      <div className="page-header">
        <div>
          <div className="breadcrumb">
            ASSESSMENT <span>/</span> HUMAN JUDGMENT
          </div>
          <h1>Transcript review</h1>
          <p>
            Listen first. Compare faithfully. Reveal identities after you
            commit.
          </p>
        </div>
        <Badge tone="success">
          <ShieldCheck size={13} />{" "}
          {review?.locked ? "Identities revealed" : "Blind assessment"}
        </Badge>
      </div>
      <ErrorMessage error={error || experiments.error} />
      {error && <button className="button secondary small-button" onClick={() => setRefreshToken(value => value + 1)}>Refresh blind output set</button>}
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
              {[
                ["raw", "Raw text"],
                ["word", "Word diff"],
                ["character", "Character diff"],
              ].map(([value, title]) => (
                <button
                  key={value}
                  className={mode === value ? "active" : ""}
                  onClick={() => setMode(value)}
                >
                  {title}
                </button>
              ))}
            </div>
            <button
              className="icon-button"
              aria-label="Toggle review details"
              onClick={() => setInspector(!inspector)}
            >
              <PanelRight size={17} />
            </button>
          </div>
          <div className={`review-body ${inspector ? "details-open" : ""}`}>
            <aside className="review-queue">
              <div className="section-label">
                RECORDINGS <span>{queue.length}</span>
              </div>
              {queue.map((r, index) => (
                <button
                  key={r.id}
                  className={r.id === selectedRecording?.id ? "active" : ""}
                  onClick={() => setRecordingId(r.id)}
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
                </>
              )}
              <div className="output-list">
                {review ? (
                  review.outputs.map((output, index) => (
                    <article
                      key={output.id}
                      className={`output-row ${focused === index ? "focused" : ""}`}
                      onClick={() => setFocused(index)}
                    >
                      <div className="output-heading">
                        <strong>{output.id}</strong>
                        {review.locked && <Badge>{output.model_id}</Badge>}
                        <span className="muted small">
                          {ratings[output.id]?.rank
                            ? `Rank ${ratings[output.id].rank}`
                            : "Unranked"}
                        </span>
                      </div>
                      {mode === "raw" ? (
                        <p className="transcript" dir="auto">
                          {output.text || (
                            <em className="muted">Empty transcription</em>
                          )}
                        </p>
                      ) : (
                        <Diff
                          edits={
                            mode === "word"
                              ? output.alignment
                              : output.character_alignment
                          }
                          characters={mode === "character"}
                        />
                      )}
                      <div className="rating-controls">
                        {[
                          ["faithfulness", "Faithfulness"],
                          ["readability", "Readability"],
                          ["rank", "Rank"],
                        ].map(([key, title]) => (
                          <label key={key}>
                            {title}
                            <select
                              aria-label={`${output.id} ${title}`}
                              disabled={review.locked}
                              value={ratings[output.id]?.[key as "rank"] || ""}
                              onChange={(e) =>
                                rate(
                                  output.id,
                                  key as keyof Rating,
                                  e.target.value
                                    ? Number(e.target.value)
                                    : null,
                                )
                              }
                            >
                              <option value="">—</option>
                              {Array.from(
                                {
                                  length:
                                    key === "rank" ? review.outputs.length : 5,
                                },
                                (_, i) => (
                                  <option key={i + 1} value={i + 1}>
                                    {i + 1}
                                    {key === "rank" ? "" : " / 5"}
                                  </option>
                                ),
                              )}
                            </select>
                          </label>
                        ))}
                        <label className="comment-label">
                          Comment
                          <input
                            aria-label={`${output.id} comment`}
                            disabled={review.locked}
                            value={ratings[output.id]?.comment || ""}
                            onChange={(e) =>
                              rate(output.id, "comment", e.target.value)
                            }
                            placeholder="Meaning, vocabulary, missing words…"
                          />
                        </label>
                      </div>
                    </article>
                  ))
                ) : (
                  <div className="loading">Preparing anonymous comparison…</div>
                )}
              </div>
              <div className="review-footer">
                <span className="small muted">
                  {saved} · 1–5 faithfulness · ↑↓ output · J/K recording
                </span>
                {review && !review.locked && (
                  <button
                    className="button small-button"
                    disabled={busy}
                    onClick={async () => {
                      setBusy(true);
                      try {
                        await persist(ratings, review);
                        const locked = await api<ReviewData>(
                          `/reviews/${review.id}/lock`,
                          { method: "POST" },
                        );
                        setReview(locked);
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
                          disabled={review.locked}
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
                          disabled={review.locked}
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
        </>
      )}
    </div>
  );
}
