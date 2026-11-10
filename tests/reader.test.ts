import { describe, it, expect } from 'vitest';
import { extractCleanArticle } from '../src/services/reader.js';

describe('Reader Article Extraction', () => {
  it('extracts clean body text and strips boilerplate scripts and styles', () => {
    const html = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>Artificial Intelligence Breakthrough</title>
          <style>body { background: black; }</style>
        </head>
        <body>
          <script>console.log("tracking code");</script>
          <header><nav><a href="/">Home</a></nav></header>
          <article>
            <h1>New Milestone Reached</h1>
            <p>Researchers have introduced an ultra-lightweight autonomous gateway architecture.</p>
            <p>The new framework achieves sub-100ms response times and requires zero heavy dependencies.</p>
          </article>
          <footer>Copyright 2026 AI Journal</footer>
        </body>
      </html>
    `;

    const { title, text } = extractCleanArticle(html, 'https://example.com/ai');
    expect(title).toContain('Artificial Intelligence Breakthrough');
    expect(text).toContain('autonomous gateway architecture');
    expect(text).not.toContain('console.log');
    expect(text).not.toContain('background: black');
  });
});
