import { serve } from '@hono/node-server';
import { Hono } from 'hono';
import { cors } from 'hono/cors';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { ZodError } from 'zod';

import { config } from './config.js';
import { SSRFProtectionError } from './security.js';
import { executeSearch } from './services/search.js';
import { getNews } from './services/news.js';
import { readUrl } from './services/reader.js';
import { crawlWebsite } from './services/crawler.js';
import { conductResearch } from './services/research.js';
import { verifyClaim } from './services/verify.js';
import {
  SearchRequestSchema,
  NewsRequestSchema,
  ReaderRequestSchema,
  CrawlRequestSchema,
  ResearchRequestSchema,
  FactVerificationRequestSchema,
} from './types.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, '..');
const staticDir = path.join(rootDir, 'static');

const app = new Hono();

// Middleware: CORS
app.use('*', cors());

// Middleware: Sliding Window Rate Limiter
const ipTimestamps = new Map<string, number[]>();
app.use('*', async (c, next) => {
  // Exclude static assets and health check from rate limiting
  if (c.req.path === '/' || c.req.path === '/health' || c.req.path.startsWith('/static')) {
    return next();
  }

  const clientIp = c.req.header('x-forwarded-for')?.split(',')[0].trim() || 'local';
  const now = Date.now();
  const windowMs = 60000;

  let timestamps = ipTimestamps.get(clientIp) || [];
  timestamps = timestamps.filter((t) => now - t < windowMs);

  if (timestamps.length >= config.rateLimitPerMinute) {
    return c.json(
      { error: 'RateLimitExceeded', detail: `Maximum ${config.rateLimitPerMinute} requests per minute permitted.` },
      429,
    );
  }

  timestamps.push(now);
  ipTimestamps.set(clientIp, timestamps);
  await next();
});

// Error handling
app.onError((err, c) => {
  if (err instanceof SSRFProtectionError) {
    return c.json({ error: 'SecurityViolation', detail: err.message }, 400);
  }
  if (err instanceof ZodError) {
    return c.json({ error: 'ValidationError', detail: err.errors }, 400);
  }
  console.error('[Unhandled Error]', err);
  return c.json({ error: 'InternalServerError', detail: err.message }, 500);
});

// ==============================================================================
// 1. Dashboard & System Endpoints
// ==============================================================================

app.get('/', (c) => {
  const indexPath = path.join(staticDir, 'index.html');
  if (fs.existsSync(indexPath)) {
    const html = fs.readFileSync(indexPath, 'utf-8');
    return c.html(html);
  }
  return c.json({ status: 'ok', service: 'live-info-plugin (typescript)' });
});

app.get('/health', (c) => {
  return c.json({
    status: 'ok',
    service: 'live-info-plugin',
    runtime: 'typescript-node',
    searxng_url: config.searxngUrl,
    llm_provider: config.llmProvider,
    rate_limit_per_minute: config.rateLimitPerMinute,
  });
});

app.get('/tools', (c) => {
  const manifestPath = path.join(rootDir, 'tools_manifest.json');
  if (fs.existsSync(manifestPath)) {
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
    return c.json(manifest);
  }
  return c.json({ error: 'NotFound', detail: 'tools_manifest.json not found' }, 404);
});

// ==============================================================================
// 2. Core Capabilities Endpoints
// ==============================================================================

// POST /search
app.post('/search', async (c) => {
  const body = await c.req.json();
  const parsed = SearchRequestSchema.parse(body);
  const { results, cached } = await executeSearch(parsed);
  return c.json({
    query: parsed.query,
    total: results.length,
    results,
    cached,
  });
});

// POST /news
app.post('/news', async (c) => {
  const body = await c.req.json();
  const parsed = NewsRequestSchema.parse(body);
  const response = await getNews(parsed);
  return c.json(response);
});

// POST /read
app.post('/read', async (c) => {
  const body = await c.req.json();
  const parsed = ReaderRequestSchema.parse(body);
  const response = await readUrl(parsed);
  return c.json(response);
});

// POST /crawl (Scrapy-Style Multi-Page Crawler)
app.post('/crawl', async (c) => {
  const body = await c.req.json();
  const parsed = CrawlRequestSchema.parse(body);
  const response = await crawlWebsite(parsed);
  return c.json(response);
});

// POST /research
app.post('/research', async (c) => {
  const body = await c.req.json();
  const parsed = ResearchRequestSchema.parse(body);
  const response = await conductResearch(parsed);
  return c.json(response);
});

// POST /verify
app.post('/verify', async (c) => {
  const body = await c.req.json();
  const parsed = FactVerificationRequestSchema.parse(body);
  const response = await verifyClaim(parsed);
  return c.json(response);
});

// ==============================================================================
// Start Server
// ==============================================================================

if (process.env.NODE_ENV !== 'test') {
  console.log(`🌐 LiveInfo Plugin (TypeScript) starting on http://${config.host}:${config.port}...`);
  serve({
    fetch: app.fetch,
    port: config.port,
    hostname: config.host,
  });
}

export default app;
