import { describe, it, expect } from 'vitest';
import { isPrivateIPv4, isPrivateIPv6, validateUrl, SSRFProtectionError } from '../src/security.js';

describe('SSRF Protection Guard', () => {
  it('identifies private and reserved IPv4 addresses', () => {
    expect(isPrivateIPv4('127.0.0.1')).toBe(true);
    expect(isPrivateIPv4('10.0.0.1')).toBe(true);
    expect(isPrivateIPv4('172.16.0.5')).toBe(true);
    expect(isPrivateIPv4('192.168.1.1')).toBe(true);
    expect(isPrivateIPv4('169.254.169.254')).toBe(true); // AWS/GCP metadata
    expect(isPrivateIPv4('8.8.8.8')).toBe(false); // Google Public DNS
    expect(isPrivateIPv4('93.184.216.34')).toBe(false); // example.com
  });

  it('identifies private and loopback IPv6 addresses', () => {
    expect(isPrivateIPv6('::1')).toBe(true);
    expect(isPrivateIPv6('fc00::1')).toBe(true);
    expect(isPrivateIPv6('fe80::1')).toBe(true);
    expect(isPrivateIPv6('2606:4700:4700::1111')).toBe(false); // Cloudflare
  });

  it('blocks non-HTTP protocols', async () => {
    await expect(validateUrl('file:///etc/passwd')).rejects.toThrow(SSRFProtectionError);
    await expect(validateUrl('ftp://example.com')).rejects.toThrow(SSRFProtectionError);
  });

  it('blocks localhost aliases and cloud metadata hostnames', async () => {
    await expect(validateUrl('http://localhost:8080')).rejects.toThrow(SSRFProtectionError);
    await expect(validateUrl('http://metadata.google.internal')).rejects.toThrow(SSRFProtectionError);
  });

  it('blocks private IP literals', async () => {
    await expect(validateUrl('http://169.254.169.254/latest/meta-data/')).rejects.toThrow(SSRFProtectionError);
    await expect(validateUrl('http://192.168.1.100')).rejects.toThrow(SSRFProtectionError);
    await expect(validateUrl('http://127.0.0.1:3000')).rejects.toThrow(SSRFProtectionError);
  });

  it('allows public resolvable domains', async () => {
    const valid = await validateUrl('https://example.com/test');
    expect(valid).toBe('https://example.com/test');
  });

  it('allows .onion domains', async () => {
    const valid = await validateUrl('http://duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion');
    expect(valid).toContain('.onion');
  });
});
