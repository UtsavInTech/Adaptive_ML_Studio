/** A small picture of how a change arrives: how much of each row follows the new behaviour, from
 *  left (earlier rows) to right (later rows). Low = old behaviour, high = new behaviour. */

import type { DriftKind } from "../lib/api";

const PATHS: Record<DriftKind | "none", string> = {
  // nothing is changed: the line stays on the old behaviour
  none: "M2 23 H78",
  // all at once
  abrupt: "M2 23 H34 V7 H78",
  // every row is old or new; new rows become more frequent
  gradual: "M2 23 H20 V7 H22 V23 H29 V7 H33 V23 H38 V7 H45 V23 H48 V7 H58 V23 H60 V7 H78",
  // every row moves a little further
  incremental: "M2 23 H22 L56 7 H78",
  // there and back again
  recurring: "M2 23 H18 V7 H34 V23 H50 V7 H66 V23 H78",
};

export default function DriftShape({ kind }: { kind: DriftKind | "none" }) {
  return (
    <svg className={`drift-shape ${kind}`} viewBox="0 0 80 30" width="80" height="30" aria-hidden="true">
      <path d="M2 23 H78" className="base" />
      <path d={PATHS[kind]} className="line" />
    </svg>
  );
}
