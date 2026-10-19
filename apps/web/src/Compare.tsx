import { useEffect, useMemo, useState } from "react";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import {
  ArrowDownUp,
  ChartNoAxesCombined,
  FileDown,
  GitCompareArrows,
} from "lucide-react";
import {
  api,
  percent,
  useResource,
  type Counts,
  type Experiment,
  type Job,
} from "./api";
import { Badge, Empty, ErrorMessage, Modal } from "./ui";
import { LANGUAGES } from "./Library";

type Distribution = {
  count: number;
  median: number | null;
  p95: number | null;
  mean: number | null;
  stddev: number | null;
  min: number | null;
  max: number | null;
};
type Row = {
  model_id: string;
  family: string;
  variant: string;
  revision: string;
  runtime: string;
  parity: string;
  metrics: { word: Counts; character: Counts };
  strict_metrics: { word: Counts; character: Counts };
  wer_ci95: [number, number] | null;
  completed_recordings: number;
  eligible_recordings: number;
  failed_jobs: number;
  failure_rate: number;
  total_jobs: number;
  stale_references: number;
  latency: Distribution;
  rtf: Distribution;
  load_time: Distribution;
};
type Comparison = {
  rows: Row[];
  penalties: {
    reference_model_id: string;
    deployment_model_id: string;
    penalty: number | null;
    ci95: [number, number] | null;
    paired_recordings: number;
    attribution: string;
  }[];
  human_reviews: {
    model_id: string;
    rank: number;
    faithfulness: number;
    readability: number;
  }[];
  methodology: string;
};
const seconds = (value: number | null) =>
  value == null ? "—" : `${value.toFixed(3)} s`;

