import assert from 'node:assert/strict';
import test from 'node:test';

import { mockListCommonCodes } from './api.mock.ts';

test('returns all five positive feedback reasons sorted by sortOrder', () => {
  const items = mockListCommonCodes('CHAT', 'P_REASON');

  assert.equal(items.length, 5);
  assert.deepEqual(
    items.map(({ detailCode, sortOrder }) => [detailCode, sortOrder]),
    [
      ['P01', 0],
      ['P02', 1],
      ['P03', 2],
      ['P04', 3],
      ['P05', 4],
    ],
  );
});

test('returns all five negative feedback reasons sorted by sortOrder', () => {
  const items = mockListCommonCodes('CHAT', 'N_REASON');

  assert.equal(items.length, 5);
  assert.deepEqual(
    items.map(({ detailCode, sortOrder }) => [detailCode, sortOrder]),
    [
      ['N01', 1],
      ['N02', 2],
      ['N03', 3],
      ['N04', 4],
      ['N05', 5],
    ],
  );
});
