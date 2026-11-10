import * as cheerio from 'cheerio';
import { validateUrl, SSRFProtectionError } from '../security.js';
import { fetchPageContent, extractCleanArticle } from './reader.js';
import { completeText } from './llm.js';
import type { CrawledPageItem, CrawlRequest, CrawlResponse } from '../types.js';

const EXCLUDED_EXTENSIONS = [
  '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico',
  '.pdf', '.zip', '.tar', '.gz', '.7z', '.rar',
  '.exe', '.dmg', '.pkg', '.deb', '.rpm',
  '.mp3', '.mp4', '.wav', '.avi', '.mov', '.mkv',
  '.css', '.js', '.json', '.xml', '.woff', '.woff2', '.ttf',
];

export function extractChildLinks(html: string, baseUrl: string, allowedHost?: string): string[] {
  const $ = cheerio.load(html);
  const links: string[] = [];

  $('a[href]').each((_, el) => {
    const rawHref = $(el).attr('href')?.trim();
    if (!rawHref || rawHref.startsWith('#') || rawHref.startsWith('javascript:') || rawHref.startsWith('mailto:')) {
      return;
    }

    try {
      const resolved = new URL(rawHref, baseUrl);
      resolved.hash = ''; // remove anchor

      // Only http / https
      if (resolved.protocol !== 'http:' && resolved.protocol !== 'https:') return;

      // Check excluded extensions
      const pathLower = resolved.pathname.toLowerCase();
      if (EXCLUDED_EXTENSIONS.some((ext) => pathLower.endsWith(ext))) return;

      // Check domain boundary if specified
      if (allowedHost) {
        const host = resolved.hostname.toLowerCase();
        if (host !== allowedHost && !host.endsWith(`.${allowedHost}`)) {
          return;
        }
      }

      links.push(resolved.toString());
    } catch {}
  });

  return Array.from(new Set(links));
}

export async function crawlWebsite(req: CrawlRequest): Promise<CrawlResponse> {
  const rootValidated = await validateUrl(req.url);
  const rootUrlObj = new URL(rootValidated);
  const allowedHost = req.stay_on_domain ? rootUrlObj.hostname.toLowerCase() : undefined;

  const visited = new Set<string>();
  const queue: Array<{ url: string; depth: number }> = [{ url: rootValidated, depth: 1 }];
  const crawledPages: CrawledPageItem[] = [];
  let maxDepthReached = 1;

  while (queue.length > 0 && crawledPages.length < req.max_pages) {
    const current = queue.shift()!;
    const cleanUrl = current.url.split('#')[0];

    if (visited.has(cleanUrl)) continue;
    visited.add(cleanUrl);

    if (current.depth > maxDepthReached) {
      maxDepthReached = current.depth;
    }

    let html = '';
    let finalUrl = cleanUrl;
    try {
      const safeUrl = await validateUrl(cleanUrl);
      const res = await fetchPageContent(safeUrl);
      html = res.html;
      finalUrl = res.finalUrl;
    } catch (err: any) {
      console.warn(`[Crawler Skipped '${cleanUrl}']:`, err.message);
      continue;
    }

    const { title, text } = extractCleanArticle(html, finalUrl);
    const childLinks = extractChildLinks(html, finalUrl, allowedHost);
    const words = text.split(/\s+/).filter(Boolean).length;

    crawledPages.push({
      url: finalUrl,
      title,
      text: text.slice(0, 10000),
      depth: current.depth,
      word_count: words,
      child_links_count: childLinks.length,
    });

    if (current.depth < req.max_depth && crawledPages.length + queue.length < req.max_pages * 2) {
      for (const link of childLinks) {
        if (!visited.has(link)) {
          queue.push({ url: link, depth: current.depth + 1 });
        }
      }
    }
  }

  let knowledgeSummary: string | null = null;
  if (req.summarize && crawledPages.length > 0) {
    try {
      const snippets = crawledPages.slice(0, 6).map((p, i) => `[${i + 1}] ${p.title || p.url}\nURL: ${p.url}\nExcerpt: ${p.text.slice(0, 1200)}`).join('\n\n');
      const prompt = `Synthesize an executive knowledge summary of the concepts, architecture, and topics covered across these ${crawledPages.length} crawled pages from ${req.url}:\n\n${snippets}\n\nTask: Output a clear, structured summary with bullet points and source URL citations.`;

      knowledgeSummary = await completeText({
        prompt,
        systemPrompt: 'You are an expert technical documentation synthesizer. Be direct, clear, and structured.',
        maxTokens: 800,
      });
    } catch (err: any) {
      console.warn('[Crawler Summarize Warning]', err.message);
    }
  }

  return {
    root_url: req.url,
    total_pages_crawled: crawledPages.length,
    depth_reached: maxDepthReached,
    pages: crawledPages,
    knowledge_summary: knowledgeSummary,
  };
}
