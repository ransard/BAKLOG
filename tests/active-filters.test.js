import { describe, it, expect, beforeEach } from 'vitest';
import { state } from '../js/state.js';
import { loadSessionPrefs } from '../js/prefs.js';
import { collectActiveFilters } from '../js/active-filters.js';

beforeEach(() => {
  state.activeView = 'library';
  state.allGames = [];
  state.sessionPrefs = loadSessionPrefs();
  state.prefs = {
    storeFilter: '',
    wishlistStoreFilter: '',
    releaseYearFilter: '',
    hltbBucket: null,
    genreFilters: [],
  };
});

describe('collectActiveFilters', () => {
  it('shows each active HLTB range bound independently', () => {
    state.sessionPrefs.minHours = 5.5;
    state.sessionPrefs.maxHours = 20;
    expect(collectActiveFilters()).toEqual(expect.arrayContaining([
      { kind: 'minHours', value: '5.5', label: 'HLTB ≥ 5.5h' },
      { kind: 'maxHours', value: '20', label: 'HLTB ≤ 20h' },
    ]));
    state.sessionPrefs.minHours = 0;
    state.sessionPrefs.maxHours = 200;
    expect(collectActiveFilters().filter(p => ['minHours', 'maxHours'].includes(p.kind))).toEqual([]);
  });

  it('omits dedup pill when library catalog is empty', () => {
    const pills = collectActiveFilters();
    expect(pills.some((p) => p.kind === 'dedup')).toBe(false);
  });

  it('includes dedup pill when library has games and dedup is on', () => {
    state.allGames = [{ store: 'steam', id: '1', name: 'Hades' }];
    const pills = collectActiveFilters();
    expect(pills.some((p) => p.kind === 'dedup')).toBe(true);
  });
});
