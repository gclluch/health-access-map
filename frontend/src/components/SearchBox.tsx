import { useState } from 'react';
import { useStore } from '../store';

// Search is the fastest path in (§13.2): a valid 5-digit ZIP flies to + selects.
export default function SearchBox() {
  const metrics = useStore((s) => s.metrics);
  const select = useStore((s) => s.select);
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const z = value.trim();
    if (!/^\d{5}$/.test(z)) {
      setError('Enter a 5-digit ZIP');
      return;
    }
    if (!metrics.has(z)) {
      setError(`No ZIP matches ${z}`);
      return;
    }
    setError(null);
    select(z, { fly: true });
  };

  return (
    <form onSubmit={submit} className="relative">
      <input
        className="num w-[150px] max-[520px]:w-[118px] bg-surface/90 border border-hairline rounded px-2.5 py-1.5 text-[13px] text-ink outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 max-[520px]:min-h-[40px]"
        placeholder="Search ZIP"
        inputMode="numeric"
        maxLength={5}
        value={value}
        aria-label="Search by ZIP code"
        onChange={(e) => {
          setValue(e.target.value.replace(/\D/g, ''));
          setError(null);
        }}
      />
      {error && (
        <div className="absolute top-full mt-1 left-0 text-[11px] text-accent bg-surface border border-hairline rounded px-2 py-1 whitespace-nowrap shadow-sm">
          {error}
        </div>
      )}
    </form>
  );
}
