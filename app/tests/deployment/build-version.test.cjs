const assert = require('node:assert/strict');
const { existsSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const script = path.resolve(__dirname, '../../../scripts/ci/allocate_build_version.cjs');
const context = { repo: { owner: 'example', repo: 'rxvita' }, sha: 'a'.repeat(40) };

function allocator() {
  assert.ok(existsSync(script), 'Daily build version allocator is not implemented');
  return require(script);
}

// Substitute only the external GitHub REST boundary; allocator code runs unchanged.
function repository(names = [], hooks = {}) {
  const refs = new Map(names.map(name => [`refs/tags/${name}`, 'old-commit']));
  const git = {
    async listMatchingRefs({ ref }) {
      return { data: [...refs.keys()].filter(key => key.startsWith(`refs/${ref}`))
        .map(ref => ({ ref, object: { type: 'commit', sha: refs.get(ref) } })) };
    },
    async createRef({ ref, sha }) {
      if (hooks.create) await hooks.create(ref, refs);
      if (refs.has(ref)) throw Object.assign(new Error('Reference already exists'), { status: 422 });
      refs.set(ref, sha);
      return { data: { ref, object: { type: 'commit', sha } } };
    },
    async getRef({ ref }) {
      const key = `refs/${ref}`;
      if (!refs.has(key)) throw Object.assign(new Error('Not found'), { status: 404 });
      return { data: { ref: key, object: { type: 'commit', sha: refs.get(key) } } };
    },
  };
  return { github: { rest: { git } }, refs };
}

test('Korean midnight starts a new date even when UTC is still the previous date', async () => {
  const { github, refs } = repository(['build-20260916-7']);
  const version = await allocator()({ github, context, now: new Date('2026-09-16T15:00:00Z') });
  assert.equal(version, 'build-20260917-1');
  assert.equal(refs.get('refs/tags/build-20260917-1'), context.sha);
});

test('increments the numeric maximum, ignores unrelated suffixes and does not fill gaps', async () => {
  const { github } = repository(['build-20260917-2', 'build-20260917-10', 'build-20260917-9',
    'build-20260917-999-preview']);
  assert.equal(await allocator()({ github, context, now: new Date('2026-09-17T01:00:00Z') }),
    'build-20260917-11');
});

test('a second build keeps an allocated number consumed and next Korean day resets to one', async () => {
  const { github } = repository();
  const allocate = allocator();
  assert.equal(await allocate({ github, context, now: new Date('2026-09-17T14:59:58Z') }), 'build-20260917-1');
  assert.equal(await allocate({ github, context, now: new Date('2026-09-17T14:59:59Z') }), 'build-20260917-2');
  assert.equal(await allocate({ github, context, now: new Date('2026-09-17T15:00:00Z') }), 'build-20260918-1');
});

test('retries the next number only after verifying another caller created the same ref', async () => {
  let first = true;
  const { github } = repository([], { create(ref, refs) {
    if (first) { first = false; refs.set(ref, 'competing-commit'); }
  } });
  assert.equal(await allocator()({ github, context, now: new Date('2026-09-17T01:00:00Z') }),
    'build-20260917-2');
});

test('permission and non-collision validation errors fail closed rather than return a version', async () => {
  for (const status of [403, 422]) {
    const error = Object.assign(new Error('Blocked by policy'), { status });
    const { github, refs } = repository([], { create() { throw error; } });
    await assert.rejects(allocator()({ github, context, now: new Date('2026-09-17T01:00:00Z') }),
      err => err === error);
    assert.equal(refs.size, 0);
  }
});

test('stops after bounded collision retries', async () => {
  const { github } = repository([], { create(ref, refs) { refs.set(ref, 'competing-commit'); } });
  await assert.rejects(allocator()({ github, context, now: new Date('2026-09-17T01:00:00Z') }),
    /reserve|allocate|collision/i);
});
