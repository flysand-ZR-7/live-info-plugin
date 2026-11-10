import { config } from '../config.js';

export interface LLMOptions {
  prompt: string;
  systemPrompt?: string;
  maxTokens?: number;
  temperature?: number;
}

/**
 * Standardized LLM completion caller across Anthropic, OpenAI, and OpenAI-compatible providers.
 */
export async function completeText(opts: LLMOptions): Promise<string> {
  const { prompt, systemPrompt, maxTokens = 1000, temperature = 0.2 } = opts;

  // Option A: Anthropic (Claude)
  if (config.llmProvider === 'anthropic') {
    if (!config.llmApiKey) {
      return `[LLM Not Configured] Unable to synthesize without LLM_API_KEY. Prompt preview: ${prompt.substring(0, 150)}...`;
    }

    try {
      const res = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': config.llmApiKey,
          'anthropic-version': '2023-06-01',
        },
        body: JSON.stringify({
          model: config.llmModel || 'claude-3-5-sonnet-20241022',
          max_tokens: maxTokens,
          temperature,
          system: systemPrompt,
          messages: [{ role: 'user', content: prompt }],
        }),
      });

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(`Anthropic API returned ${res.status}: ${errText}`);
      }

      const data: any = await res.json();
      return data?.content?.[0]?.text || '';
    } catch (err: any) {
      console.error('[LLM Error (Anthropic)]', err.message);
      return `[Synthesis Error: ${err.message}]`;
    }
  }

  // Option B: OpenAI / Local OpenAI-compatible (Ollama, vLLM, LM Studio)
  const baseUrl = config.llmProvider === 'openai-compatible'
    ? (config.llmBaseUrl || 'http://localhost:11434/v1').replace(/\/+$/, '')
    : 'https://api.openai.com/v1';

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (config.llmApiKey) {
    headers['Authorization'] = `Bearer ${config.llmApiKey}`;
  }

  const messages: Array<{ role: string; content: string }> = [];
  if (systemPrompt) {
    messages.push({ role: 'system', content: systemPrompt });
  }
  messages.push({ role: 'user', content: prompt });

  try {
    const res = await fetch(`${baseUrl}/chat/completions`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        model: config.llmModel || (config.llmProvider === 'openai-compatible' ? 'llama3.1' : 'gpt-4o-mini'),
        messages,
        max_tokens: maxTokens,
        temperature,
      }),
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`OpenAI API returned ${res.status}: ${errText}`);
    }

    const data: any = await res.json();
    return data?.choices?.[0]?.message?.content || '';
  } catch (err: any) {
    console.error('[LLM Error]', err.message);
    return `[Synthesis Error: ${err.message}]`;
  }
}
