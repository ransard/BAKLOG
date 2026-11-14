/** Dashboard drill-down resets library filters including custom lists. */
import { beforeEach, describe, expect, it } from 'vitest';
import { dashResetLibraryFiltersExceptDedup } from '../js/dashboard-drilldown.js';
import { state } from '../js/state.js';

describe('dashResetLibraryFiltersExceptDedup', () => {
  beforeEach(() => {
    state.sessionPrefs.search = 'foo';
    state.sessionPrefs.minHours = 10;
    state.sessionPrefs.maxHours = 20;
    state.prefs.customListFilter = 'my-list';
    state.prefs.genreFilters = ['RPG'];
  });

  it('clears custom list filter along with other drill resets', () => {
    dashResetLibraryFiltersExceptDedup();
    expect(state.sessionPrefs.search).toBe('');
    expect(state.sessionPrefs.minHours).toBe(0);
    expect(state.sessionPrefs.maxHours).toBe(200);
    expect(state.prefs.customListFilter).toBeNull();
    expect(state.prefs.genreFilters).toEqual([]);
  });
});
