import { useCallback, useEffect, useState } from "react";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch("/api/v1" + path, {
    ...options,
    headers: {
      ...(options.body && !(options.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    let message = response.statusText;
    try {
      const value = (await response.json()).detail;
      message = typeof value === "string" ? value : JSON.stringify(value);
    } catch {
      /* HTTP error without JSON */
    }
    throw new ApiError(response.status, message);
  }
  return response.json();
}

export function useResource<T>(path: string, initial: T) {
  const [data, setData] = useState<T>(initial);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    try {
      setData(await api<T>(path));
      setError("");
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [path]);
  useEffect(() => {
    setLoading(true);
    void reload();
  }, [reload]);
  return { data, setData, error, loading, reload };
}

export type Reference = {
  revision: number;
  text: string;
  status: "draft" | "verified";
  created_at?: string;
};
export type Recording = {
  id: string;
  name: string;
  duration: number;
  language: string;
  tags: string[];
  reference: Reference;
  source_sha256: string;
  canonical: {
    sha256: string;
    sample_rate: number;
    channels: number;
    size_bytes: number;
  };
  waveform: number[];
  sample_rate: number;
  channels: number;
  source_format: string;
  size_bytes: number;
  benchmark_count: number;
  diagnostics: { silence_fraction: number; clipping_fraction: number };
};
export type Model = {
  id: string;
  family: string;
  variant: string;
  repository: string;
  runtime?: string;
  backend?: string;
  revision: string | null;
  status: string;
  parity: string;
  languages: string[];
  note?: string;
  ios?: string;
  license: string | null;
  size_bytes?: number;
  components?: { name: string; precision: string; quantization: string }[];
};
export type Experiment = {
  id: string;
  name: string;
  target: "mac" | "iphone";
  state: string;
  counts: Record<string, number>;
  job_count: number;
  created_at: string;
  finalized_at: string | null;
  settings: { language_mode: string; repetitions: number };
};
export type Edit = {
  kind: "equal" | "substitute" | "insert" | "delete";
  reference: string[];
  hypothesis: string[];
};
export type Score = {
  normalized: { word: Counts; character: Counts };
  strict: { word: Counts; character: Counts };
  alignment: Edit[];
  character_alignment: Edit[];
};
export type Counts = {
  rate: number | null;
  substitutions: number;
  deletions: number;
  insertions: number;
  reference_length: number;
};
export type Job = {
  id: string;
  recording_id: string;
  model_id: string;
  repetition: number;
  state: string;
  error: string | null;
  stale_reference: boolean;
  evaluation_reference?: {
    text: string;
    revision: number;
    version: string;
  } | null;
  snapshot: {
    recording: Recording & { asset_sha256: string };
    reference: Reference;
    model: Model;
    supported_language: boolean;
  };
  output: {
    id: string;
    text: string;
    measurements: {
      inference_seconds: number;
      load_seconds: number;
      runtime_version: string;
    };
  } | null;
  scores: Score | null;
  attempts: { id: string; state: string; error: string | null }[];
};
export type Rating = {
  faithfulness: number | null;
  readability: number | null;
  rank: number | null;
  comment: string;
  semantic_preservation?: number | null;
  proper_nouns?: number | null;
  technical_vocabulary?: number | null;
  hallucination?: boolean;
  missing_words?: boolean;
};
export type Review = {
  id: string;
  experiment_id: string;
  recording_id: string;
  locked: boolean;
  outputs: {
    id: string;
    text: string;
    model_id?: string;
    alignment: Edit[];
    character_alignment: Edit[];
  }[];
  ratings: Record<string, Rating>;
};
export const duration = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${Math.floor(seconds % 60)
    .toString()
    .padStart(2, "0")}`;
export const percent = (value: number | null | undefined) =>
  value == null ? "—" : `${(value * 100).toFixed(2)}%`;
export const size = (bytes: number) =>
  bytes > 1e9
    ? `${(bytes / 1e9).toFixed(2)} GB`
    : `${(bytes / 1e6).toFixed(1)} MB`;
export const jsonBody = (value: unknown) => JSON.stringify(value);
