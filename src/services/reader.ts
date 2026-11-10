import crypto from 'node:crypto';
import { parseHTML } from 'linkedom';
import { Readability } from '@mozilla/readability';
import { config } from '../config.js';
import { validateUrl, SSRFProtectionError } from '../security.js';
import { completeText } from './llm.js';
import type { ReaderRequest, ReaderResponse } from '../types.js';

interface ReaderCacheEntry {
  expiresAt: number;
  data: ReaderResponse;
}

const readerCache = new Map<string, ReaderCacheEntry>();

function makeCacheKey(req: ReaderRequest): string {
  const raw = `${req.url.trim()}|${req.max_chars}|${req.summarize}`;
  return crypto.createHash('sha256').update(raw).digest('hex');
}

/**
 * Safely fetches a web page's HTML:
 * - Validates initial URL with SSRF protection.
 * - Follows up to 3 redirects, re-validating SSRF on every hop.
 * - Enforces streaming size cap (default 5MB).
 */
export async function fetchPageContent(targetUrl: string, maxRedirects: number = 3): Promise<{ finalUrl: string; html: string }> {
  let currentUrl = await validateUrl(targetUrl);
  let redirectsRemaining = maxRedirects;

  while (true) {
    const res = await fetch(currentUrl, {
      redirect: 'manual',
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) LiveInfoPlugin/1.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      },
      signal: AbortSignal.timeout(config.readerTimeoutMs),
    });

    // Check redirects
    if (res.status >= 300 && res.status < 400) {
      if (redirectsRemaining <= 0) {
        throw new SSRFProtectionError('Too many redirects encountered.');
      }
      const location = res.headers.get('location');
      if (!location) {
        throw new Error('Redirect status received without Location header.');
      }
      const resolved = new URL(location, currentUrl).toString();
      currentUrl = await validateUrl(resolved); // Re-validate SSRF on redirect destination
      redirectsRemaining--;
      continue;
    }

    if (!res.ok) {
      throw new Error(`Upstream server returned HTTP ${res.status}`);
    }

    // Read response with size cap
    if (!res.body) {
      const text = await res.text();
      return { finalUrl: currentUrl, html: text.slice(0, config.readerMaxBytes) };
    }

    const reader = res.body.getReader();
    const chunks: Uint8Array[] = [];
    let receivedBytes = 0;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (value) {
        receivedBytes += value.length;
        if (receivedBytes > config.readerMaxBytes) {
          reader.cancel();
          break;
        }
        chunks.push(value);
      }
    }

    const totalBuffer = new Uint8Array(receivedBytes);
    let offset = 0;
    for (const chunk of chunks) {
      totalBuffer.set(chunk, offset);
      offset += chunk.length;
    }

    const html = new TextDecoder('utf-8').decode(totalBuffer);
    return { finalUrl: currentUrl, html };
  }
}

/**
 * Extracts clean readable text from HTML using Mozilla Readability.
 */
export function extractCleanArticle(html: string, url: string): { title: string | null; text: string } {
  try {
    const { document } = parseHTML(html);
    const reader = new Readability(document);
    const article = reader.parse();

    if (article && article.textContent && article.textContent.trim().length > 50) {
      const cleanText = article.textContent
        .replace(/[ \t]+/g, ' ')
        .replace(/\n\s*\n+/g, '\n\n')
        .trim();
      return { title: article.title || null, text: cleanText };
    }
  } catch (err) {
    console.warn('[Readability Parse Fallback]', err);
  }

  // Fallback: simple tag stripping
  const titleMatch = html.match(/<title[^>]*>(.*?)<\/title>/i);
  const title = titleMatch ? titleMatch[1].replace(/<[^>]+>/g, '').trim() : null;
  const stripped = html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  return { title, text: stripped };
}

export async function readUrl(req: ReaderRequest, useCache: boolean = true): Promise<ReaderResponse> {
  const cacheKey = makeCacheKey(req);
  const now = Date.now();

  if (useCache && readerCache.has(cacheKey)) {
    const entry = readerCache.get(cacheKey)!;
    if (now < entry.expiresAt) {
      return { ...entry.data, cached: true };
    }
    readerCache.delete(cacheKey);
  }

  const { finalUrl, html } = await fetchPageContent(req.url);
  const { title, text } = extractCleanArticle(html, finalUrl);

  const truncated = text.length > req.max_chars;
  const content = truncated ? text.slice(0, req.max_chars) : text;

  let summary: string | null = null;
  if (req.summarize && content.length > 100) {
    try {
      const prompt = `Summarize the following web page in 3 to 5 concise bullet points:\n\nTitle: ${title || 'Untitled'}\nURL: ${finalUrl}\n\nContent:\n${content.slice(0, 4000)}`;
      summary = await completeText({
        prompt,
        systemPrompt: 'You are a precise, objective web content summarizer. Be direct, clear, and factual.',
        maxTokens: 400,
      });
    } catch (err: any) {
      console.warn('[Reader Summarize Warning]', err.message);
    }
  }

  const result: ReaderResponse = {
    url: finalUrl,
    title,
    text: content,
    truncated,
    char_count: content.length,
    summary,
    cached: false,
  };

  if (useCache) {
    readerCache.set(cacheKey, {
      expiresAt: now + config.cacheTtlSeconds * 1000,
      data: result,
    });
  }

  return result;
}
