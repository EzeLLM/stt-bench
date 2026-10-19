import { useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import {
  AlertCircle,
  ChevronDown,
  Music2,
  Pause,
  Play,
  RotateCcw,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { duration, type Recording } from "./api";

export function Badge({
  children,
  tone = "",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function ErrorMessage({ error }: { error: string }) {
  return error ? (
    <div role="alert" className="error">
      <AlertCircle size={16} />
      {error}
    </div>
  ) : null;
}
export function Empty({
  icon: Icon = Music2,
  title,
  children,
  action,
}: {
  icon?: LucideIcon;
  title: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Icon size={25} strokeWidth={1.5} />
      </div>
      <h2>{title}</h2>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function Modal({
  open,
  onOpenChange,
  title,
  children,
  closeLabel = "Close dialog",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  children: React.ReactNode;
  closeLabel?: string;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay" />
        <Dialog.Content className="modal">
          <div className="modal-header">
            <Dialog.Title>{title}</Dialog.Title>
            <Dialog.Close className="icon-button" aria-label={closeLabel}>
              <X size={18} />
            </Dialog.Close>
          </div>
          <Dialog.Description className="sr-only">
            {title} for your local benchmark lab.
          </Dialog.Description>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function AudioPlayer({ recording }: { recording: Recording }) {
  const audio = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [speed, setSpeed] = useState("1");
  const seek = (value: number) => {
    if (audio.current) {
      audio.current.currentTime = value;
      setPosition(value);
    }
  };
  return (
    <div className="audio-player">
      <audio
        ref={audio}
        src={`/api/v1/recordings/${recording.id}/audio`}
        preload="metadata"
        onTimeUpdate={() => setPosition(audio.current?.currentTime || 0)}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
      />
      <div
        className="waveform"
        role="slider"
        aria-label="Audio position"
        aria-valuemin={0}
        aria-valuemax={recording.duration}
        aria-valuenow={position}
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight")
            seek(Math.min(recording.duration, position + 2));
          if (e.key === "ArrowLeft") seek(Math.max(0, position - 2));
          if (e.key === " ") {
            e.preventDefault();
            playing ? audio.current?.pause() : void audio.current?.play();
          }
        }}
        onClick={(e) => {
          const bounds = e.currentTarget.getBoundingClientRect();
          seek(((e.clientX - bounds.left) / bounds.width) * recording.duration);
        }}
      >
        <svg viewBox="0 0 800 72" preserveAspectRatio="none" aria-hidden="true">
          {recording.waveform.map((peak, index) => (
            <line
              key={index}
              x1={(index * 800) / recording.waveform.length}
              x2={(index * 800) / recording.waveform.length}
              y1={36 - Math.max(1, peak * 33)}
              y2={36 + Math.max(1, peak * 33)}
              className={
                index / recording.waveform.length <=
                position / recording.duration
                  ? "played"
                  : ""
              }
            />
          ))}
        </svg>
        <div
          className="playhead"
          style={{ left: `${(position / recording.duration) * 100}%` }}
        />
      </div>
      <div className="playback-controls">
        <button
          className="play-button"
          aria-label={playing ? "Pause audio" : "Play audio"}
          onClick={() =>
            playing ? audio.current?.pause() : void audio.current?.play()
          }
        >
          {playing ? <Pause size={16} /> : <Play size={16} />}
        </button>
        <button
          className="icon-button"
          aria-label="Replay last 3 seconds"
          onClick={() => seek(Math.max(0, position - 3))}
        >
          <RotateCcw size={15} />
        </button>
        <span className="mono">
          {duration(position)}{" "}
          <span className="muted">/ {duration(recording.duration)}</span>
        </span>
        <label className="speed">
          <span className="sr-only">Playback speed</span>
          <select
            value={speed}
            onChange={(e) => {
              setSpeed(e.target.value);
              if (audio.current)
                audio.current.playbackRate = Number(e.target.value);
            }}
          >
            {["0.5", "0.75", "1", "1.25", "1.5", "2"].map((value) => (
              <option key={value} value={value}>
                {value}×
              </option>
            ))}
          </select>
        </label>
        <span className="muted small">← → seek · space play</span>
      </div>
    </div>
  );
}
