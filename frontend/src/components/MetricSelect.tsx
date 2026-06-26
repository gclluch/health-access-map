import {
  ACCESS_RESID_METRIC,
  COMPOSITE_METRIC,
  COMPOSITE_MULT_METRIC,
  MODEL,
  OUTCOME_METRICS,
  WITHIN_STATE_METRIC,
} from '../lib/types';

type MetricSelectProps = {
  value: string;
  onChange: (metric: string) => void;
  ariaLabel: string;
  className: string;
  includeWithinState?: boolean;
};

export default function MetricSelect({
  value,
  onChange,
  ariaLabel,
  className,
  includeWithinState = false,
}: MetricSelectProps) {
  return (
    <select
      aria-label={ariaLabel}
      className={className}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value={COMPOSITE_METRIC}>Access gap (composite)</option>
      <option value={COMPOSITE_MULT_METRIC}>Access gap (coincidence lens)</option>
      <option value={ACCESS_RESID_METRIC}>Barriers to care, net of deprivation</option>
      {includeWithinState && <option value={WITHIN_STATE_METRIC}>Access gap (within-state rank)</option>}
      {MODEL.map((d) => (
        <optgroup key={d.key} label={d.label}>
          <option value={`${d.key}_pctile`}>{d.label} (overall)</option>
          {d.subs.map((s) => (
            <option key={s.key} value={`${s.key}_pctile`}>
              &nbsp;&nbsp;{s.label}
            </option>
          ))}
        </optgroup>
      ))}
      <optgroup label="Outcomes (not in the score)">
        {OUTCOME_METRICS.map((o) => (
          <option key={o.key} value={`${o.key}_pctile`}>
            {o.label}
          </option>
        ))}
      </optgroup>
    </select>
  );
}
