import test from 'node:test';
import assert from 'node:assert/strict';
import { createLimiter } from '../lib/rate-limit.mjs';

test('rate limiter: cuenta por clave y se reinicia al pasar la ventana', () => {
  let t = 0;
  const allow = createLimiter(2, 1000, () => t);
  assert.deepEqual([allow('a'), allow('a'), allow('a')], [true, true, false]);
  assert.equal(allow('b'), true);  // otra clave no se ve afectada
  t = 1000;
  assert.equal(allow('a'), true);
});
