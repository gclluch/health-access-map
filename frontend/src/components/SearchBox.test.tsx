import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import SearchBox from './SearchBox';
import { useStore } from '../store';
import { makeMetric, seedStore } from '../test/harness';

// Search is the keyboard route into the data, so its failure modes have to be announced rather
// than silent - a wrong ZIP that does nothing is indistinguishable from a broken app.
describe('SearchBox', () => {
  const type = (v: string) => fireEvent.change(screen.getByLabelText('Search by ZIP code'), { target: { value: v } });
  const submit = () => fireEvent.submit(screen.getByLabelText('Search by ZIP code').closest('form')!);

  it('selects a ZIP that exists', () => {
    seedStore([makeMetric({ zcta5: '90001' })]);
    render(<SearchBox />);

    type('90001');
    submit();

    expect(useStore.getState().selectedZcta).toBe('90001');
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('explains a short entry instead of selecting nothing', () => {
    seedStore([makeMetric({ zcta5: '90001' })]);
    render(<SearchBox />);

    type('900');
    submit();

    expect(screen.getByRole('alert').textContent).toContain('5-digit');
    expect(useStore.getState().selectedZcta).toBeNull();
  });

  it('names the ZIP it could not find', () => {
    seedStore([makeMetric({ zcta5: '90001' })]);
    render(<SearchBox />);

    type('99999');
    submit();

    expect(screen.getByRole('alert').textContent).toContain('99999');
    expect(useStore.getState().selectedZcta).toBeNull();
  });

  it('strips non-digits and wires the error to the input for assistive tech', () => {
    seedStore([makeMetric({ zcta5: '90001' })]);
    render(<SearchBox />);
    const input = screen.getByLabelText('Search by ZIP code') as HTMLInputElement;

    type('9a0b0');
    expect(input.value).toBe('900');

    submit();
    expect(input.getAttribute('aria-invalid')).toBe('true');
    expect(input.getAttribute('aria-describedby')).toBe(screen.getByRole('alert').id);
  });

  it('clears a stale error as soon as the user edits', () => {
    seedStore([makeMetric({ zcta5: '90001' })]);
    render(<SearchBox />);

    type('900');
    submit();
    expect(screen.getByRole('alert')).toBeTruthy();

    type('9001');
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
