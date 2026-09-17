/** Formatting helpers. Every value that is missing renders as an em dash, never as 0. */

export const DASH = "—";

export const num = (value: number | null | undefined, digits = 0): string =>
  value == null || Number.isNaN(value) ? DASH : value.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });

export const pct = (value: number | null | undefined, digits = 1): string =>
  value == null || Number.isNaN(value) ? DASH : `${(value * 100).toFixed(digits)} %`;

export const us = (value: number | null | undefined, digits = 1): string => (value == null ? DASH : `${value.toFixed(digits)} µs`);

export const ms = (value: number | null | undefined, digits = 1): string => (value == null ? DASH : `${value.toFixed(digits)} ms`);

export const kb = (value: number | null | undefined): string =>
  value == null ? DASH : value >= 1024 ? `${(value / 1024).toFixed(1)} MB` : `${value.toFixed(0)} KB`;

export const samples = (value: number | null | undefined): string => (value == null ? DASH : `${value.toLocaleString()}`);

export const signedPoints = (a: number | null | undefined, b: number | null | undefined, digits = 1): string => {
  if (a == null || b == null) return DASH;
  const delta = (b - a) * 100;
  return `${delta >= 0 ? "+" : ""}${delta.toFixed(digits)} pts`;
};

export const timeAgo = (iso: string): string => {
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
  if (seconds < 90) return "just now";
  const minutes = seconds / 60;
  if (minutes < 90) return `${Math.round(minutes)} min ago`;
  const hours = minutes / 60;
  if (hours < 36) return `${Math.round(hours)} h ago`;
  return `${Math.round(hours / 24)} d ago`;
};

export const METHOD_LABELS: Record<string, string> = {
  static: "Static (train-once)",
  incremental: "Incremental (no detection)",
  adaptive: "Adaptive pipeline",
  arf: "Adaptive Random Forest [20]",
  periodic: "Periodic retraining",
};

export const methodLabel = (method: string): string => METHOD_LABELS[method] ?? method;
