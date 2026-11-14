import { beforeEach, describe, expect, it } from 'vitest';
import { state } from '../js/state.js';
import { gameGenresCanonical } from '../js/genres.js';
import { coverageLabel, coverageTooltipLine, pendingForEnrich, refreshHintFor } from '../js/fetcher/source-meta.js';

describe('genre enrichment coverage', () => {
  beforeEach(() => {
    state.allGames = [
      { id: 10, store: 'steam', genres: ['Action'] },
      { id: 'new', store: 'gog', genres: [] },
      { id: 'miss', store: 'ea' },
      { id: 'empty', store: 'xbox' },
    ];
    state.itchGames = [
      { id: 'game', store: 'itch', genres: ['Windows', 'html', ' '] },
      { id: 'tool', store: 'itch', classification: 'tool' },
    ];
    state.libraryMeta = { genres: { by_key: {
      'ea:miss': false,
      'xbox:empty': { appid: 20, genres: [] },
    } } };
  });

  it('counts missing usable genres across stores and excludes non-game itch rows', () => {
    expect(pendingForEnrich('genres')).toEqual({ unchecked: 2, retry: 0, noMatch: 2 });
    expect(coverageLabel('genres')).toBe('20% · 2 new');
    expect(coverageTooltipLine('genres')).toContain('1 of 5 have genres. 2 still to try.');
    expect(refreshHintFor({ key: 'genres', supportsRefresh: true })).toContain('2 cached misses');
  });

  it('updates coverage after the enriched catalogs are loaded', () => {
    state.allGames.forEach(g => { g.genres = ['RPG']; });
    state.itchGames[0].genres = ['Puzzle'];
    expect(coverageLabel('genres')).toBe('100%');
    expect(pendingForEnrich('genres')).toEqual({ unchecked: 0, retry: 0, noMatch: 0 });
  });

  it('ignores blank or malformed genres consistently with the backfill', () => {
    expect(gameGenresCanonical({ genres: [null, '', ' ', 'Windows', ' Action ', 'Action'] })).toEqual(['Action']);
    expect(gameGenresCanonical({ genres: 'Action' })).toEqual([]);
  });

  it('explains cached misses when there is no new work', () => {
    state.allGames = state.allGames.filter(g => ['miss', 'empty'].includes(g.id));
    state.itchGames = [];
    expect(coverageLabel('genres')).toBe('0%');
    expect(coverageTooltipLine('genres')).toContain('no Steam match or genre data. Shift+click to retry.');
  });
});
