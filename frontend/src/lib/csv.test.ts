import { describe, it, expect } from 'vitest';
import { toCsv } from './csv';

describe('toCsv', () => {
  it('emits a header and one row per record', () => {
    const csv = toCsv([{ zip: '90001', score: 88 }, { zip: '90210', score: 12 }]);
    expect(csv).toBe('zip,score\n90001,88\n90210,12');
  });

  it('quotes fields containing commas, quotes, or newlines', () => {
    const csv = toCsv([{ name: 'Los Angeles, CA', note: 'a "quote"' }]);
    expect(csv).toBe('name,note\n"Los Angeles, CA","a ""quote"""');
  });

  it('honors an explicit column order and renders null as empty', () => {
    const csv = toCsv([{ a: 1, b: null }], ['b', 'a']);
    expect(csv).toBe('b,a\n,1');
  });

  it('returns empty string for no rows', () => {
    expect(toCsv([])).toBe('');
  });
});
