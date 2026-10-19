import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  Check,
  CheckCheck,
  Clock3,
  FileAudio,
  History,
  Inbox,
  Plus,
  Search,
  SlidersHorizontal,
  Upload,
  X,
} from "lucide-react";
import {
  api,
  duration,
  jsonBody,
  size,
  useResource,
  type Recording,
  type Reference,
} from "./api";
import { AudioPlayer, Badge, Empty, ErrorMessage, Modal } from "./ui";

export const LANGUAGES = [
  ["en", "English"],
  ["tr", "Turkish"],
  ["ar", "Arabic"],
  ["de", "German"],
  ["en+tr", "English + Turkish"],
  ["en+ar", "English + Arabic"],
  ["mixed", "Other multilingual"],
];

function readRecovery(
  id: string,
): { text: string; status: "draft" | "verified"; revision: number } | null {
  try {
    const value = JSON.parse(
      localStorage.getItem(`stt-lab-unsaved-${id}`) || "null",
    );
    return value &&
      typeof value.text === "string" &&
      Number.isInteger(value.revision) &&
      ["draft", "verified"].includes(value.status)
      ? value
      : null;
  } catch {
    return null;
  }
}

function GroundTruth({
  recording,
  onUpdate,
}: {
  recording: Recording;
  onUpdate: () => void;
}) {
  const [recovery] = useState(() => readRecovery(recording.id));
  const [text, setText] = useState(recovery?.text ?? recording.reference.text);
  const [status, setStatus] = useState(
    recovery?.status ?? recording.reference.status,
  );
  const [saved, setSaved] = useState(
    recovery
      ? "Recovered unsaved local draft"
      : `Saved · revision ${recording.reference.revision}`,
  );
  const [error, setError] = useState("");
  const [history, setHistory] = useState<Reference[] | null>(null);
  const [serverReference, setServerReference] = useState<Reference | null>(
    null,
  );
  const latest = useRef({
    text: recovery?.text ?? recording.reference.text,
    status: recovery?.status ?? recording.reference.status,
    revision: recovery?.revision ?? recording.reference.revision,
    dirty: !!recovery,
  });
  const recoveryKey = `stt-lab-unsaved-${recording.id}`;
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const chain = useRef(Promise.resolve());
  const mounted = useRef(true);
  const flush = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    chain.current = chain.current.then(async () => {
      if (!latest.current.dirty) return;
      const snapshot = { ...latest.current };
      try {
        localStorage.setItem(recoveryKey, JSON.stringify(snapshot));
      } catch {
        /* Server save remains available when local storage is full. */
      }
      if (mounted.current) setSaved("Saving…");
      try {
        const result = await api<Recording>(
          `/recordings/${recording.id}/reference`,
          {
            method: "PUT",
            body: jsonBody({
              text: snapshot.text,
              status: snapshot.status,
              expected_revision: snapshot.revision,
            }),
          },
        );
        latest.current.revision = result.reference.revision;
        if (
          latest.current.text === snapshot.text &&
          latest.current.status === snapshot.status
        )
          latest.current.dirty = false;
        try {
          if (latest.current.dirty)
            localStorage.setItem(recoveryKey, JSON.stringify(latest.current));
          else localStorage.removeItem(recoveryKey);
        } catch {
          /* Preserve the server result. */
        }
        if (mounted.current) {
          setSaved(`Saved · revision ${result.reference.revision}`);
          setError("");
          onUpdate();
        }
      } catch (e) {
        if (mounted.current) {
          setError(String(e));
          setSaved("Save failed — local text retained");
          void api<Recording>(`/recordings/${recording.id}`)
            .then((value) => {
              if (mounted.current) setServerReference(value.reference);
            })
            .catch(() => {});
        }
      }
    });
    return chain.current;
  }, [recording.id, onUpdate]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      void flush();
    };
  }, [flush]);
  useEffect(() => {
    const listener = (event: BeforeUnloadEvent) => {
      if (latest.current.dirty) {
        event.preventDefault();
      }
    };
    window.addEventListener("beforeunload", listener);
    return () => window.removeEventListener("beforeunload", listener);
  }, []);
  const change = (value: string) => {
    setText(value);
    setStatus("draft");
    setSaved("Unsaved changes");
    latest.current = {
      ...latest.current,
      text: value,
      status: "draft",
      dirty: true,
    };
    try {
      localStorage.setItem(recoveryKey, JSON.stringify(latest.current));
    } catch {
      /* beforeunload still warns about unsaved edits */
    }
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => void flush(), 650);
  };
  const verify = async () => {
    latest.current.status = status === "verified" ? "draft" : "verified";
    latest.current.dirty = true;
    setStatus(latest.current.status);
    await flush();
  };
  return (
    <section className="ground-truth">
      <div className="section-label">
        <span>GROUND TRUTH</span>
        <Badge tone={status === "verified" ? "success" : "neutral"}>
          {status === "verified" ? (
            <>
              <CheckCheck size={12} /> Verified reference
            </>
          ) : (
            "Draft reference"
          )}
        </Badge>
      </div>
      <p className="help">
        Transcribe what you hear. Model predictions stay out of this editor.
      </p>
      <textarea
        aria-label="Ground-truth transcript"
        dir="auto"
        value={text}
        onChange={(e) => change(e.target.value)}
        onBlur={() => void flush()}
        placeholder="Play your recording and write the exact transcript…"
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === "s") {
            e.preventDefault();
            void flush();
          }
        }}
      />
      <div className="editor-footer">
        <span className="small muted" aria-live="polite">
          {saved}
        </span>
        <button
          className="text-button"
          onClick={async () =>
            setHistory(
              await api<Reference[]>(
                `/recordings/${recording.id}/reference/history`,
              ),
            )
          }
        >
          <History size={14} /> Version history
        </button>
      </div>
      <ErrorMessage error={error} />
      {error && (
        <button className="text-button" onClick={() => void flush()}>
          Retry saving retained draft
        </button>
      )}
      {error &&
        serverReference &&
        serverReference.revision !== latest.current.revision && (
          <div className="notice warning">
            <div>
              <strong>
                Current server revision {serverReference.revision}
              </strong>
              <p dir="auto">{serverReference.text}</p>
              <div className="button-row">
                <button
                  className="text-button"
                  onClick={() => {
                    latest.current = { ...serverReference, dirty: false };
                    setText(serverReference.text);
                    setStatus(serverReference.status);
                    setError("");
                    setSaved(`Saved · revision ${serverReference.revision}`);
                    localStorage.removeItem(recoveryKey);
                  }}
                >
                  Use server reference
                </button>
                <button
                  className="text-button"
                  onClick={() => {
                    latest.current.revision = serverReference.revision;
                    latest.current.status = "draft";
                    latest.current.dirty = true;
                    setStatus("draft");
                    void flush();
                  }}
                >
                  Save my text as a new draft
                </button>
              </div>
            </div>
          </div>
        )}
      <button
        className={
          status === "verified" ? "button secondary full" : "button full"
        }
        disabled={!!error || saved === "Saving…"}
        onClick={() => void verify()}
      >
        <Check size={15} />
        {status === "verified" ? "Return to draft" : "Mark verified"}
      </button>
      <Modal
        open={history !== null}
        onOpenChange={(open) => {
          if (!open) setHistory(null);
        }}
        title="Ground-truth version history"
        closeLabel="Close history"
      >
        {history?.length ? (
          history.map((r) => (
            <article key={r.revision} className="history-entry">
              <strong>Revision {r.revision}</strong> <Badge>{r.status}</Badge>
              <time>
                {r.created_at && new Date(r.created_at).toLocaleString()}
              </time>
              <p dir="auto">{r.text || "(Empty transcript)"}</p>
            </article>
          ))
        ) : (
          <p>No saved revisions yet.</p>
        )}
      </Modal>
    </section>
  );
}

