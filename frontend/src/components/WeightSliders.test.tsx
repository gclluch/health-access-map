import { describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import WeightSliders from './WeightSliders';
import { useStore } from '../store';
import { COMPOSITE_METRIC, COMPOSITE_MULT_METRIC, DEFAULT_WEIGHTS, PRESETS } from '../lib/types';
import { seedStore } from '../test/harness';

// The sliders are the project's headline feature and its most-hedged one. Two behaviours carry
// that: the commit is debounced so a drag does not recompute 33k polygons per frame, and moving
// a weight snaps the view back to a lens the weight can actually change.
describe('WeightSliders', () => {
  const drag = (label: string, value: number) =>
    fireEvent.change(screen.getByLabelText(label), { target: { value: String(value) } });

  it('debounces the commit to the store, so a drag coalesces into one recompute', () => {
    vi.useFakeTimers();
    try {
      seedStore([]);
      render(<WeightSliders />);

      drag('Health need weight', 60);
      drag('Health need weight', 70);
      drag('Health need weight', 80);
      expect(useStore.getState().weights.health_need).toBe(DEFAULT_WEIGHTS.health_need);

      act(() => void vi.advanceTimersByTime(100));

      expect(useStore.getState().weights.health_need).toBe(80);
    } finally {
      vi.useRealTimers();
    }
  });

  it('shows the moved value immediately, before that commit lands', () => {
    vi.useFakeTimers();
    try {
      seedStore([]);
      render(<WeightSliders />);

      drag('Barriers to care weight', 90);

      expect((screen.getByLabelText('Barriers to care weight') as HTMLInputElement).value).toBe('90');
    } finally {
      vi.useRealTimers();
    }
  });

  it('snaps a non-weighted lens back to the composite so the change is visible', () => {
    seedStore([], { metric: 'insurance_pctile' });
    render(<WeightSliders />);

    drag('Health need weight', 60);

    expect(useStore.getState().metric).toBe(COMPOSITE_METRIC);
  });

  it('leaves a user already on the geometric composite where they are', () => {
    seedStore([], { metric: COMPOSITE_MULT_METRIC });
    render(<WeightSliders />);

    drag('Health need weight', 60);

    expect(useStore.getState().metric).toBe(COMPOSITE_MULT_METRIC);
  });

  it('applies a preset wholesale', () => {
    seedStore([]);
    render(<WeightSliders />);
    const [name] = Object.keys(PRESETS);

    fireEvent.click(screen.getByRole('button', { name }));

    expect(useStore.getState().weights).toEqual(PRESETS[name]);
  });

  it('offers reset only once the weights are off default', () => {
    seedStore([]);
    render(<WeightSliders />);
    const reset = screen.getByRole('button', { name: /Reset to default/ }) as HTMLButtonElement;
    expect(reset.disabled).toBe(true);

    act(() => useStore.getState().setWeights({ health_need: 90 }));
    expect(reset.disabled).toBe(false);

    fireEvent.click(reset);
    expect(useStore.getState().weights).toEqual(DEFAULT_WEIGHTS);
  });
});
