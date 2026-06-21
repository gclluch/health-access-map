import { useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

// Instant hover tooltip. The native `title` attribute has a ~1s browser-imposed
// delay that can't be configured; this shows immediately. Renders into a body
// portal (fixed position) so it is never clipped by the scrollable detail panel,
// and right-anchors so it never runs off-screen past the right-side panel.
export default function Tip({
  tip,
  children,
  className,
}: {
  tip: string;
  children: ReactNode;
  className?: string;
}) {
  const [box, setBox] = useState<{ right: number; top: number } | null>(null);
  return (
    <div
      className={className}
      onMouseEnter={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        setBox({ right: globalThis.innerWidth - r.right, top: r.top });
      }}
      onMouseLeave={() => setBox(null)}
    >
      {children}
      {box &&
        createPortal(
          <div
            style={{
              position: 'fixed',
              right: box.right,
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
