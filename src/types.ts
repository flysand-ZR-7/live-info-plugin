import { z } from 'zod';

// ==============================================================================
// 1. Search Types & Schemas
// ==============================================================================

export const SearchTimeRangeEnum = z.enum(['day', 'week', 'month', 'year']);
export type SearchTimeRange = z.infer<typeof SearchTimeRangeEnum>;

export const SearchRequestSchema = z.object({
  query: z.string().min(1).max(500),
  max_results: z.number().int().min(1).max(500).default(8),
  language: z.string().max(10).default('en'),
  time_range: SearchTimeRangeEnum.optional(),
  category: z.string().optional(),
  engine: z.string().optional(),
});
export type SearchRequest = z.infer<typeof SearchRequestSchema>;

export const SearchResultItemSchema = z.object({
  title: z.string(),
  url: z.string(),
  snippet: z.string(),
  engine: z.string(),
});
export type SearchResultItem = z.infer<typeof SearchResultItemSchema>;

export const SearchResponseSchema = z.object({
  query: z.string(),
  total: z.number(),
  results: z.array(SearchResultItemSchema),
  cached: z.boolean().default(false),
});
export type SearchResponse = z.infer<typeof SearchResponseSchema>;

// ==============================================================================
// 2. News Types & Schemas
// ==============================================================================

export const NewsRequestSchema = z.object({
  topic: z.string().min(1).max(500),
  time_range: SearchTimeRangeEnum.default('day'),
  max_results: z.number().int().min(1).max(30).default(8),
});
export type NewsRequest = z.infer<typeof NewsRequestSchema>;

export const NewsArticleItemSchema = z.object({
  title: z.string(),
  url: z.string(),
  source: z.string(),
  published_date: z.string().optional(),
  snippet: z.string(),
});
export type NewsArticleItem = z.infer<typeof NewsArticleItemSchema>;

export const NewsResponseSchema = z.object({
  topic: z.string(),
  time_range: z.string(),
  total: z.number(),
  articles: z.array(NewsArticleItemSchema),
  briefing: z.string(),
  cached: z.boolean().default(false),
});
export type NewsResponse = z.infer<typeof NewsResponseSchema>;

// ==============================================================================
// 3. Reader Types & Schemas
// ==============================================================================

export const ReaderRequestSchema = z.object({
  url: z.string().url(),
  max_chars: z.number().int().min(500).max(50000).default(8000),
  summarize: z.boolean().default(false),
  use_tor: z.boolean().default(false),
});
export type ReaderRequest = z.infer<typeof ReaderRequestSchema>;

export const ReaderResponseSchema = z.object({
  url: z.string(),
  title: z.string().nullable().optional(),
  text: z.string(),
  truncated: z.boolean(),
  char_count: z.number(),
  summary: z.string().nullable().optional(),
  cached: z.boolean().default(false),
});
export type ReaderResponse = z.infer<typeof ReaderResponseSchema>;

// ==============================================================================
// 4. Crawler Types & Schemas (Scrapy-Style)
// ==============================================================================

export const CrawledPageItemSchema = z.object({
  url: z.string(),
  title: z.string().nullable().optional(),
  text: z.string(),
  depth: z.number(),
  word_count: z.number(),
  child_links_count: z.number(),
});
export type CrawledPageItem = z.infer<typeof CrawledPageItemSchema>;

export const CrawlRequestSchema = z.object({
  url: z.string().url(),
  max_depth: z.number().int().min(1).max(4).default(2),
  max_pages: z.number().int().min(1).max(30).default(10),
  stay_on_domain: z.boolean().default(true),
  summarize: z.boolean().default(false),
  use_tor: z.boolean().default(false),
});
export type CrawlRequest = z.infer<typeof CrawlRequestSchema>;

export const CrawlResponseSchema = z.object({
  root_url: z.string(),
  total_pages_crawled: z.number(),
  depth_reached: z.number(),
  pages: z.array(CrawledPageItemSchema),
  knowledge_summary: z.string().nullable().optional(),
});
export type CrawlResponse = z.infer<typeof CrawlResponseSchema>;

// ==============================================================================
// 5. Research Types & Schemas
// ==============================================================================

export const ResearchDepthEnum = z.enum(['quick', 'standard', 'deep']);
export type ResearchDepth = z.infer<typeof ResearchDepthEnum>;

export const ResearchRequestSchema = z.object({
  question: z.string().min(3).max(1000),
  depth: ResearchDepthEnum.default('standard'),
});
export type ResearchRequest = z.infer<typeof ResearchRequestSchema>;

export const ResearchSourceSchema = z.object({
  id: z.number(),
  title: z.string(),
  url: z.string(),
  domain: z.string(),
});
export type ResearchSource = z.infer<typeof ResearchSourceSchema>;

export const ResearchResponseSchema = z.object({
  question: z.string(),
  depth: z.string(),
  sub_queries: z.array(z.string()),
  answer: z.string(),
  sources: z.array(ResearchSourceSchema),
});
export type ResearchResponse = z.infer<typeof ResearchResponseSchema>;

// ==============================================================================
// 6. Fact Verification Types & Schemas
// ==============================================================================

export const VerdictEnum = z.enum([
  'TRUE',
  'MOSTLY_TRUE',
  'MIXED',
  'MOSTLY_FALSE',
  'FALSE',
  'UNVERIFIABLE',
]);
export type Verdict = z.infer<typeof VerdictEnum>;

export const FactVerificationRequestSchema = z.object({
  claim: z.string().min(3).max(1000),
});
export type FactVerificationRequest = z.infer<typeof FactVerificationRequestSchema>;

export const EvidenceItemSchema = z.object({
  url: z.string(),
  title: z.string(),
  quote_summary: z.string(),
});
export type EvidenceItem = z.infer<typeof EvidenceItemSchema>;

export const FactVerificationResponseSchema = z.object({
  claim: z.string(),
  verdict: VerdictEnum,
  confidence: z.number().min(0).max(1),
  explanation: z.string(),
  supporting: z.array(EvidenceItemSchema).default([]),
  contradicting: z.array(EvidenceItemSchema).default([]),
});
export type FactVerificationResponse = z.infer<typeof FactVerificationResponseSchema>;
