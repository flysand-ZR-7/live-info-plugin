import { describe, it, expect } from 'vitest';
import app from '../src/index.js';

describe('LiveInfo Plugin Hono Gateway API', () => {
  it('serves the dark mode web dashboard at GET /', async () => {
    const res = await app.request('/');
    expect(res.status).toBe(200);
    const html = await res.text();
    expect(html).toContain('LiveInfo');
    expect(html).toContain('Autonomous Web Intelligence');
  });

  it('serves health status at GET /health', async () => {
    const res = await app.request('/health');
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.status).toBe('ok');
    expect(data.runtime).toBe('typescript-node');
  });

  it('serves JSON tools manifest at GET /tools', async () => {
    const res = await app.request('/tools');
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.tools).toBeDefined();
    expect(data.tools.length).toBeGreaterThanOrEqual(5);
  });

  it('rejects SSRF attacks on POST /read with 400 SecurityViolation', async () => {
    const res = await app.request('/read', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: 'http://169.254.169.254/latest/meta-data/' }),
    });

    expect(res.status).toBe(400);
    const data = await res.json();
    expect(data.error).toBe('SecurityViolation');
  });
});
