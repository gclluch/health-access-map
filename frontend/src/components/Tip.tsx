import { useId, useState, type KeyboardEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

// Instant help popover. Hover still works for mouse users, while focus/tap opens
// the same explanation for keyboard and touch. Renders into a body portal so it
// is never clipped by scrollable panels.
export default function Tip({
  tip,
  children,
  className,
  focusable = true,
}: {
  tip: string;
  children: ReactNode;
  className?: string;
  focusable?: boolean;
}) {
  const id = useId();
  const [box, setBox] = useState<{ left: number; top: number } | null>(null);
  const [pinned, setPinned] = useState(false);

  const position = (el: HTMLElement) => {
    const r = el.getBoundingClientRect();
    const width = Math.min(300, globalThis.innerWidth - 24);
    const left = Math.max(12, Math.min(r.left, globalThis.innerWidth - width - 12));
    setBox({ left, top: r.top });
  };

  const close = () => {
    setPinned(false);
    setBox(null);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') close();
    if ((e.key === 'Enter' || e.key === ' ') && focusable) {
      e.preventDefault();
      position(e.currentTarget);
      setPinned((v) => !v);
    }
  };

  return (
    <div
      className={className}
      tabIndex={focusable ? 0 : undefined}
      aria-describedby={box ? id : undefined}
      onMouseEnter={(e) => {
        position(e.currentTarget);
      }}
      onMouseLeave={() => {
        if (!pinned) setBox(null);
      }}
      onFocus={(e) => {
        if (focusable) position(e.currentTarget);
      }}
      onBlur={close}
      onClick={(e) => {
        if (!focusable) return;
        position(e.currentTarget);
        setPinned((v) => !v);
      }}
      onKeyDown={onKeyDown}
    >
      {children}
      {box &&
        createPortal(
          <div
            id={id}
            role="tooltip"
            style={{
              position: 'fixed',
              left: box.left,
              top: box.top - 6,
              transform: 'translateY(-100%)',
              maxWidth: 300,
            }}
            className="z-[1000] pointer-events-none rounded bg-ink px-2.5 py-1.5 text-[11px] leading-snug text-paper shadow-lg"
          >
            {tip}
          </div>,
          document.body,
        )}
    </div>
  );
}
