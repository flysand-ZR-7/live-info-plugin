import crypto from 'node:crypto';
import * as cheerio from 'cheerio';
import { config } from '../config.js';
import type { SearchRequest, SearchResultItem } from '../types.js';

interface CacheEntry {
  expiresAt: number;
  items: SearchResultItem[];
}

const searchCache = new Map<string, CacheEntry>();

function makeCacheKey(req: SearchRequest): string {
  const raw = `${req.query.toLowerCase().trim()}|${req.max_results}|${req.language}|${req.time_range || ''}|${req.category || ''}|${req.engine || ''}`;
  return crypto.createHash('sha256').update(raw).digest('hex');
}

function normalizeUrl(rawUrl: string): string {
  try {
    const u = new URL(rawUrl.trim());
    return `${u.protocol}//${u.host}${u.pathname.replace(/\/+$/, '')}${u.search}`;
  } catch {
    return rawUrl.trim();
  }
}

export function deduplicateResults(items: SearchResultItem[], maxResults: number): SearchResultItem[] {
  const seen = new Set<string>();
  const deduped: SearchResultItem[] = [];

  for (const item of items) {
    const norm = normalizeUrl(item.url);
    if (!seen.has(norm)) {
      seen.add(norm);
      deduped.push(item);
      if (deduped.length >= maxResults) break;
    }
  }

  return deduped;
}

export async function queryAhmiaDirect(query: string, maxResults: number = 8): Promise<SearchResultItem[]> {
  try {
    const url = new URL('https://ahmia.fi/search/');
    url.searchParams.set('q', query);

    const res = await fetch(url.toString(), {
      headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) LiveInfoPlugin/1.0' },
      signal: AbortSignal.timeout(10000),
    });

    if (!res.ok) return [];

    const html = await res.text();
    const $ = cheerio.load(html);
    const items: SearchResultItem[] = [];

    $('li.result').each((_, el) => {
      let rawHref = $(el).find('h4 a').attr('href') || '';
      const title = $(el).find('h4 a').text().trim();
      const snippet = $(el).find('p').text().trim();

      if (rawHref.includes('redirect_url=')) {
        rawHref = rawHref.split('redirect_url=').pop() || rawHref;
      }

      if (rawHref && title) {
        items.push({
          title,
          url: rawHref.trim(),
          snippet,
          engine: 'ahmia',
        });
      }
    });

    return items.slice(0, maxResults);
  } catch (err) {
    console.warn('[Ahmia Direct Search Error]', err);
    return [];
  }
}

async function querySearXNG(
  query: string,
  language: string,
  timeRange?: string,
  categories?: string,
  engine?: string,
): Promise<SearchResultItem[]> {
  const url = new URL(`${config.searxngUrl}/search`);
  url.searchParams.set('q', query);
  url.searchParams.set('format', 'json');
  url.searchParams.set('language', language);
  if (timeRange) url.searchParams.set('time_range', timeRange);
  if (categories) url.searchParams.set('categories', categories);
  if (engine) url.searchParams.set('engines', engine);

  const res = await fetch(url.toString(), {
    headers: { 'User-Agent': 'LiveInfoPlugin/1.0' },
    signal: AbortSignal.timeout(8000),
  });

  if (!res.ok) {
    throw new Error(`SearXNG returned HTTP ${res.status}`);
  }

  const data: any = await res.json();
  const rawResults = data?.results || [];

  const items: SearchResultItem[] = [];
  for (const r of rawResults) {
    if (r.url && r.title) {
      items.push({
        title: String(r.title).trim(),
        url: String(r.url).trim(),
        snippet: String(r.content || r.snippet || '').trim(),
        engine: String(r.engine || 'searxng'),
      });
    }
  }

  return items;
}

export async function executeSearch(
  req: SearchRequest,
  useCache: boolean = true,
): Promise<{ results: SearchResultItem[]; cached: boolean }> {
  const cacheKey = makeCacheKey(req);
  const now = Date.now();

  if (useCache && searchCache.has(cacheKey)) {
    const entry = searchCache.get(cacheKey)!;
    if (now < entry.expiresAt) {
      return { results: entry.items, cached: true };
    }
    searchCache.delete(cacheKey);
  }

  const isDarkweb = req.category === 'darkweb' || req.engine === 'ahmia' || req.query.toLowerCase().includes('.onion');
  const targetCategory = isDarkweb && !req.category ? 'darkweb' : req.category;
  const targetEngine = isDarkweb && !req.engine ? 'ahmia' : req.engine;

  let rawItems: SearchResultItem[] = [];

  // Attempt 1: SearXNG
  try {
    rawItems = await querySearXNG(req.query, req.language, req.time_range, targetCategory, targetEngine);
  } catch (err: any) {
    console.warn(`[SearXNG Attempt 1 Failed for '${req.query}']: ${err.message}`);
  }

  // Attempt 2: SearXNG Retry
  if (rawItems.length === 0) {
    await new Promise((r) => setTimeout(r, 400));
    try {
      rawItems = await querySearXNG(req.query, req.language, req.time_range, targetCategory, targetEngine);
    } catch (err: any) {
      console.warn(`[SearXNG Attempt 2 Failed]: ${err.message}`);
    }
  }

  // Attempt 3: If darkweb requested, fallback to direct Ahmia indexer
  if (rawItems.length === 0 && isDarkweb) {
    rawItems = await queryAhmiaDirect(req.query, req.max_results);
  }

  const finalItems = deduplicateResults(rawItems, req.max_results);

  if (useCache && finalItems.length > 0) {
    searchCache.set(cacheKey, {
      expiresAt: now + config.cacheTtlSeconds * 1000,
      items: finalItems,
    });
  }

  return { results: finalItems, cached: false };
}
