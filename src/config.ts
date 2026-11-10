import dotenv from 'dotenv';

dotenv.config();

export const config = {
  port: parseInt(process.env.PORT || '8000', 10),
  host: process.env.HOST || '0.0.0.0',
  logLevel: process.env.LOG_LEVEL || 'info',
  searxngUrl: (process.env.SEARXNG_URL || 'http://localhost:8080').replace(/\/+$/, ''),
  braveApiKey: process.env.BRAVE_API_KEY || '',
  cacheTtlSeconds: parseInt(process.env.CACHE_TTL_SECONDS || '600', 10),
  rateLimitPerMinute: parseInt(process.env.RATE_LIMIT_PER_MINUTE || '60', 10),
  readerTimeoutMs: parseInt(process.env.READER_TIMEOUT_MS || '10000', 10),
  readerMaxBytes: parseInt(process.env.READER_MAX_BYTES || String(5 * 1024 * 1024), 10), // 5MB
  llmProvider: process.env.LLM_PROVIDER || 'anthropic', // 'anthropic' | 'openai' | 'openai-compatible'
  llmApiKey: process.env.LLM_API_KEY || '',
  llmBaseUrl: process.env.LLM_BASE_URL || 'https://api.anthropic.com/v1',
  llmModel: process.env.LLM_MODEL || 'claude-3-5-sonnet-20241022',
};
