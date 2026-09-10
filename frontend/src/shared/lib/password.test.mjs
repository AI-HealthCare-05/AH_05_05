import assert from 'node:assert/strict';
import test from 'node:test';

import { PASSWORD_MAX_LENGTH, sanitizePasswordInput, validatePassword } from './password.ts';

test('한글 완성형 음절을 지운다', () => {
  assert.equal(sanitizePasswordInput('비둘기23222Ok'), '23222Ok');
  assert.equal(sanitizePasswordInput('K실험xptmxm2627@'), 'Kxptmxm2627@');
});

test('IME 조합 중에 들어오는 호환 자모를 지운다', () => {
  // 완성형만 막으면 여기서 남는다 — 조합 중에는 ㄱ~ㅣ 가 value 로 들어온다.
  assert.equal(sanitizePasswordInput('ㅂㅣㄷAbc1!'), 'Abc1!');
  assert.equal(sanitizePasswordInput('ㅃㅢ'), '');
});

test('첫가끝 자모와 자모 확장 영역도 지운다', () => {
  assert.equal(sanitizePasswordInput('각'), ''); // 첫가끝 (각)
  assert.equal(sanitizePasswordInput('ꥠꥼ'), ''); // 자모 확장 A
  assert.equal(sanitizePasswordInput('ힰퟻ'), ''); // 자모 확장 B
  assert.equal(sanitizePasswordInput('ﾡￂ'), ''); // 반각 한글
});

test('한글이 아닌 문자는 그대로 통과시킨다 (#374 에서 정한 범위)', () => {
  assert.equal(sanitizePasswordInput('漢字實驗'), '漢字實驗');
  assert.equal(sanitizePasswordInput('ひらカタ'), 'ひらカタ');
  assert.equal(sanitizePasswordInput('🙂🔥'), '🙂🔥');
  assert.equal(sanitizePasswordInput('a b'), 'a b');
  assert.equal(sanitizePasswordInput('Abc123!@#'), 'Abc123!@#');
});

test('제거를 먼저 하고 상한까지 자른다', () => {
  // 순서가 바뀌면 지워질 한글이 상한을 차지해 결과가 달라진다.
  const value = '가'.repeat(10) + 'a'.repeat(PASSWORD_MAX_LENGTH);
  assert.equal(sanitizePasswordInput(value), 'a'.repeat(PASSWORD_MAX_LENGTH));
});

test('상한을 넘는 입력은 상한까지 자른다', () => {
  assert.equal(
    sanitizePasswordInput('a'.repeat(PASSWORD_MAX_LENGTH + 5)).length,
    PASSWORD_MAX_LENGTH,
  );
});

test('빈 문자열은 그대로 둔다', () => {
  assert.equal(sanitizePasswordInput(''), '');
});

test('한글이 특수문자 조건을 대신 채우던 값은 정리 후 정책에 걸린다', () => {
  // 이 이슈의 출발점 — 한글이 [^a-zA-Z0-9] 에 걸려 「특수문자」 요건을 통과시켰다.
  assert.equal(validatePassword('비둘기23222Ok'), null);
  assert.notEqual(validatePassword(sanitizePasswordInput('비둘기23222Ok')), null);
});
