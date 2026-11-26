export function createLimiter(limit: number, windowMs: number, now?: () => number): (key: string) => boolean;
