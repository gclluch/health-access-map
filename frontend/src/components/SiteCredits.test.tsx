import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import SiteCredits from './SiteCredits';

// This was a role="dialog" with no focus trap, which promises assistive tech an Escape key and a
// trap that never existed. It is a disclosure now, and the aria wiring is the whole difference.
describe('SiteCredits', () => {
  it('is a disclosure, not a dialog', () => {
    render(<SiteCredits />);

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByRole('button', { name: /Sources/ }).getAttribute('aria-expanded')).toBe('false');
  });

  it('toggles the panel it declares it controls', () => {
    render(<SiteCredits />);
    const toggle = screen.getByRole('button', { name: /Sources/ });
    expect(document.getElementById(toggle.getAttribute('aria-controls')!)).toBeNull();

    fireEvent.click(toggle);

    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    const panel = document.getElementById(toggle.getAttribute('aria-controls')!);
    expect(panel).not.toBeNull();
    expect(panel!.textContent).toContain('CDC PLACES');

    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
  });

  it('keeps the screening-tool disclaimer with the sources', () => {
    render(<SiteCredits />);
    fireEvent.click(screen.getByRole('button', { name: /Sources/ }));

    // The phrase sits in a <strong>, so read the paragraph that carries the rest of the sentence.
    expect(screen.getByText(/relative screening tool/).closest('p')!.textContent)
      .toContain('not medical advice');
  });
});