export default function Compare() {
  const experiments = useResource<Experiment[]>("/experiments", []);
  const [experimentId, setExperimentId] = useState("");
  const [language, setLanguage] = useState("");
  const [tag, setTag] = useState("");
  const [strict, setStrict] = useState(false);
  const [data, setData] = useState<Comparison | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState("");
  const [evaluationId, setEvaluationId] = useState("");
  const [evaluations, setEvaluations] = useState<
    { id: string; version: string; created_at: string }[]
  >([]);
  const [sorting, setSorting] = useState<SortingState>([
    { id: "wer", desc: false },
  ]);
  const [drill, setDrill] = useState("");
  const [other, setOther] = useState("");
  const active =
    experimentId ||
    experiments.data.find((e) => (e.counts.succeeded || 0) > 0)?.id;
  useEffect(() => {
    if (!active) return;
    let alive = true;
    void Promise.all([
      api<Comparison>(
        `/compare/${active}?language=${encodeURIComponent(language)}&tag=${encodeURIComponent(tag)}${evaluationId ? `&evaluation_id=${evaluationId}` : ""}`,
      ),
      api<Job[]>(
        `/experiments/${active}/jobs${evaluationId ? `?evaluation_id=${evaluationId}` : ""}`,
      ),
    ])
      .then(([result, rows]) => {
        if (alive) {
          setData(result);
          setJobs(rows);
          setError("");
        }
      })
      .catch((e) => setError(String(e)));
    return () => {
      alive = false;
    };
  }, [active, language, tag, evaluationId]);
  useEffect(() => {
    if (active)
      void api<{ id: string; version: string; created_at: string }[]>(
        `/experiments/${active}/evaluations`,
      )
        .then(setEvaluations)
        .catch((e) => setError(String(e)));
  }, [active]);
  const columns = useMemo<ColumnDef<Row>[]>(
    () => [
      {
        accessorKey: "family",
        header: "Implementation",
        cell: ({ row }) => (
          <button
            className="model-cell"
            onClick={() => setDrill(row.original.model_id)}
          >
            <strong>{row.original.family}</strong>
            <small>
              {row.original.variant} · {row.original.runtime}
            </small>
            <span className="mono muted small">
              {row.original.revision.slice(0, 8)}
            </span>
          </button>
        ),
      },
      {
        id: "wer",
        accessorFn: (r) => (strict ? r.strict_metrics : r.metrics).word.rate,
        header: "WER ↓",
        sortUndefined: "last",
        cell: ({ row }) => (
          <div className="metric-cell">
            <strong className="mono">
              {percent(
                (strict ? row.original.strict_metrics : row.original.metrics)
                  .word.rate,
              )}
            </strong>
            <span className="metric-bar">
              <span
                style={{
                  width: `${Math.min(100, ((strict ? row.original.strict_metrics : row.original.metrics).word.rate || 0) * 100)}%`,
                }}
              />
            </span>
          </div>
        ),
      },
      {
        id: "cer",
        accessorFn: (r) =>
          (strict ? r.strict_metrics : r.metrics).character.rate,
        header: "CER ↓",
        cell: (info) => (
          <span className="mono">
            {percent(info.getValue<number | null>())}
          </span>
        ),
      },
      {
        id: "ci",
        header: "WER · 95% CI",
        cell: ({ row }) => (
          <span className="mono small">
            {!strict && row.original.wer_ci95
              ? `${percent(row.original.wer_ci95[0])} – ${percent(row.original.wer_ci95[1])}`
              : "Insufficient / unavailable"}
          </span>
        ),
      },
      {
        id: "coverage",
        header: "Coverage",
        accessorFn: (r) =>
          r.completed_recordings / Math.max(1, r.eligible_recordings),
        cell: ({ row: { original: r } }) => (
          <span
            className={
              r.completed_recordings < r.eligible_recordings
                ? "warning-text mono"
                : "mono"
            }
          >
            {r.completed_recordings} / {r.eligible_recordings}
          </span>
        ),
      },
      {
        accessorKey: "failure_rate",
        header: "Failed",
        cell: ({ row: { original: r } }) => (
          <span className={r.failed_jobs ? "danger-text" : "muted"}>
            {r.failed_jobs} / {r.total_jobs}
          </span>
        ),
      },
      {
        id: "median",
        accessorFn: (r) => r.latency.median,
        header: "Median latency",
        cell: (info) => (
          <span className="mono">
            {seconds(info.getValue<number | null>())}
          </span>
        ),
      },
      {
        id: "p95",
        accessorFn: (r) => r.latency.p95,
        header: "P95",
        cell: (info) => (
          <span className="mono">
            {seconds(info.getValue<number | null>())}
          </span>
        ),
      },
      {
        id: "rtf",
        accessorFn: (r) => r.rtf.median,
        header: "Median RTF",
        cell: (info) => (
          <span className="mono">
            {info.getValue<number | null>()?.toFixed(3) ?? "—"}
          </span>
        ),
      },
    ],
    [strict],
  );
  const table = useReactTable({
    data: data?.rows || [],
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });
  const tags = Array.from(
    new Set(
      jobs.flatMap(
        (j) =>
          (j as Job & { snapshot: { tags: string[] } }).snapshot.tags || [],
      ),
    ),
  ).sort();
  return (
    <div className="workspace">
      <div className="page-header">
        <div>
          <div className="breadcrumb">
            ANALYSIS <span>/</span> FOLLOW THE EVIDENCE
          </div>
          <h1>Compare implementations</h1>
          <p>
            Accuracy, deployment loss and measured performance. No composite
            winner.
          </p>
        </div>
        {active && (
          <a
            className="button secondary"
            href={`/api/v1/export/${active}`}
            target="_blank"
            rel="noreferrer"
          >
            <FileDown size={15} /> Export evidence
          </a>
        )}
      </div>
      <ErrorMessage error={error || experiments.error} />
      {!active ? (
        <Empty icon={ChartNoAxesCombined} title="Evidence before rankings">
          Run an experiment on your verified recordings.
          <br />
          Every aggregate will link back to its inputs, revisions and outputs.
        </Empty>
      ) : (
        <>
          <div className="toolbar compare-toolbar">
            <select
              aria-label="Comparison experiment"
              value={active}
              onChange={(e) => {
                setExperimentId(e.target.value);
                setEvaluationId("");
              }}
            >
              {experiments.data.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.name}
                </option>
              ))}
            </select>
            <select
              aria-label="Comparison language"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              <option value="">All supported languages</option>
              {LANGUAGES.map(([code, label]) => (
                <option key={code} value={code}>
                  {label}
                </option>
              ))}
            </select>
            <select
              aria-label="Comparison condition"
              value={tag}
              onChange={(e) => setTag(e.target.value)}
            >
              <option value="">All speech conditions</option>
              {tags.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={strict}
                onChange={(e) => setStrict(e.target.checked)}
              />{" "}
              Strict text
            </label>
          </div>
          <div className="toolbar">
            <label>
              Evaluation snapshot
              <select
                aria-label="Evaluation snapshot"
                value={evaluationId}
                onChange={(e) => setEvaluationId(e.target.value)}
              >
                <option value="">Original frozen scores</option>
                {evaluations.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.version} · {new Date(e.created_at).toLocaleString()}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="button secondary small-button"
              onClick={async () => {
                try {
                  const created = await api<{ id: string }>(
                    `/experiments/${active}/evaluations`,
                    { method: "POST" },
                  );
                  setEvaluations(
                    await api(`/experiments/${active}/evaluations`),
                  );
                  setEvaluationId(created.id);
                } catch (e) {
                  setError(String(e));
                }
              }}
            >
              Rescore current verified references
            </button>
            <span className="help">
              Creates a new immutable score snapshot. Original scores stay
              unchanged.
            </span>
          </div>
          <div className="analysis-note">
            <span className="status-dot" />
            Corpus WER · total edits / total reference words{" "}
            <span className="muted">/</span> Lower is better{" "}
            <span className="muted">/</span> Click an implementation to inspect
            recordings
          </div>
          {data &&
            data.rows.some(
              (r) => r.completed_recordings < r.eligible_recordings,
            ) && (
              <div className="notice warning">
                Partial coverage: compare matched successful recordings before
                interpreting this order. Failure rates remain separate from
                accuracy.
              </div>
            )}
          {data?.rows.some((r) => r.stale_references) && (
            <div className="notice warning">
              Ground truth changed after this experiment. These scores retain
              the original frozen references; create a new experiment to
              evaluate corrections.
            </div>
          )}
          <div className="table-scroll compare-table">
            <table className="data-table">
              <thead>
                {table.getHeaderGroups().map((group) => (
                  <tr key={group.id}>
                    {group.headers.map((h) => (
                      <th key={h.id}>
                        <button
                          className="sort-button"
                          onClick={h.column.getToggleSortingHandler()}
                        >
                          {flexRender(
                            h.column.columnDef.header,
                            h.getContext(),
                          )}
                          {h.column.getCanSort() && <ArrowDownUp size={11} />}
                        </button>
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody>
                {table.getRowModel().rows.map((row) => (
                  <tr key={row.id}>
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id}>
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext(),
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="methodology">{data?.methodology}</p>
          <section className="analysis-section">
            <div className="section-heading">
              <h2>
                <GitCompareArrows size={18} /> Reference → deployment
              </h2>
              <Badge>Paired recordings only</Badge>
            </div>
            {data?.penalties.length ? (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Reference</th>
                    <th>Deployment</th>
                    <th>WER difference</th>
                    <th>Paired recordings</th>
                    <th>95% CI</th>
                  </tr>
                </thead>
                <tbody>
                  {data.penalties.map((p) => (
                    <tr
                      key={`${p.reference_model_id}-${p.deployment_model_id}`}
                    >
                      <td>{p.reference_model_id}</td>
                      <td>{p.deployment_model_id}</td>
                      <td className="mono">
                        {p.penalty == null
                          ? "—"
                          : `${p.penalty > 0 ? "+" : ""}${(p.penalty * 100).toFixed(2)} pp`}
                      </td>
                      <td className="mono">{p.paired_recordings}</td>
                      <td className="mono">
                        {p.ci95
                          ? `${(p.ci95[0] * 100).toFixed(2)} to ${(p.ci95[1] * 100).toFixed(2)} pp`
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="help">
                Include an original reference and a deployment checkpoint from
                the same family to calculate paired accuracy loss.
              </p>
            )}
            <p className="help">
              This is a deployment difference. Quantization, conversion, backend
              and decoding can all contribute. Bit-width labels are not
              equivalent across formats.
            </p>
          </section>
          <section className="analysis-section">
            <h2>Locked human assessments</h2>
            {data?.human_reviews.length ? (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Implementation</th>
                    <th>Mean faithfulness</th>
                    <th>Mean readability</th>
                    <th>Mean rank</th>
                    <th>Assessments</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r) => {
                    const reviews = data.human_reviews.filter(
                      (v) => v.model_id === r.model_id,
                    );
                    if (!reviews.length) return null;
                    return (
                      <tr key={r.model_id}>
                        <td>{r.model_id}</td>
                        <td>
                          {(
                            reviews.reduce(
                              (sum, v) => sum + v.faithfulness,
                              0,
                            ) / reviews.length
                          ).toFixed(2)}
                        </td>
                        <td>
                          {(
                            reviews.reduce((sum, v) => sum + v.readability, 0) /
                            reviews.length
                          ).toFixed(2)}
                        </td>
                        <td>
                          {(
                            reviews.reduce((sum, v) => sum + v.rank, 0) /
                            reviews.length
                          ).toFixed(2)}
                        </td>
                        <td>{reviews.length}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <p className="help">
                No locked blind reviews for this experiment. Human judgments
                stay separate from automated scores.
              </p>
            )}
          </section>
        </>
      )}
      <Modal
        open={!!drill}
        onOpenChange={(open) => {
          if (!open) setDrill("");
        }}
        title="Recording-level evidence"
      >
        <div className="form-grid">
          <label>
            Implementation
            <select value={drill} onChange={(e) => setDrill(e.target.value)}>
              {data?.rows.map((r) => (
                <option key={r.model_id}>{r.model_id}</option>
              ))}
            </select>
          </label>
          <label>
            Compare transcript
            <select value={other} onChange={(e) => setOther(e.target.value)}>
              <option value="">Reference only</option>
              {data?.rows
                .filter((r) => r.model_id !== drill)
                .map((r) => (
                  <option key={r.model_id}>{r.model_id}</option>
                ))}
            </select>
          </label>
        </div>
        {jobs
          .filter(
            (j) =>
              j.model_id === drill &&
              j.repetition === 0 &&
              (!language || j.snapshot.recording.language === language) &&
              (!tag ||
                (
                  j.snapshot as Job["snapshot"] & { tags: string[] }
                ).tags?.includes(tag)),
          )
          .map((job) => (
            <article className="evidence-entry" key={job.id}>
              <div className="split">
                <strong>{job.snapshot.recording.name}</strong>
                <Badge tone={job.state === "succeeded" ? "success" : "danger"}>
                  {job.state}
                </Badge>
              </div>
              <span className="small muted">
                Input{" "}
                {job.snapshot.recording.canonical?.sha256 ||
                  (job.snapshot.recording as RecordingHash).asset_sha256}{" "}
                · reference r
                {(job.evaluation_reference || job.snapshot.reference).revision}
              </span>
              <p className="transcript evidence-reference" dir="auto">
                {(job.evaluation_reference || job.snapshot.reference).text}
              </p>
              <div className={other ? "side-by-side" : ""}>
                <div>
                  <span className="eyebrow">{drill}</span>
                  <p className="transcript" dir="auto">
                    {job.output?.text ?? job.error ?? "No output"}
                  </p>
                  <small>
                    WER {percent(job.scores?.normalized.word.rate)} · CER{" "}
                    {percent(job.scores?.normalized.character.rate)}
                  </small>
                </div>
                {other && (
                  <div>
                    <span className="eyebrow">{other}</span>
                    <p className="transcript" dir="auto">
                      {jobs.find(
                        (j) =>
                          j.recording_id === job.recording_id &&
                          j.model_id === other &&
                          j.repetition === 0,
                      )?.output?.text ?? "No successful output"}
                    </p>
                  </div>
                )}
              </div>
            </article>
          ))}
      </Modal>
    </div>
  );
}
type RecordingHash = { asset_sha256: string };
