/** Choosing what to run, and running it.
 *
 *  The scenario is presented as what a visitor will see, with the backend's exact specification one
 *  disclosure away. Controls that only make sense mid-run (injecting a concept change) appear only
 *  while a run is in progress, so an idle screen stays quiet. */

import type { Lifecycle, Preset, Profile } from "../lib/api";
import { pct, samples } from "../lib/format";
import { scenarioCopy } from "../lib/scenarios";
import { ExplainButton } from "./Explain";
import { TechnicalDetails } from "./ui";

type Props = {
  presets: Record<string, Preset>;
  preset: string;
  onPreset: (value: string) => void;
  profiles: Record<string, Profile>;
  profile: string;
  onProfile: (value: string) => void;
  variants: number[];
  injectVariant: number;
  onInjectVariant: (value: number) => void;
  flip: number | null;
  active: boolean;
  lifecycle: Lifecycle;
  sample: number;
  total: number;
  seed: number | null;
  busy: boolean;
  demo: boolean;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  onInject: () => void;
  onDemo: () => void;
};

export default function RunControlBar(props: Props) {
  const { active, lifecycle, busy } = props;
  const paused = lifecycle === "paused";
  const chosen = props.presets[props.preset];
  const copy = scenarioCopy(props.preset, chosen?.name);

  return (
    <div className="panel">
      <div className="panel-body row wrap" style={{ gap: 18, alignItems: "flex-start" }}>
        <label className="field scenario-pick">
          Scenario
          <select value={props.preset} onChange={(event) => props.onPreset(event.target.value)} disabled={active} style={{ maxWidth: "100%" }}>
            {Object.entries(props.presets).map(([key, preset]) => (
              <option key={key} value={key}>
                {scenarioCopy(key, preset.name).title}
              </option>
            ))}
          </select>
          {copy.said && <span className="scenario-said">{copy.said}</span>}
        </label>

        <label className="field">
          Resource profile
          <select value={props.profile} onChange={(event) => props.onProfile(event.target.value)} disabled={active}>
            {Object.entries(props.profiles).map(([key, profile]) => (
              <option key={key} value={key}>
                {profile.label}
                {profile.placeholder ? " (placeholder budgets)" : ""}
              </option>
            ))}
          </select>
        </label>

        <div className="spacer" />

        <div className="row" style={{ gap: 8, paddingTop: 18 }}>
          {!active ? (
            <button type="button" className="btn primary" onClick={props.onStart} disabled={busy}>
              ▶ Start run
            </button>
          ) : (
            <>
              {paused ? (
                <button type="button" className="btn" onClick={props.onResume}>
                  ▶ Resume
                </button>
              ) : (
                <button type="button" className="btn" onClick={props.onPause}>
                  ⏸ Pause
                </button>
              )}
              <button type="button" className="btn danger" onClick={props.onStop}>
                ■ Stop
              </button>
            </>
          )}
          <button type="button" className="btn" onClick={props.onDemo} aria-pressed={props.demo}>
            {props.demo ? "Demo mode on" : "Guided demo"}
          </button>
        </div>
      </div>

      {active && (
        <div className="panel-body row wrap secondary" style={{ gap: 12, borderTop: "1px solid var(--border)", paddingTop: 12 }}>
          <span className="small muted">Inject a concept change now:</span>
          <select
            value={props.injectVariant}
            onChange={(event) => props.onInjectVariant(Number(event.target.value))}
            aria-label="Concept to switch to"
          >
            {props.variants.map((variant) => (
              <option key={variant} value={variant}>
                concept {variant}
              </option>
            ))}
          </select>
          <button type="button" className="btn small" onClick={props.onInject} disabled={busy}>
            ⚡ Inject drift
          </button>
          {props.flip != null && (
            <span className="small muted row" style={{ gap: 4 }}>
              {pct(props.flip, 1)} of labels would change <ExplainButton id="flip" />
            </span>
          )}
        </div>
      )}

      <div className="panel-body" style={{ paddingTop: 0 }}>
        <TechnicalDetails summary="What this scenario runs">
          {chosen?.description && <p className="small">{chosen.description}</p>}
          {copy.watch && (
            <p className="small">
              <strong>What to watch for.</strong> {copy.watch}
            </p>
          )}
          <p className="tiny muted" style={{ margin: 0 }}>
            Preset <span className="mono">{props.preset}</span>
            {chosen?.name ? ` — “${chosen.name}”` : ""}
            {props.seed != null ? ` · seed ${props.seed}` : ""}
            {props.total ? ` · ${samples(props.total)} samples` : ""}. The settings are fixed by the scenario so that
            every run of it stays comparable; edit the preset file to vary them.
          </p>
        </TechnicalDetails>
      </div>
    </div>
  );
}
