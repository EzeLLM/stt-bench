import { useEffect, useState } from "react";
import {
  AudioLines,
  BookOpen,
  ChartNoAxesCombined,
  Check,
  ChevronRight,
  DatabaseBackup,
  FlaskConical,
  FolderClosed,
  Headphones,
  Moon,
  Smartphone,
  Sun,
} from "lucide-react";
import { api, useResource } from "./api";
import Library from "./Library";
import Experiments from "./Experiments";
import Review from "./Review";
import Compare from "./Compare";
import Devices from "./Devices";
import Registry from "./Registry";

const links = [
  { id: "library", title: "Library", icon: FolderClosed },
  { id: "experiments", title: "Experiments", icon: FlaskConical },
  { id: "review", title: "Review", icon: Headphones },
  { id: "compare", title: "Compare", icon: ChartNoAxesCombined },
  { id: "devices", title: "Devices", icon: Smartphone },
];
export default function App() {
  const [page, setPage] = useState(window.location.hash.slice(1) || "library");
  const [dark, setDark] = useState(
    localStorage.getItem("stt-lab-theme") === "dark",
  );
  const [message, setMessage] = useState("");
  const [backingUp, setBackingUp] = useState(false);
  const health = useResource<{ status: string }>("/health", { status: "" });
  useEffect(() => {
    const listener = () => setPage(window.location.hash.slice(1) || "library");
    window.addEventListener("hashchange", listener);
    return () => window.removeEventListener("hashchange", listener);
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("stt-lab-theme", dark ? "dark" : "light");
  }, [dark]);
  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(() => setMessage(""), 5500);
    return () => clearTimeout(timer);
  }, [message]);
  useEffect(() => {
    const handle = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        window.location.hash = "library";
        setTimeout(
          () =>
            document
              .querySelector<HTMLInputElement>(
                '[aria-label="Search recordings"]',
              )
              ?.focus(),
          50,
        );
      }
    };
    window.addEventListener("keydown", handle);
    return () => window.removeEventListener("keydown", handle);
  }, []);
  const notify = (text: string) => setMessage(text);
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a href="#library" className="brand">
          <span className="brand-symbol">
            <AudioLines size={23} />
          </span>
          <span>
            STT <strong>Benchmark Lab</strong>
            <small>PERSONAL RESEARCH WORKBENCH</small>
          </span>
        </a>
        <div className="project-switch">
          <span className="project-dot" />
          <div>
            <strong>My speech research</strong>
            <small>Local workspace</small>
          </div>
          <ChevronRight size={14} />
        </div>
        <span className="nav-label">WORKSPACES</span>
        <nav>
          {links.map(({ id, title, icon: Icon }) => (
            <a
              key={id}
              href={`#${id}`}
              aria-label={title}
              aria-current={page === id ? "page" : undefined}
              className={page === id ? "active" : ""}
            >
              <Icon size={17} />
              <span>{title}</span>
              {id === "review" && <span className="nav-hint">BLIND</span>}
            </a>
          ))}
        </nav>
        <div className="sidebar-divider" />
        <span className="nav-label">RESEARCH RESOURCES</span>
        <nav>
          <a
            href="#registry"
            aria-label="Model registry"
            className={page === "registry" ? "active" : ""}
          >
            <BookOpen size={17} />
            <span>Model registry</span>
          </a>
          <button
            disabled={backingUp}
            onClick={async () => {
              setBackingUp(true);
              try {
                const result = await api<{ id: string; note: string }>(
                  "/backup",
                  { method: "POST" },
                );
                const a = document.createElement("a");
                a.href = `/api/v1/backup/${result.id}`;
                a.download = "";
                a.click();
                notify("Consistent database and audio backup created");
              } catch (e) {
                notify(String(e));
              } finally {
                setBackingUp(false);
              }
            }}
          >
            <DatabaseBackup size={17} />
            <span>{backingUp ? "Creating backup…" : "Back up dataset"}</span>
          </button>
        </nav>
        <div className="sidebar-bottom">
          <div className="privacy-note">
            <span className={`status-dot ${health.error ? "offline" : ""}`} />
            <strong>
              {health.error
                ? "Coordinator unavailable"
                : health.data.status === "ok"
                  ? "Local coordinator online"
                  : "Connecting…"}
            </strong>
            <p>
              Private recordings stay here.
              <br />
              No analytics. No audio uploads.
            </p>
          </div>
          <div className="sidebar-footer">
            <span>v0.1 · Research build</span>
            <button
              className="icon-button"
              aria-label="Toggle appearance"
              onClick={() => setDark(!dark)}
            >
              {dark ? <Sun size={16} /> : <Moon size={16} />}
            </button>
          </div>
        </div>
      </aside>
      <div className="app-content">
        <header className="app-topbar">
          <span>
            <span className="status-dot" /> LOCAL WORKSPACE
          </span>
          <span className="topbar-detail">
            Source → checkpoint → runtime → evidence
          </span>
        </header>
        {page === "library" ? (
          <Library notify={notify} />
        ) : page === "experiments" ? (
          <Experiments notify={notify} />
        ) : page === "review" ? (
          <Review />
        ) : page === "compare" ? (
          <Compare />
        ) : page === "devices" ? (
          <Devices />
        ) : page === "registry" ? (
          <Registry notify={notify} />
        ) : (
          <Library notify={notify} />
        )}
      </div>
      {message && (
        <div role="status" className="toast">
          <Check size={16} />
          {message}
        </div>
      )}
    </div>
  );
}
