import { useStore } from '../store';
import { STATE_NAMES } from '../lib/types';
import Caret from './Caret';

// State quick-jump (§13.2): reach a workable zoom in one action; also filters the
// rankings. Plus "Use my area" geolocation.
export default function TopControls() {
  const { availableStates, stateFilter, locating } = useStore();
  const jumpToState = useStore((s) => s.jumpToState);
  const locateMe = useStore((s) => s.locateMe);

  return (
    <div className="flex items-center gap-1.5 max-[520px]:gap-1">
      <div className="relative max-w-[150px] max-[520px]:max-w-[140px]">
        <select
          value={stateFilter ?? ''}
          onChange={(e) => jumpToState(e.target.value || null)}
          aria-label="Jump to a state"
          title="The default map opens on the continental U.S.; Alaska, Hawaii, and Puerto Rico are available here."
          className="w-full appearance-none text-[12px] bg-surface/90 border border-hairline rounded pl-2 pr-6 py-1.5 text-ink outline-none focus:border-accent cursor-pointer max-[520px]:pr-5"
        >
          <option value="">CONUS overview</option>
          {availableStates.map((s) => (
            <option key={s} value={s}>
              {STATE_NAMES[s] ?? s}
            </option>
          ))}
        </select>
        <Caret
          open
          size={12}
          className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-graphite"
        />
      </div>
      <button
        onClick={locateMe}
        disabled={locating}
        aria-label="Find my area"
        title="Find my area"
        className="text-[12px] bg-surface/90 border border-hairline rounded px-2 py-1.5 text-graphite hover:text-accent hover:border-accent disabled:opacity-50 max-[520px]:px-1.5"
      >
        {locating ? '…' : '◉ My area'}
      </button>
    </div>
  );
}
