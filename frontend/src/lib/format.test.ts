import { describe, it, expect } from 'vitest';
import { fmtScore, ordinal, fmtRatePct, fmtInt, fmtMoney, severity } from './format';

describe('fmtScore', () => {
  it('rounds to a whole number and dashes on null/NaN', () => {
    expect(fmtScore(62.4)).toBe('62');
    expect(fmtScore(null)).toBe('--');
    expect(fmtScore(NaN)).toBe('--');
  });
});

describe('ordinal', () => {
  it('uses correct suffixes including the 11-13 exception', () => {
    expect(ordinal(1)).toBe('1st');
    expect(ordinal(2)).toBe('2nd');
    expect(ordinal(3)).toBe('3rd');
    expect(ordinal(4)).toBe('4th');
    expect(ordinal(11)).toBe('11th');
    expect(ordinal(12)).toBe('12th');
    expect(ordinal(13)).toBe('13th');
    expect(ordinal(21)).toBe('21st');
    expect(ordinal(112)).toBe('112th');
    expect(ordinal(null)).toBe('--');
  });
});

describe('severity', () => {
  it('maps the access-gap percentile to a band (higher = worse), null on no data', () => {
    expect(severity(95)?.label).toBe('Severe gap');
    expect(severity(80)?.label).toBe('Severe gap');
    expect(severity(70)?.label).toBe('High gap');
    expect(severity(50)?.label).toBe('Moderate gap');
    expect(severity(25)?.label).toBe('Below average');
    expect(severity(5)?.label).toBe('Low gap');
    expect(severity(null)).toBeNull();
    expect(severity(NaN)).toBeNull();
  });
});

describe('rate/int/money', () => {
  it('formats fractions as percents and rounds counts', () => {
    expect(fmtRatePct(0.123)).toBe('12.3%');
    expect(fmtInt(12345)).toBe('12,345');
    expect(fmtMoney(54000)).toBe('$54,000');
    expect(fmtRatePct(null)).toBe('--');
  });
});
