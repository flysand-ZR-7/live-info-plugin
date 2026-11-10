import { executeSearch } from './search.js';
import { completeText } from './llm.js';
import type { NewsArticleItem, NewsRequest, NewsResponse } from '../types.js';

export async function getNews(req: NewsRequest): Promise<NewsResponse> {
  const { results, cached } = await executeSearch(
    {
      query: req.topic,
      max_results: req.max_results,
      language: 'en',
      time_range: req.time_range,
      category: 'news',
    },
    true,
  );

  const articles: NewsArticleItem[] = results.map((r) => {
    let source = r.engine;
    try {
      source = new URL(r.url).hostname.replace(/^www\./, '');
    } catch {}

    return {
      title: r.title,
      url: r.url,
      source,
      snippet: r.snippet,
    };
  });

  if (articles.length === 0) {
    return {
      topic: req.topic,
      time_range: req.time_range,
      total: 0,
      articles: [],
      briefing: `No recent news articles discovered for topic: "${req.topic}".`,
      cached,
    };
  }

  // Generate 5-bullet executive briefing with citations [n]
  const contextSnippets = articles
    .slice(0, 8)
    .map((a, i) => `[${i + 1}] "${a.title}" (${a.source})\nURL: ${a.url}\nExcerpt: ${a.snippet}`)
    .join('\n\n');

  const prompt = `Topic: "${req.topic}"\nTime window: ${req.time_range}\n\nArticles:\n${contextSnippets}\n\nTask: Synthesize a concise executive briefing of up to 5 bullet points summarizing the most critical updates. Each bullet point MUST cite its sources using numbered brackets like [1], [2]. Be objective, direct, and factual.`;

  const briefing = await completeText({
    prompt,
    systemPrompt: 'You are an elite geopolitical and business intelligence analyst. Summarize news clearly and cite article numbers precisely.',
    maxTokens: 500,
  });

  return {
    topic: req.topic,
    time_range: req.time_range,
    total: articles.length,
    articles,
    briefing,
    cached,
  };
}
