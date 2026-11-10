import dns from 'node:dns/promises';
import { URL } from 'node:url';

export class SSRFProtectionError extends Error {
  statusCode: number;
  constructor(message: string, statusCode: number = 400) {
    super(message);
    this.name = 'SSRFProtectionError';
    this.statusCode = statusCode;
  }
}

const BLOCKED_HOSTNAMES = new Set([
  'localhost',
  'localhost.localdomain',
  'ip6-localhost',
  'ip6-loopback',
  'metadata.google.internal',
  'instance-data',
]);

/**
 * Checks whether an IPv4 address is in a reserved/private/link-local/loopback range.
 */
export function isPrivateIPv4(ip: string): boolean {
  const parts = ip.split('.').map((p) => parseInt(p, 10));
  if (parts.length !== 4 || parts.some((p) => isNaN(p) || p < 0 || p > 255)) {
    return true; // malformed, treat as unsafe
  }

  const [a, b] = parts;

  // 127.0.0.0/8 Loopback
  if (a === 127) return true;
  // 10.0.0.0/8 Private
  if (a === 10) return true;
  // 172.16.0.0/12 Private
  if (a === 172 && b >= 16 && b <= 31) return true;
  // 192.168.0.0/16 Private
  if (a === 192 && b === 168) return true;
  // 169.254.0.0/16 Link-local & Cloud Metadata (AWS/GCP/Azure)
  if (a === 169 && b === 254) return true;
  // 0.0.0.0/8 Current network
  if (a === 0) return true;
  // 100.64.0.0/10 Carrier-grade NAT
  if (a === 100 && b >= 64 && b <= 127) return true;
  // 224.0.0.0/4 Multicast
  if (a >= 224 && a <= 239) return true;
  // 240.0.0.0/4 Reserved
  if (a >= 240) return true;

  return false;
}

/**
 * Checks whether an IPv6 address is in a loopback/link-local/unique-local range.
 */
export function isPrivateIPv6(ip: string): boolean {
  const lower = ip.toLowerCase();
  if (lower === '::1' || lower === '0:0:0:0:0:0:0:1') return true;
  // fc00::/7 (Unique local)
  if (lower.startsWith('fc') || lower.startsWith('fd')) return true;
  // fe80::/10 (Link-local)
  if (lower.startsWith('fe8') || lower.startsWith('fe9') || lower.startsWith('fea') || lower.startsWith('feb')) {
    return true;
  }
  return false;
}

/**
 * Validates a URL against SSRF threats:
 * 1. Requires http/https.
 * 2. Blocks loopback hostname aliases.
 * 3. Resolves DNS to check all returned IPs against private/metadata CIDRs.
 */
export async function validateUrl(rawUrl: string): Promise<string> {
  if (!rawUrl || typeof rawUrl !== 'string') {
    throw new SSRFProtectionError('URL must be a non-empty string.');
  }

  let parsed: URL;
  try {
    parsed = new URL(rawUrl.trim());
  } catch (err: any) {
    throw new SSRFProtectionError(`Malformed URL: ${err.message}`);
  }

  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new SSRFProtectionError(`Unsupported scheme '${parsed.protocol}'. Only http and https are permitted.`);
  }

  const hostname = parsed.hostname.toLowerCase();
  if (!hostname) {
    throw new SSRFProtectionError('URL missing valid hostname.');
  }

  if (BLOCKED_HOSTNAMES.has(hostname) || hostname.endsWith('.localhost')) {
    throw new SSRFProtectionError(`Access to local hostname '${hostname}' is prohibited.`);
  }

  // Tor .onion domains do not resolve via standard clearweb DNS
  if (hostname.endsWith('.onion')) {
    return parsed.toString();
  }

  // If host is an IP literal
  if (/^(\d{1,3}\.){3}\d{1,3}$/.test(hostname)) {
    if (isPrivateIPv4(hostname)) {
      throw new SSRFProtectionError(`Access to private IP address '${hostname}' is prohibited.`);
    }
    return parsed.toString();
  }

  // Resolve DNS
  try {
    const addresses = await dns.lookup(hostname, { all: true });
    if (!addresses || addresses.length === 0) {
      throw new SSRFProtectionError(`Could not resolve DNS for host '${hostname}'.`);
    }

    for (const record of addresses) {
      if (record.family === 4 && isPrivateIPv4(record.address)) {
        throw new SSRFProtectionError(`Host '${hostname}' resolves to private IP '${record.address}'. Access prohibited.`);
      }
      if (record.family === 6 && isPrivateIPv6(record.address)) {
        throw new SSRFProtectionError(`Host '${hostname}' resolves to private IPv6 '${record.address}'. Access prohibited.`);
      }
    }
  } catch (err: any) {
    if (err instanceof SSRFProtectionError) throw err;
    throw new SSRFProtectionError(`DNS resolution failed for '${hostname}': ${err.message}`);
  }

  return parsed.toString();
}
