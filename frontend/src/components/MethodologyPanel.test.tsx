import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import MethodologyPanel from './MethodologyPanel';
import { useStore } from '../store';
import { seedStore } from '../test/harness';

// This one really is a modal, so it owes assistive tech everything SiteCredits does not: a trap,
// an Escape key, and the focus put back where it came from.
describe('MethodologyPanel', () => {
  const open = () => {
    seedStore([], { showMethodology: true });
    return render(<MethodologyPanel />);
  };

  it('renders nothing while closed', () => {
    seedStore([], { showMethodology: false });
    const { container } = render(<MethodologyPanel />);

    expect(container.textContent).toBe('');
  });

  it('announces itself as a modal dialog with a name', () => {
    open();
    const dialog = screen.getByRole('dialog');

    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(document.getElementById(dialog.getAttribute('aria-labelledby')!)?.textContent)
      .toContain('How to read this');
  });

  it('moves focus to the close button on open', () => {
    open();

    expect(document.activeElement).toBe(screen.getByRole('button', { name: /close/i }));
  });

  it('closes on Escape', () => {
    open();

    fireEvent.keyDown(window, { key: 'Escape' });

    expect(useStore.getState().showMethodology).toBe(false);
  });

  it('wraps Tab from the last focusable back to the first, and Shift+Tab the other way', () => {
    open();
    const dialog = screen.getByRole('dialog');
    const focusables = dialog.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, summary, [tabindex]:not([tabindex="-1"])',
    );
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    expect(focusables.length).toBeGreaterThan(1);

    last.focus();
    fireEvent.keyDown(dialog, { key: 'Tab' });
    expect(document.activeElement).toBe(first);

    fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(last);
  });

  it('restores focus to the opener when it unmounts', () => {
    const opener = document.createElement('button');
    document.body.appendChild(opener);
    opener.focus();

    const { unmount } = open();
    expect(document.activeElement).not.toBe(opener);

    unmount();

    expect(document.activeElement).toBe(opener);
    opener.remove();
  });
});
