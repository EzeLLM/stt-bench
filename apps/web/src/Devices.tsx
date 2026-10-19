import { useState } from "react";
import {
  Copy,
  Link2,
  RefreshCw,
  ShieldCheck,
  Smartphone,
  Wifi,
} from "lucide-react";
import { api, useResource } from "./api";
import { Badge, Empty, ErrorMessage, Modal } from "./ui";

type Device = {
  id: string;
  name: string;
  details: Record<string, unknown>;
  last_seen: string;
};
export default function Devices() {
  const devices = useResource<Device[]>("/devices", []);
  const [pairing, setPairing] = useState<{
    token: string;
    instructions: string;
  } | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  return (
    <div className="workspace">
      <div className="page-header">
        <div>
          <div className="breadcrumb">
            HARDWARE <span>/</span> PHYSICAL DEVICE EVIDENCE
          </div>
          <h1>Devices & performance</h1>
          <p>
            The Mac coordinates. The iPhone runs the model. Measurements keep
            their context.
          </p>
        </div>
        <div className="button-row">
          <button
            className="button secondary"
            onClick={() => void devices.reload()}
          >
            <RefreshCw size={15} /> Refresh
          </button>
          <button
            className="button"
            onClick={async () => {
              try {
                setPairing(await api("/pairing"));
              } catch (e) {
                setError(String(e));
              }
            }}
          >
            <Link2 size={15} /> Pair iPhone
          </button>
        </div>
      </div>
      <ErrorMessage error={error || devices.error} />
      <div className="protocol-strip">
        <span>
          <ShieldCheck size={16} /> Local inference only
        </span>
        <span>
          <Wifi size={16} /> Trusted local Wi-Fi
        </span>
        <span>Offline execution after assets are cached</span>
      </div>
      {devices.data.length ? (
        <div className="devices-list">
          {devices.data.map((d) => (
            <article key={d.id} className="device-panel">
              <div className="device-title">
                <Smartphone size={30} />
                <div>
                  <h2>{d.name}</h2>
                  <p className="small muted">
                    Last seen {new Date(d.last_seen).toLocaleString()}
                  </p>
                </div>
                <Badge
                  tone={
                    Date.now() - Date.parse(d.last_seen) < 30000
                      ? "success"
                      : ""
                  }
                >
                  {Date.now() - Date.parse(d.last_seen) < 30000
                    ? "Recently observed"
                    : "Not recently observed"}
                </Badge>
              </div>
              <dl className="metadata">
                {Object.entries(d.details).map(([key, value]) => (
                  <div className="metadata-row" key={key}>
                    <dt>{key.replaceAll("_", " ")}</dt>
                    <dd>
                      {typeof value === "object"
                        ? JSON.stringify(value)
                        : String(value)}
                    </dd>
                  </div>
                ))}
              </dl>
              <p className="help">
                Pairing is not proof of inference or device compatibility. Batch
                results appear in Experiments and Compare after this device
                submits a validated measurement envelope.
              </p>
            </article>
          ))}
        </div>
      ) : (
        <Empty
          icon={Smartphone}
          title="Inference belongs on the iPhone"
          action={
            <button
              className="button secondary"
              onClick={async () => {
                try {
                  setPairing(await api("/pairing"));
                } catch (e) {
                  setError(String(e));
                }
              }}
            >
              <Link2 size={15} /> Show pairing instructions
            </button>
          }
        >
          No device has paired with this lab.
          <br />
          Install the native app from the repository, then connect over local
          Wi-Fi.
        </Empty>
      )}
      <div className="measurement-grid">
        <section>
          <span className="eyebrow">OBSERVED ON DEVICE</span>
          <h3>Latency, memory & thermal state</h3>
          <p>
            Monotonic timestamps separate model loading, warmups and inference.
            Memory and thermal state are observations with device, OS and
            runtime identities.
          </p>
        </section>
        <section>
          <span className="eyebrow">EXTERNAL PROFILING</span>
          <h3>Power needs a supported instrument</h3>
          <p>
            Use Apple's Instruments and retain the trace with its experiment.
            Battery percentage is an observation; it is never converted to
            joules per inference.
          </p>
        </section>
        <section>
          <span className="eyebrow">VALIDATION GATE</span>
          <h3>Physical iPhone required</h3>
          <p>
            This Linux build environment cannot compile Core ML or validate
            A-series behavior. Native components remain experimental until built
            and tested on your hardware.
          </p>
        </section>
      </div>
      <Modal
        open={!!pairing}
        onOpenChange={(open) => {
          if (!open) {
            setPairing(null);
            setCopied(false);
          }
        }}
        title="Pair a physical iPhone"
      >
        {pairing && (
          <>
            <ol className="pairing-steps">
              <li>
                Build and install <code>apps/ios</code> from a Mac with Xcode.
              </li>
              <li>
                On a trusted private LAN, start the coordinator with{" "}
                <code>--host 0.0.0.0 --port 8000</code>.
              </li>
              <li>
                Enter <code>http://YOUR-MAC-LAN-IP:8000</code> in the iPhone
                app.
              </li>
              <li>
                Enter this local pairing token. The app receives its own device
                credential.
              </li>
            </ol>
            <div className="pairing-token">
              <code>{pairing.token}</code>
              <button
                className="icon-button"
                aria-label="Copy pairing token"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(pairing.token);
                    setCopied(true);
                  } catch {
                    setError(
                      "Clipboard unavailable; select and copy the token manually.",
                    );
                  }
                }}
              >
                <Copy size={16} />
              </button>
            </div>
            {copied && <p className="help">Copied</p>}
            <p className="help">
              Pair only over a trusted LAN. Use TLS on untrusted networks. The
              lab stores device credentials locally and never includes them in
              exports.
            </p>
          </>
        )}
      </Modal>
    </div>
  );
}
