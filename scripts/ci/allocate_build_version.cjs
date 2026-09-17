// Reserve before building, so failed/partially pushed builds never reuse a number.
// These lightweight Git tags are a durable counter: do not delete or rewrite them.
module.exports = async function allocateBuildVersion({ github, context, now = new Date() }) {
  const { owner, repo } = context.repo;
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(now);
  const date = ['year', 'month', 'day'].map(type => parts.find(part => part.type === type).value).join('');
  const prefix = `build-${date}-`;
  const { data } = await github.rest.git.listMatchingRefs({ owner, repo, ref: `tags/${prefix}` });
  if (!Array.isArray(data)) throw new Error('Invalid GitHub matching-ref response');
  let maximum = 0;
  for (const item of data) {
    const match = item.ref.match(new RegExp(`^refs/tags/${prefix}([1-9][0-9]*)$`));
    if (!match) continue;
    const number = Number(match[1]);
    if (!Number.isSafeInteger(number)) throw new Error('Build sequence exceeds safe integer range');
    maximum = Math.max(maximum, number);
  }
  for (let attempt = 1; attempt <= 5; attempt++) {
    const number = maximum + attempt;
    if (!Number.isSafeInteger(number)) throw new Error('Build sequence exceeds safe integer range');
    const version = `${prefix}${number}`;
    try {
      await github.rest.git.createRef({ owner, repo, ref: `refs/tags/${version}`, sha: context.sha });
      return version;
    } catch (error) {
      // A 422 also means policy/validation failure. Retry only a proven collision.
      if (error.status !== 422) throw error;
      try {
        const existing = await github.rest.git.getRef({ owner, repo, ref: `tags/${version}` });
        if (existing.data.ref !== `refs/tags/${version}`) throw error;
      } catch {
        throw error;
      }
    }
  }
  throw new Error('Unable to reserve a build version after repeated collisions');
};
