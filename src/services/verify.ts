import { executeSearch } from './search.js';
import { completeText } from './llm.js';
import type { EvidenceItem, FactVerificationRequest, FactVerificationResponse, Verdict } from '../types.js';

export async function verifyClaim(req: FactVerificationRequest): Promise<FactVerificationResponse> {
  const claim = req.claim.trim();

  // Step 1: Formulate adversarial search queries
  const confirmingQuery = `${claim} true evidence proof`;
  const refutingQuery = `${claim} false debunked myth criticism fact check`;

  const [confirmingRes, refutingRes] = await Promise.all([
    executeSearch({ query: confirmingQuery, max_results: 5, language: 'en' }, true).catch(() => ({ results: [] })),
    executeSearch({ query: refutingQuery, max_results: 5, language: 'en' }, true).catch(() => ({ results: [] })),
  ]);

  const supporting: EvidenceItem[] = confirmingRes.results.slice(0, 3).map((r) => ({
    url: r.url,
    title: r.title,
    quote_summary: r.snippet.slice(0, 200),
  }));

  const contradicting: EvidenceItem[] = refutingRes.results.slice(0, 3).map((r) => ({
    url: r.url,
    title: r.title,
    quote_summary: r.snippet.slice(0, 200),
  }));

  // Step 2: LLM Adjudication
  const context = `Claim: "${claim}"\n\nSupporting Evidence Searches:\n${supporting.map((s) => `- ${s.title}: "${s.quote_summary}" (${s.url})`).join('\n')}\n\nContradicting Evidence Searches:\n${contradicting.map((c) => `- ${c.title}: "${c.quote_summary}" (${c.url})`).join('\n')}`;

  const adjudicationPrompt = `${context}\n\nTask: Evaluate the veracity of this claim based on the retrieved evidence.\n\nStrict Output Format:\nVERDICT: [Choose ONE: TRUE | MOSTLY_TRUE | MIXED | MOSTLY_FALSE | FALSE | UNVERIFIABLE]\nCONFIDENCE: [A number between 0.0 and 1.0]\nEXPLANATION: [A concise, 2-3 sentence explanation based strictly on the evidence]`;

  let verdict: Verdict = 'UNVERIFIABLE';
  let confidence = 0.5;
  let explanation = 'Unable to conclusively verify claim against retrieved evidence.';

  try {
    const rawDecision = await completeText({
      prompt: adjudicationPrompt,
      systemPrompt: 'You are an impartial, highly rigorous fact verification adjudicator. Rely strictly on evidence and output only the required format.',
      maxTokens: 350,
    });

    const verdictMatch = rawDecision.match(/VERDICT:\s*(TRUE|MOSTLY_TRUE|MIXED|MOSTLY_FALSE|FALSE|UNVERIFIABLE)/i);
    if (verdictMatch) {
      verdict = verdictMatch[1].toUpperCase() as Verdict;
    }

    const confMatch = rawDecision.match(/CONFIDENCE:\s*([0-1](?:\.\d+)?)/i);
    if (confMatch) {
      confidence = Math.min(1.0, Math.max(0.0, parseFloat(confMatch[1])));
    }

    const explMatch = rawDecision.match(/EXPLANATION:\s*([\s\S]+)$/i);
    if (explMatch) {
      explanation = explMatch[1].trim();
    } else {
      explanation = rawDecision.replace(/VERDICT:.*?\n/i, '').replace(/CONFIDENCE:.*?\n/i, '').trim();
    }
  } catch (err: any) {
    console.warn('[Fact Verification Error]', err.message);
  }

  return {
    claim,
    verdict,
    confidence,
    explanation,
    supporting,
    contradicting,
  };
}
