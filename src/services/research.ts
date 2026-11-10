import { executeSearch } from './search.js';
import { readUrl } from './reader.js';
import { completeText } from './llm.js';
import type { ResearchDepth, ResearchRequest, ResearchResponse, ResearchSource } from '../types.js';

function getSubQueryCount(depth: ResearchDepth): number {
  switch (depth) {
    case 'quick':
      return 3;
    case 'deep':
      return 8;
    case 'standard':
    default:
      return 5;
  }
}

export async function conductResearch(req: ResearchRequest): Promise<ResearchResponse> {
  const queryCount = getSubQueryCount(req.depth);

  // Step 1: Deconstruct into sub-queries
  const decompositionPrompt = `Deconstruct this research question into exactly ${queryCount} distinct, targeted search queries to investigate different facets, evidence, perspectives, and background:\n\nQuestion: "${req.question}"\n\nOutput only one search query per line. No numbering, no bullets.`;

  let subQueries: string[] = [];
  try {
    const rawDecomp = await completeText({
      prompt: decompositionPrompt,
      systemPrompt: 'You are an advanced research strategist. Output only targeted, high-signal search queries line by line.',
      maxTokens: 300,
    });
    subQueries = rawDecomp
      .split('\n')
      .map((q) => q.replace(/^\d+[\.\-\)]\s*/, '').trim())
      .filter((q) => q.length > 2)
      .slice(0, queryCount);
  } catch {}

  if (subQueries.length === 0) {
    subQueries = [req.question, `${req.question} analysis`, `${req.question} key findings`];
  }

  // Step 2: Parallel search across sub-queries
  const searchPromises = subQueries.map((q) =>
    executeSearch({ query: q, max_results: 5, language: 'en' }, true)
      .then((res) => res.results)
      .catch(() => [])
  );

  const searchResultsArrays = await Promise.all(searchPromises);
  const allResults = searchResultsArrays.flat();

  // Step 3: Domain diversity selection
  const domainCount = new Map<string, number>();
  const selectedSources: ResearchSource[] = [];
  const urlsToRead: string[] = [];

  for (const item of allResults) {
    try {
      const domain = new URL(item.url).hostname.replace(/^www\./, '');
      const count = domainCount.get(domain) || 0;
      if (count < 2 && selectedSources.length < 8) {
        domainCount.set(domain, count + 1);
        const id = selectedSources.length + 1;
        selectedSources.push({
          id,
          title: item.title,
          url: item.url,
          domain,
        });
        urlsToRead.push(item.url);
      }
    } catch {}
  }

  // Step 4: Fetch source excerpts
  const readPromises = urlsToRead.slice(0, 5).map((url) =>
    readUrl({ url, max_chars: 3000, summarize: false, use_tor: false }, true)
      .then((res) => res.text.slice(0, 1500))
      .catch(() => '')
  );
  const excerpts = await Promise.all(readPromises);

  // Step 5: Synthesize cited research report
  const context = selectedSources
    .slice(0, 5)
    .map((s, i) => `[${s.id}] Title: ${s.title}\nDomain: ${s.domain}\nURL: ${s.url}\nContent Excerpt: ${excerpts[i] || 'Snippet available from search results.'}`)
    .join('\n\n');

  const reportPrompt = `Research Question: "${req.question}"\n\nInvestigated Sources:\n${context}\n\nTask: Write an authoritative, structured research synthesis report answering the question in detail.\n\nStructure:\n1. Executive Summary\n2. Key Findings & Analysis\n3. Technical Bottlenecks / Uncertainties / Trade-offs\n4. Conclusion\n\nRequirement: Every major assertion MUST cite one or more sources using bracketed citations like [1], [2]. Be objective, analytical, and direct.`;

  const answer = await completeText({
    prompt: reportPrompt,
    systemPrompt: 'You are an elite principal research scientist. Produce deeply cited, factual reports.',
    maxTokens: 1200,
  });

  return {
    question: req.question,
    depth: req.depth,
    sub_queries: subQueries,
    answer,
    sources: selectedSources,
  };
}
