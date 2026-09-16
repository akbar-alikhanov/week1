/**
 * Simple in-memory sliding-window rate limiter, keyed by an arbitrary
 * string (e.g. user id). Sufficient for a single-process deployment; a
 * multi-instance production deployment should swap this for a shared
 * store (e.g. Redis/Upstash) behind the same `RateLimiter` shape.
 */
export class InMemoryRateLimiter {
  private hits = new Map<string, number[]>();

  constructor(
    private readonly maxRequests: number,
    private readonly windowMs: number,
  ) {}

  /** Returns true if the request is allowed, false if the limit was exceeded. */
  check(key: string): boolean {
    const now = Date.now();
    const windowStart = now - this.windowMs;
    const timestamps = (this.hits.get(key) ?? []).filter((t) => t > windowStart);

    if (timestamps.length >= this.maxRequests) {
      this.hits.set(key, timestamps);
      return false;
    }

    timestamps.push(now);
    this.hits.set(key, timestamps);
    return true;
  }
}

export const sqlQueryRateLimiter = new InMemoryRateLimiter(20, 60_000);
