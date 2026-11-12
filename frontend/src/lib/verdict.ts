/** The plain result of a two-model replay: how often each was right over the whole run, and the
 *  difference in wrong predictions. Words follow the numbers; nothing is claimed below half a point. */

export type Verdict = {
  scored: number;
  learner: { right: number; wrong: number };
  frozen: { right: number; wrong: number };
  sentence: string;
};

export function verdict(learnerAccuracy: number | null | undefined, frozenAccuracy: number | null | undefined, scored: number, finished: boolean): Verdict | null {
  if (learnerAccuracy == null || frozenAccuracy == null || !(scored > 0)) return null;
  const wrong = (accuracy: number) => Math.round((1 - accuracy) * scored);
  const learner = { right: learnerAccuracy, wrong: wrong(learnerAccuracy) };
  const frozen = { right: frozenAccuracy, wrong: wrong(frozenAccuracy) };
  const gap = learnerAccuracy - frozenAccuracy;
  const rows = scored.toLocaleString();
  const soFar = finished ? "" : " so far";
  const sentence =
    Math.abs(gap) < 0.005
      ? `Both models scored about the same${soFar}: there is no clear difference on these ${rows} rows.`
      : gap > 0
        ? `The model that keeps learning made ${(frozen.wrong - learner.wrong).toLocaleString()} fewer wrong predictions${soFar} (${learner.wrong.toLocaleString()} against ${frozen.wrong.toLocaleString()}, out of ${rows} rows).`
        : `The model trained once made ${(learner.wrong - frozen.wrong).toLocaleString()} fewer wrong predictions${soFar} (${frozen.wrong.toLocaleString()} against ${learner.wrong.toLocaleString()}, out of ${rows} rows). Keeping on learning did not help on this run.`;
  return { scored, learner, frozen, sentence };
}
