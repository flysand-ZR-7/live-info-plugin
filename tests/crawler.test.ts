import { describe, it, expect } from 'vitest';
import { extractChildLinks } from '../src/services/crawler.js';

describe('Scrapy-Style Crawler Link Extraction', () => {
  it('extracts, normalizes, and filters child links within domain boundaries', () => {
    const html = `
      <html>
        <body>
          <a href="/docs/guide">Guide</a>
          <a href="https://example.com/api">API Reference</a>
          <a href="https://malicious.com/phish">External Domain</a>
          <a href="/downloads/setup.exe">Setup Exe</a>
          <a href="/images/logo.png">Image File</a>
          <a href="javascript:void(0)">Action</a>
          <a href="#overview">Anchor Link</a>
        </body>
      </html>
    `;

    const links = extractChildLinks(html, 'https://example.com/start', 'example.com');
    expect(links).toContain('https://example.com/docs/guide');
    expect(links).toContain('https://example.com/api');
    expect(links).not.toContain('https://malicious.com/phish');
    expect(links).not.toContain('https://example.com/downloads/setup.exe');
    expect(links).not.toContain('https://example.com/images/logo.png');
  });
});
