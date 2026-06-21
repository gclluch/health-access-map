import { useStore } from '../store';
import { STATE_NAMES } from '../lib/types';

// State quick-jump (§13.2): reach a workable zoom in one action; also filters the
// rankings. Plus "Use my area" geolocation.
export default function TopControls() {
  const { availableStates, stateFilter, locating } = useStore();
  const jumpToState = useStore((s) => s.jumpToState);
  const locateMe = useStore((s) => s.locateMe);

  return (
    <div className="flex items-center gap-1.5">
      <select
        value={stateFilter ?? ''}
        onChange={(e) => jumpToState(e.target.value || null)}
        aria-label="Jump to a state"
        className="text-[12px] bg-surface/90 border border-hairline rounded px-2 py-1.5 text-ink outline-none focus:border-accent cursor-pointer max-w-[150px]"
      >
        <option value="">All United States</option>
        {availableStates.map((s) => (
          <option key={s} value={s}>
            {STATE_NAMES[s] ?? s}
          </option>
        ))}
      </select>
      <button
        onClick={locateMe}
        disabled={locating}
        aria-label="Find my area"
        title="Find my area"
        className="text-[12px] bg-surface/90 border border-hairline rounded px-2 py-1.5 text-graphite hover:text-accent hover:border-accent disabled:opacity-50"
      >
        {locating ? '…' : '◉ My area'}
      </button>
    </div>
  );
}