export function RecordingInspector({
  recording,
  onUpdate,
  onClose,
}: {
  recording: Recording;
  onUpdate: () => void;
  onClose?: () => void;
}) {
  const [language, setLanguage] = useState(recording.language);
  const [tags, setTags] = useState(recording.tags.join(", "));
  const [error, setError] = useState("");
  const [labelStatus, setLabelStatus] = useState("");
  return (
    <aside className="inspector">
      <header className="inspector-header">
        <div>
          <span className="eyebrow">RECORDING INSPECTOR</span>
          <h2 title={recording.name}>{recording.name}</h2>
        </div>
        {onClose && (
          <button
            className="icon-button"
            aria-label="Close inspector"
            onClick={onClose}
          >
            <X size={17} />
          </button>
        )}
      </header>
      <div className="inspector-scroll">
        <AudioPlayer recording={recording} />
        <GroundTruth
          key={recording.id}
          recording={recording}
          onUpdate={onUpdate}
        />
        <section className="label-editor">
          <div className="section-label">LABELS & CONDITIONS</div>
          <label>
            Language
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              {LANGUAGES.map(([code, label]) => (
                <option key={code} value={code}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Tags
            <span className="help">Comma-separated. Create any category.</span>
            <input
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="Accented, Technical, Quiet speech"
            />
          </label>
          <div className="split">
            <button
              className="button secondary small-button"
              onClick={async () => {
                try {
                  await api(`/recordings/${recording.id}`, {
                    method: "PATCH",
                    body: jsonBody({ language, tags: tags.split(",") }),
                  });
                  onUpdate();
                  setLabelStatus("Labels saved");
                  setError("");
                } catch (e) {
                  setError(String(e));
                }
              }}
            >
              Save labels
            </button>
            <span className="small muted">{labelStatus}</span>
          </div>
        </section>
        <section>
          <div className="section-label">AUDIO PROVENANCE</div>
          <dl className="metadata">
            <dt>Source format</dt>
            <dd>{recording.source_format.split(",")[0].toUpperCase()}</dd>
            <dt>Original audio</dt>
            <dd>
              {recording.sample_rate.toLocaleString()} Hz · {recording.channels}{" "}
              ch
            </dd>
            <dt>Original size</dt>
            <dd>{size(recording.size_bytes)}</dd>
            <dt>Canonical input</dt>
            <dd>16 kHz · mono · PCM16 WAV</dd>
            <dt>Silence observation</dt>
            <dd>
              {(recording.diagnostics.silence_fraction * 100).toFixed(1)}%
            </dd>
            <dt>Potential clipping</dt>
            <dd>
              {(recording.diagnostics.clipping_fraction * 100).toFixed(3)}%
            </dd>
          </dl>
          <p className="help">
            Silence and clipping are sample-level diagnostics. No audio
            enhancement or VAD applied.
          </p>
          <details>
            <summary>File hashes</summary>
            <p className="hash">Original: {recording.source_sha256}</p>
            <p className="hash">Canonical: {recording.canonical.sha256}</p>
          </details>
          <a
            className="text-button download"
            href={`/api/v1/recordings/${recording.id}/audio?original=true`}
          >
            Download retained original
          </a>
        </section>
        <ErrorMessage error={error} />
      </div>
    </aside>
  );
}

export default function Library({
  notify,
}: {
  notify: (message: string) => void;
}) {
  const resource = useResource<Recording[]>("/recordings", []);
  const [query, setQuery] = useState("");
  const [language, setLanguage] = useState("");
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [selection, setSelection] = useState<Record<string, boolean>>({});
  const [sorting, setSorting] = useState<SortingState>([]);
  const [dragging, setDragging] = useState(false);
  const [importing, setImporting] = useState<{
    done: number;
    total: number;
    name: string;
  } | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [batch, setBatch] = useState(false);
  const [batchTags, setBatchTags] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const refresh = useCallback(() => {
    void resource.reload();
  }, [resource.reload]);
  const filtered = useMemo(
    () =>
      resource.data.filter(
        (r) =>
          (!query ||
            `${r.name} ${r.tags.join(" ")}`
              .toLowerCase()
              .includes(query.toLowerCase())) &&
          (!language || r.language === language) &&
          (!status || r.reference.status === status),
      ),
    [resource.data, query, language, status],
  );
  const columns = useMemo<ColumnDef<Recording>[]>(
    () => [
      {
        id: "select",
        header: ({ table }) => (
          <input
            aria-label="Select all visible recordings"
            type="checkbox"
            checked={table.getIsAllRowsSelected()}
            onChange={table.getToggleAllRowsSelectedHandler()}
          />
        ),
        cell: ({ row }) => (
          <input
            aria-label={`Select ${row.original.name}`}
            type="checkbox"
            checked={row.getIsSelected()}
            onChange={row.getToggleSelectedHandler()}
          />
        ),
      },
      {
        accessorKey: "name",
        header: "Recording",
        cell: ({ row }) => (
          <button
            className="recording-name"
            aria-label={`Open ${row.original.name}`}
            onClick={() => setSelected(row.original.id)}
          >
            <span className="file-icon">
              <FileAudio size={17} />
            </span>
            <span>
              <strong>{row.original.name}</strong>
              <small>
                {row.original.tags.slice(0, 2).join(" · ") ||
                  "No conditions labeled"}
              </small>
            </span>
          </button>
        ),
      },
      {
        accessorKey: "duration",
        header: "Duration",
        cell: (info) => (
          <span className="mono">{duration(info.getValue<number>())}</span>
        ),
      },
      {
        accessorKey: "language",
        header: "Language",
        cell: (info) => (
          <span className="language-code">{info.getValue<string>()}</span>
        ),
      },
      {
        id: "reference",
        accessorFn: (r) => r.reference.status,
        header: "Ground truth",
        cell: ({ row }) =>
          row.original.reference.status === "verified" ? (
            <Badge tone="success">
              <CheckCheck size={12} /> Verified
            </Badge>
          ) : (
            <Badge>
              {row.original.reference.revision ? "Draft" : "Not started"}
            </Badge>
          ),
      },
      {
        accessorKey: "benchmark_count",
        header: "Results",
        cell: (info) => (
          <span className="mono muted">{info.getValue<number>() || "—"}</span>
        ),
      },
    ],
    [],
  );
  const table = useReactTable({
    data: filtered,
    columns,
    state: { sorting, rowSelection: selection },
    onSortingChange: setSorting,
    onRowSelectionChange: setSelection,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    enableRowSelection: true,
  });
  const importFiles = async (files: FileList | File[]) => {
    if (importing) return;
    const list = Array.from(files);
    const failures: string[] = [];
    for (let i = 0; i < list.length; i++) {
      const file = list[i];
      setImporting({ done: i, total: list.length, name: file.name });
      try {
        const form = new FormData();
        form.append("file", file);
        await api("/recordings", { method: "POST", body: form });
      } catch (e) {
        failures.push(`${file.name}: ${e}`);
      }
    }
    setErrors(failures);
    setImporting(null);
    await resource.reload();
    notify(
      `${list.length - failures.length} recording${list.length === 1 ? "" : "s"} imported${failures.length ? ` · ${failures.length} need attention` : ""}`,
    );
  };
  const active = resource.data.find((r) => r.id === selected);
  const verified = resource.data.filter(
    (r) => r.reference.status === "verified",
  ).length;
  return (
    <div
      className="workspace library"
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node))
          setDragging(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        void importFiles(e.dataTransfer.files);
      }}
    >
      <div className="page-header">
        <div>
          <div className="breadcrumb">
            DATASET <span>/</span> YOUR RECORDINGS
          </div>
          <h1>Recording library</h1>
          <p>Your voice. Your reference. A reproducible starting point.</p>
        </div>
        <button
          className="button"
          onClick={() => input.current?.click()}
          disabled={!!importing}
        >
          <Plus size={17} /> Import recordings
        </button>
        <input
          ref={input}
          type="file"
          multiple
          accept="audio/*,.m4a,.caf,.aiff,.flac"
          hidden
          onChange={(e) => {
            if (e.target.files) void importFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>
      <div className="dataset-strip">
        <span>
          <FileAudio size={15} />
          <strong>{resource.data.length}</strong> recordings
        </span>
        <span>
          <Clock3 size={15} />
          <strong>
            {duration(resource.data.reduce((s, r) => s + r.duration, 0))}
          </strong>{" "}
          total audio
        </span>
        <span>
          <CheckCheck size={15} />
          <strong>{verified}</strong> verified{" "}
          <i className="progress-track">
            <i
              style={{
                width: `${(verified / Math.max(1, resource.data.length)) * 100}%`,
              }}
            />
          </i>
        </span>
        <span className="strip-note">
          Originals retained · lossless preprocessing
        </span>
      </div>
      {importing && (
        <div className="import-progress" role="status">
          <Upload size={16} />
          <span>
            Preparing {importing.done + 1} of {importing.total} ·{" "}
            {importing.name}
          </span>
          <progress value={importing.done} max={importing.total} />
        </div>
      )}
      <ErrorMessage error={resource.error} />
      {errors.length > 0 && (
        <details className="import-errors" open>
          <summary>{errors.length} import issues</summary>
          {errors.map((e, i) => (
            <p key={i}>{e}</p>
          ))}
        </details>
      )}
      <div className={`library-body ${active ? "with-inspector" : ""}`}>
        <div className="library-main">
          <div className="toolbar">
            <label className="search">
              <Search size={16} />
              <input
                aria-label="Search recordings"
                placeholder="Search recordings or tags…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              <kbd>⌘ K</kbd>
            </label>
            <select
              aria-label="Filter language"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              <option value="">All languages</option>
              {LANGUAGES.map(([code, label]) => (
                <option key={code} value={code}>
                  {label}
                </option>
              ))}
            </select>
            <select
              aria-label="Filter ground truth"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="">All references</option>
              <option value="draft">Draft</option>
              <option value="verified">Verified</option>
            </select>
          </div>
          {Object.values(selection).some(Boolean) && (
            <div className="batch-bar">
              <span>
                {Object.values(selection).filter(Boolean).length} selected
              </span>
              <button className="text-button" onClick={() => setBatch(true)}>
                Add tags
              </button>
              <button className="text-button" onClick={() => setSelection({})}>
                Clear selection
              </button>
            </div>
          )}
          {resource.loading ? (
            <div className="loading">Loading local library…</div>
          ) : filtered.length ? (
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  {table.getHeaderGroups().map((group) => (
                    <tr key={group.id}>
                      {group.headers.map((h) => (
                        <th key={h.id}>
                          {h.column.getCanSort() ? (
                            <button
                              className="sort-button"
                              onClick={h.column.getToggleSortingHandler()}
                            >
                              {flexRender(
                                h.column.columnDef.header,
                                h.getContext(),
                              )}
                              <ArrowDownUp size={11} />
                            </button>
                          ) : (
                            flexRender(
                              h.column.columnDef.header,
                              h.getContext(),
                            )
                          )}
                        </th>
                      ))}
                    </tr>
                  ))}
                </thead>
                <tbody>
                  {table.getRowModel().rows.map((row) => (
                    <tr
                      key={row.id}
                      className={row.id === selected ? "selected" : ""}
                    >
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
          ) : resource.data.length ? (
            <Empty icon={Search} title="No recordings match">
              Adjust the language, reference or search filters.
            </Empty>
          ) : (
            <Empty
              icon={Inbox}
              title="Build a dataset that sounds like you"
              action={
                <button
                  className="button secondary"
                  onClick={() => input.current?.click()}
                >
                  <Upload size={16} /> Choose audio files
                </button>
              }
            >
              Drop your Voice Memos here, or choose files.
              <br />
              M4A, WAV, MP3, FLAC, AAC, CAF and AIFF.
              <span className="empty-footnote">
                Private by default. Audio stays on this computer.
              </span>
            </Empty>
          )}
          <div className="table-footer">
            <span>
              {filtered.length} recordings{" "}
              {query || language || status ? "match filters" : "in library"}
            </span>
            <span>Canonical audio: 16 kHz mono WAV</span>
          </div>
        </div>
        {active && (
          <RecordingInspector
            key={active.id}
            recording={active}
            onUpdate={refresh}
            onClose={() => setSelected(null)}
          />
        )}
      </div>
      {dragging && (
        <div className="drop-overlay">
          <Upload size={38} />
          <h2>Drop recordings to import</h2>
          <p>Original files are always preserved.</p>
        </div>
      )}
      <Modal
        open={batch}
        onOpenChange={setBatch}
        title="Label selected recordings"
      >
        <label>
          Tags to add
          <input
            value={batchTags}
            onChange={(e) => setBatchTags(e.target.value)}
            placeholder="Technical, Accented"
          />
        </label>
        <button
          className="button"
          onClick={async () => {
            try {
              for (const r of resource.data.filter((r) => selection[r.id]))
                await api(`/recordings/${r.id}`, {
                  method: "PATCH",
                  body: jsonBody({
                    language: r.language,
                    tags: [...r.tags, ...batchTags.split(",")],
                  }),
                });
              setBatch(false);
              await resource.reload();
              notify("Tags added");
            } catch (e) {
              setErrors([String(e)]);
            }
          }}
        >
          Apply tags
        </button>
      </Modal>
    </div>
  );
}
