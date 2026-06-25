// Single disclosure signifier used everywhere a section expands/collapses or a
// <select> opens. NN/g's accordion-icon study found the caret/chevron is the only
// common glyph that reliably reads as "expands in place" (nngroup.com/articles/
// accordion-icons). Rendered as an SVG stroke in `currentColor` so contrast is
// governed by the parent's text color (keep it >=3:1 per WCAG 1.4.11 non-text),
// and it rotates from ">" (collapsed) to "v" (expanded) for clear state feedback.
export default function Caret({
  open,
  className = '',
  size = 14,
}: {
  open: boolean;
  className?: string;
  size?: number;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
      className={`shrink-0 transition-transform duration-150 ${open ? 'rotate-90' : ''} ${className}`}
    >
      <path
        d="M6 3.5 L10.5 8 L6 12.5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
