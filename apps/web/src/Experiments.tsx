import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  CheckCheck,
  CirclePause,
  FlaskConical,
  Play,
  Plus,
  RotateCcw,
  Square,
  Smartphone,
  Monitor,
  FileDown,
} from "lucide-react";
import {
  api,
  jsonBody,
  percent,
  useResource,
  type Experiment,
  type Job,
  type Model,
  type Recording,
} from "./api";
import { Badge, Empty, ErrorMessage, Modal } from "./ui";
import { LANGUAGES } from "./Library";

export default function Experiments({
  notify,
}: {
  notify: (s: string) => void;
}) {
  const experiments = useResource<Experiment[]>("/experiments", []);
  const recordings = useResource<Recording[]>("/recordings", []);
  const models = useResource<{ installed: Model[]; candidates: Model[] }>(
    "/models",
    { installed: [], candidates: [] },
  );
  const [activeId, setActiveId] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [artifacts, setArtifacts] = useState<{id:string;name:string;sha256:string;measurement_kind:string}[]>([]);
  const traceInput = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("Personal speech · accuracy");
  const [modelIds, setModelIds] = useState<string[]>([]);
  const [recordingIds, setRecordingIds] = useState<string[]>([]);
  const [language, setLanguage] = useState("");
  const [tag, setTag] = useState("");
  const [target, setTarget] = useState("mac");
  const [mode, setMode] = useState("auto");
  const [repetitions, setRepetitions] = useState(1);
  const [warmups, setWarmups] = useState(0);
  const [seed, setSeed] = useState(42);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<{
    job_count: number;
    exclusions: unknown[];
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const active =
    experiments.data.find((e) => e.id === activeId) || experiments.data[0];
  useEffect(() => {
    if (!active) {
      setJobs([]);
      return;
    }
    let alive = true;
    const refresh = async () => {
      try {
        const rows = await api<Job[]>(`/experiments/${active.id}/jobs`);
        const profiles = await api<typeof artifacts>(`/experiments/${active.id}/artifacts`);
        if (alive) { setJobs(rows); setArtifacts(profiles); }
      } catch (e) {
        if (alive) setError(String(e));
      }
    };
    void refresh();
    const timer = setInterval(() => {
      void refresh();
      void experiments.reload();
    }, 2500);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [active?.id, experiments.reload]);
  const eligible = recordings.data.filter(
    (r) =>
      r.reference.status === "verified" &&
      (!language || r.language === language) &&
      (!tag || r.tags.includes(tag)),
  );
  const selectedRecordings = recordingIds.filter((id) =>
    eligible.some((r) => r.id === id),
  );
  const selectedModels = models.data.installed
    .filter(
      (m) =>
        modelIds.includes(m.id) &&
        (target === "mac" ||
          ["whisperkit", "fluidaudio"].includes(m.runtime || "")),
    )
    .map((m) => m.id);
  const payload = () => ({
    name,
    target,
    recording_ids: selectedRecordings,
    model_ids: selectedModels,
    seed,
    settings: { language_mode: mode, repetitions, warmups, temperature: 0 },
  });
  const mutate = async (command: string) => {
    if (!active) return;
    setBusy(true);
    try {
      await api(`/experiments/${active.id}/${command}`, { method: "POST" });
      await experiments.reload();
      setJobs(await api(`/experiments/${active.id}/jobs`));
      setError("");
      notify(
        `Experiment ${command === "retry" ? "failed jobs queued" : command}`,
      );
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };
  const pending = active
    ? (active.counts.queued || 0) + (active.counts.running || 0)
    : 0;
  const percentDone = active
    ? (((active.counts.succeeded || 0) +
        (active.counts.failed || 0) +
        (active.counts.cancelled || 0)) /
        active.job_count) *
      100
    : 0;
  return (
    <div className="workspace">
      <div className="page-header">
        <div>
          <div className="breadcrumb">
            BENCHMARK <span>/</span> REPRODUCIBLE RUNS
          </div>
          <h1>Experiments</h1>
          <p>
            Freeze inputs and settings. Preserve every output, attempt and
            failure.
          </p>
        </div>
        <button
          className="button"
          onClick={() => {
            setRecordingIds(eligible.map((r) => r.id));
            setOpen(true);
          }}
        >
          <Plus size={16} /> New experiment
        </button>
      </div>
      <ErrorMessage error={error || experiments.error} />
      {!models.data.installed.length && (
        <div className="notice">
          <FlaskConical size={18} />
          <div>
            <strong>No installed checkpoints</strong>
            <p>
              The registry contains research candidates. Stage model files and
              register a hash-verified manifest before running inference.{" "}
              <a href="#registry">
                Open model registry <ArrowRight size={12} />
              </a>
            </p>
          </div>
        </div>
      )}
      {experiments.data.length ? (
        <>
          <div className="experiment-tabs">
            {experiments.data.map((e) => (
              <button
                key={e.id}
                className={active?.id === e.id ? "active" : ""}
                onClick={() => setActiveId(e.id)}
              >
                {e.target === "mac" ? (
                  <Monitor size={15} />
                ) : (
                  <Smartphone size={15} />
                )}
                <span>{e.name}</span>
                <Badge
                  tone={
                    e.state === "completed" || e.state === "finalized"
                      ? "success"
                      : ""
                  }
                >
                  {e.state}
                </Badge>
              </button>
            ))}
          </div>
          {active && (
            <section className="run-panel">
              <div className="run-header">
                <div>
                  <span className="eyebrow">
                    {active.target === "mac"
                      ? "MAC ACCURACY"
                      : "IPHONE · LOCAL INFERENCE ONLY"}
                  </span>
                  <h2>{active.name}</h2>
                  <p className="muted small">
                    {active.settings.language_mode} language ·{" "}
                    {active.settings.repetitions} repetition(s) ·{" "}
                    {new Date(active.created_at).toLocaleString()}
                  </p>
                </div>
                <div className="button-row">
                  {!active.finalized_at && (
                    <>
                      <button
                        className="button small-button"
                        disabled={busy || active.state === "running"}
                        onClick={() =>
                          void mutate(
                            active.state === "draft" ? "start" : "resume",
                          )
                        }
                      >
                        <Play size={14} />
                        {active.state === "draft" ? "Start" : "Resume"}
                      </button>
                      <button
                        className="button secondary small-button"
                        disabled={busy || active.state !== "running"}
                        onClick={() => void mutate("pause")}
                      >
                        <CirclePause size={14} /> Pause
                      </button>
                      <button
                        className="icon-button"
                        aria-label="Cancel experiment"
                        disabled={busy || !pending}
                        onClick={() => void mutate("cancel")}
                      >
                        <Square size={15} />
                      </button>
                    </>
                  )}
                  <a
                    className="button secondary small-button"
                    href={`/api/v1/export/${active.id}?format=csv`}
                    download
                  >
                    <FileDown size={14} /> CSV
                  </a>
                <button className="button secondary small-button" disabled={busy || !!active.finalized_at} onClick={() => traceInput.current?.click()}>Attach profiling trace</button>
                <input ref={traceInput} aria-label="Profiling trace file" type="file" hidden accept=".zip,.aar,.xctrace" onChange={async e => { const file = e.target.files?.[0]; if (!file) return; const form = new FormData(); form.append('file',file); form.append('measurement_kind','external-trace'); try { await api(`/experiments/${active.id}/artifacts`,{method:'POST',body:form}); setArtifacts(await api(`/experiments/${active.id}/artifacts`)); notify('Profiling artifact attached with its hash and experiment context'); } catch(error) { setError(String(error)); } e.target.value=''; }}/>
                  <a
                    className="button secondary small-button"
                    href={`/api/v1/export/${active.id}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    JSON
                  </a>
                </div>
              </div>
              <div className="run-progress">
                <progress value={percentDone} max={100} />
                <span>
                  {active.counts.succeeded || 0} succeeded ·{" "}
                  {active.counts.failed || 0} failed · {pending} pending /{" "}
                  {active.job_count}
                </span>
                <div className="button-row">
                  <button
                    className="text-button"
                    disabled={
                      busy || !active.counts.failed || !!active.finalized_at
                    }
                    onClick={() => void mutate("retry")}
                  >
                    <RotateCcw size={13} /> Retry failed
                  </button>
                  <button
                    className="text-button"
                    disabled={busy || pending > 0 || !!active.finalized_at}
                    onClick={() => void mutate("finalize")}
                  >
                    <CheckCheck size={13} /> Finalize
                  </button>
                </div>
              </div>
              {artifacts.length > 0 && <div className="notice compact"><div><strong>Profiling artifacts · preserved source traces</strong>{artifacts.map(a => <p key={a.id}><a href={`/api/v1/artifacts/${a.id}`} download>{a.name}</a> · {a.measurement_kind} · <span className="mono">{a.sha256.slice(0,12)}</span></p>)}</div></div>}
              <div className="table-scroll">
                <table className="data-table job-table">
                  <thead>
                    <tr>
                      <th>Recording / checkpoint</th>
                      <th>Run</th>
                      <th>State</th>
                      <th>WER</th>
                      <th>CER</th>
                      <th>Inference</th>
                    </tr>
                  </thead>
                  <tbody>
                    {jobs.map((job) => (
                      <tr key={job.id}>
                        <td>
                          <strong>{job.snapshot.recording.name}</strong>
                          <div className="muted small">
                            {job.snapshot.model.family} ·{" "}
                            {job.snapshot.model.variant}
                          </div>
                          {job.error && (
                            <details className="job-error">
                              <summary>
                                Failure · {job.attempts.length} attempt(s)
                              </summary>
                              <pre>{job.error}</pre>
                            </details>
                          )}
                          {job.stale_reference && (
                            <Badge tone="warning">
                              Reference changed after snapshot
                            </Badge>
                          )}
                          {!job.snapshot.supported_language && (
                            <Badge tone="warning">
                              Exploratory · unsupported language
                            </Badge>
                          )}
                        </td>
                        <td className="mono">{job.repetition + 1}</td>
                        <td>
                          <Badge
                            tone={
                              job.state === "succeeded"
                                ? "success"
                                : job.state === "failed"
                                  ? "danger"
                                  : ""
                            }
                          >
                            {job.state}
                          </Badge>
                        </td>
                        <td className="mono">
                          {percent(job.scores?.normalized.word.rate)}
                        </td>
                        <td className="mono">
                          {percent(job.scores?.normalized.character.rate)}
                        </td>
                        <td className="mono">
                          {job.output
                            ? `${job.output.measurements.inference_seconds.toFixed(3)} s`
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </>
      ) : (
        <Empty
          icon={FlaskConical}
          title="One experiment. Every implementation."
          action={
            <button
              className="button secondary"
              onClick={() => {
                setRecordingIds(eligible.map((r) => r.id));
                setOpen(true);
              }}
            >
              Configure your first experiment
            </button>
          }
        >
          Select verified recordings and exact checkpoints.
          <br />
          The lab saves a fixed snapshot before any model runs.
        </Empty>
      )}
      <Modal open={open} onOpenChange={setOpen} title="Configure experiment">
        <div className="experiment-form">
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <div className="form-grid">
            <label>
              Execution
              <select
                value={target}
                onChange={(e) => {
                  setTarget(e.target.value);
                  setPreview(null);
                }}
              >
                <option value="mac">Mac · accuracy</option>
                <option value="iphone">iPhone · on-device batch</option>
              </select>
            </label>
            <label>
              Language mode
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="auto">Automatic detection</option>
                <option value="forced">Force recording language</option>
              </select>
            </label>
            <label>
              Measured repetitions
              <input
                type="number"
                min={1}
                max={100}
                value={repetitions}
                onChange={(e) => setRepetitions(Number(e.target.value))}
              />
            </label>
            <label>
              Warmups per load
              <input
                type="number"
                min={0}
                max={20}
                value={warmups}
                onChange={(e) => setWarmups(Number(e.target.value))}
              />
            </label>
            <label>
              Randomization seed
              <input
                type="number"
                min={0}
                value={seed}
                onChange={(e) => setSeed(Number(e.target.value))}
              />
            </label>
          </div>
          <div className="section-label">
            VERIFIED RECORDINGS{" "}
            <span>{selectedRecordings.length} selected</span>
          </div>
          <div className="form-grid">
            <select
              aria-label="Experiment recording language"
              value={language}
              onChange={(e) => {
                setLanguage(e.target.value);
                setPreview(null);
              }}
            >
              <option value="">All languages</option>
              {LANGUAGES.map(([code, title]) => (
                <option key={code} value={code}>
                  {title}
                </option>
              ))}
            </select>
            <input
              placeholder="Filter exact tag"
              aria-label="Experiment tag filter"
              value={tag}
              onChange={(e) => {
                setTag(e.target.value);
                setPreview(null);
              }}
            />
          </div>
          <button
            className="text-button"
            onClick={() => setRecordingIds(eligible.map((r) => r.id))}
          >
            Select all matching
          </button>
          <div className="checklist">
            {eligible.length ? (
              eligible.map((r) => (
                <label key={r.id}>
                  <input
                    type="checkbox"
                    checked={recordingIds.includes(r.id)}
                    onChange={(e) =>
                      setRecordingIds(
                        e.target.checked
                          ? [...recordingIds, r.id]
                          : recordingIds.filter((id) => id !== r.id),
                      )
                    }
                  />
                  <span>{r.name}</span>
                  <Badge>{r.language}</Badge>
                </label>
              ))
            ) : (
              <p className="help">
                No matching verified references. Verify recordings in the
                library first.
              </p>
            )}
          </div>
          <div className="section-label">EXACT CHECKPOINTS</div>
          <div className="checklist">
            {models.data.installed
              .filter(
                (m) =>
                  target !== "iphone" ||
                  ["whisperkit", "fluidaudio"].includes(m.runtime || ""),
              )
              .map((m) => (
                <label key={m.id}>
                  <input
                    type="checkbox"
                    checked={modelIds.includes(m.id)}
                    onChange={(e) =>
                      setModelIds(
                        e.target.checked
                          ? [...modelIds, m.id]
                          : modelIds.filter((id) => id !== m.id),
                      )
                    }
                  />
                  <span>
                    {m.family}
                    <small>
                      {m.variant} · {m.runtime} · {m.revision?.slice(0, 8)}
                    </small>
                  </span>
                </label>
              ))}
            {!models.data.installed.length && (
              <p className="help">
                No installed checkpoints. Register a complete local manifest in
                the registry.
              </p>
            )}
          </div>
          <p className="help">
            Greedy decoding, no VAD or enhancement. Unsupported-language pairs
            are excluded. Each Mac job uses a new process; OS file cache is
            uncontrolled. iPhone adapters remain experimental until tested on
            your hardware.
          </p>
          <ErrorMessage error={error} />
          {preview && (
            <div className="notice compact">
              {preview.job_count} compatible jobs · {preview.exclusions.length}{" "}
              unsupported pairs excluded
            </div>
          )}
          <div className="modal-actions">
            <button
              className="button secondary"
              disabled={
                !selectedRecordings.length || !selectedModels.length || busy
              }
              onClick={async () => {
                try {
                  setPreview(
                    await api("/experiments/preview", {
                      method: "POST",
                      body: jsonBody(payload()),
                    }),
                  );
                  setError("");
                } catch (e) {
                  setError(String(e));
                }
              }}
            >
              Preview jobs
            </button>
            <button
              className="button"
              disabled={
                !selectedRecordings.length || !selectedModels.length || busy
              }
              onClick={async () => {
                setBusy(true);
                try {
                  const created = await api<Experiment>("/experiments", {
                    method: "POST",
                    body: jsonBody(payload()),
                  });
                  setActiveId(created.id);
                  setOpen(false);
                  setError("");
                  await experiments.reload();
                  notify("Experiment snapshot created");
                } catch (e) {
                  setError(String(e));
                } finally {
                  setBusy(false);
                }
              }}
            >
              Create experiment <ArrowRight size={15} />
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
