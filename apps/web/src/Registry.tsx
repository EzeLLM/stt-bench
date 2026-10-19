import { useRef, useState } from "react";
import { ArrowUpRight, BookOpen, FileCheck2, Upload } from "lucide-react";
import { api, jsonBody, size, useResource, type Model } from "./api";
import { Badge, ErrorMessage, Modal } from "./ui";

export default function Registry({ notify }: { notify: (s: string) => void }) {
  const models = useResource<{ installed: Model[]; candidates: Model[] }>(
    "/models",
    { installed: [], candidates: [] },
  );
  const [selected, setSelected] = useState<Model | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className="workspace">
      <div className="page-header">
        <div>
          <div className="breadcrumb">
            PROVENANCE <span>/</span> CHECKPOINTS, NOT LABELS
          </div>
          <h1>Model registry</h1>
          <p>
            Research candidates are distinct from installed, hash-verified
            implementations.
          </p>
        </div>
        <button
          className="button"
          disabled={busy}
          onClick={() => input.current?.click()}
        >
          <Upload size={16} /> Register manifest
        </button>
        <input
          ref={input}
          hidden
          type="file"
          accept="application/json,.json"
          onChange={async (e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            setBusy(true);
            try {
              const value = JSON.parse(await file.text());
              await api("/models", { method: "POST", body: jsonBody(value) });
              await models.reload();
              setError("");
              notify("Checkpoint manifest and file checksums verified");
            } catch (e) {
              setError(String(e));
            } finally {
              setBusy(false);
            }
          }}
        />
      </div>
      <ErrorMessage error={error || models.error} />
      <div className="notice">
        <FileCheck2 size={19} />
        <div>
          <strong>Trust is a chain of evidence</strong>
          <p>
            Stage checkpoint files under the lab's data directory, then register
            a complete manifest containing the exact revision, license,
            component precisions and every file's SHA-256. Registration verifies
            local bytes; it does not certify reference parity or iPhone
            compatibility. See <code>docs/models.md</code>.
          </p>
        </div>
      </div>
      <div className="section-heading">
        <h2>Registered checkpoints</h2>
        <Badge>{models.data.installed.length}</Badge>
      </div>
      {models.data.installed.length ? (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Implementation</th>
                <th>Runtime</th>
                <th>Revision</th>
                <th>Size</th>
                <th>Parity</th>
              </tr>
            </thead>
            <tbody>
              {models.data.installed.map((m) => (
                <tr key={m.id}>
                  <td>
                    <button
                      className="model-cell"
                      onClick={() => setSelected(m)}
                    >
                      <strong>{m.family}</strong>
                      <small>{m.variant}</small>
                    </button>
                  </td>
                  <td>{m.runtime}</td>
                  <td className="mono">{m.revision?.slice(0, 8)}</td>
                  <td className="mono">{size(m.size_bytes || 0)}</td>
                  <td>
                    <Badge tone="warning">{m.parity}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="help registry-empty">
          No model assets installed. Candidate entries below cannot be
          benchmarked yet.
        </p>
      )}
      <div className="section-heading">
        <h2>Compatibility investigation</h2>
        <span className="small muted">
          Five selected families · variants kept distinct
        </span>
      </div>
      <div className="table-scroll">
        <table className="data-table registry-table">
          <thead>
            <tr>
              <th>Family / candidate</th>
              <th>Implementation path</th>
              <th>Language scope</th>
              <th>Evidence state</th>
            </tr>
          </thead>
          <tbody>
            {models.data.candidates.map((m) => (
              <tr key={m.id}>
                <td>
                  <button className="model-cell" onClick={() => setSelected(m)}>
                    <strong>{m.family}</strong>
                    <small>{m.variant}</small>
                  </button>
                </td>
                <td>
                  <span>{m.backend}</span>
                  <a
                    href={`https://huggingface.co/${m.repository}`}
                    target="_blank"
                    rel="noreferrer"
                    className="source-link"
                  >
                    {m.repository}
                    <ArrowUpRight size={12} />
                  </a>
                </td>
                <td>
                  <div className="language-list">
                    {["en", "tr", "ar", "de"].map((l) => (
                      <span
                        key={l}
                        className={
                          m.languages.includes(l) ? "supported" : "unsupported"
                        }
                        title={
                          m.languages.includes(l)
                            ? "Upstream language support; artifact unverified"
                            : "Unsupported"
                        }
                      >
                        {l.toUpperCase()}
                      </span>
                    ))}
                  </div>
                </td>
                <td>
                  <Badge tone={m.status === "blocked" ? "warning" : ""}>
                    {m.status}
                  </Badge>
                  <span className="small muted block">
                    Parity not validated
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="methodology">
        Exact Hugging Face revisions and licenses were inspected on 19 October
        2026. Checkpoint bytes, runtime compatibility and reference parity
        remain separate validation gates. Published comparisons are evidence
        from the publisher, not measurements on your recordings.
      </p>
      <Modal
        open={!!selected}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
        title={selected?.family || "Checkpoint"}
      >
        {selected && (
          <>
            <h3>{selected.variant}</h3>
            <dl className="metadata">
              <dt>Repository</dt>
              <dd>
                <a
                  href={`https://huggingface.co/${selected.repository}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  {selected.repository}
                </a>
              </dd>
              <dt>Exact revision</dt>
              <dd className="hash">{selected.revision || "Not verified"}</dd>
              <dt>License</dt>
              <dd>{selected.license || "Not verified for this artifact"}</dd>
              <dt>Backend</dt>
              <dd>{selected.runtime || selected.backend}</dd>
              <dt>Parity</dt>
              <dd>{selected.parity}</dd>
              <dt>iPhone</dt>
              <dd>{selected.ios || "Not physically validated"}</dd>
              <dt>Languages</dt>
              <dd>{selected.languages.join(", ")}</dd>
            </dl>
            {selected.components?.map((c) => (
              <p key={c.name}>
                <strong>{c.name}</strong>: {c.precision} · {c.quantization}
              </p>
            ))}
            {selected.note && (
              <div className="notice warning">{selected.note}</div>
            )}
          </>
        )}
      </Modal>
    </div>
  );
}
