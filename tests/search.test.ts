import { describe, it, expect, vi } from 'vitest';
import { deduplicateResults, queryAhmiaDirect } from '../src/services/search.js';
import type { SearchResultItem } from '../src/types.js';

describe('Search Service', () => {
  it('deduplicates results by normalized URL while preserving order', () => {
    const rawItems: SearchResultItem[] = [
      { title: 'Item 1', url: 'https://example.com/page/', snippet: 'first', engine: 'ddg' },
      { title: 'Item 1 Duplicate', url: 'https://example.com/page', snippet: 'dup', engine: 'bing' },
      { title: 'Item 2', url: 'https://example.com/page2', snippet: 'second', engine: 'brave' },
      { title: 'Item 3', url: 'https://other.com/doc', snippet: 'third', engine: 'wp' },
    ];

    const deduped = deduplicateResults(rawItems, 10);
    expect(deduped.length).toBe(3);
    expect(deduped[0].title).toBe('Item 1');
    expect(deduped[1].title).toBe('Item 2');
    expect(deduped[2].title).toBe('Item 3');
  });

  it('respects max_results cap during deduplication', () => {
    const rawItems: SearchResultItem[] = [
      { title: 'A', url: 'https://a.com', snippet: 'a', engine: 'ddg' },
      { title: 'B', url: 'https://b.com', snippet: 'b', engine: 'ddg' },
      { title: 'C', url: 'https://c.com', snippet: 'c', engine: 'ddg' },
    ];

    const deduped = deduplicateResults(rawItems, 2);
    expect(deduped.length).toBe(2);
  });
});
