import { expect, test, type Locator, type Page } from 'playwright/test';
import { advanceSignupToPassword, openSignup } from './helpers/signup';

/**
 * #374 — 비밀번호 칸의 한글 차단.
 *
 * 🔴 **이 스펙은 「조합 중에 기존 값이 지워지는 버그」를 잡지 못한다.** 과신하지 말 것.
 *
 * 그 버그는 실제 Windows 한글 IME 에서만 재현됐다. 합성 조합 이벤트(아래 composeInto)로도,
 * CDP `Input.imeSetComposition` 으로도 재현되지 않는다 — 둘 다 시도해 확인했다.
 * `isComposing` 가드를 제거하고 돌려도 이 스펙은 통과한다. **회귀 방지 장치가 아니다.**
 *
 * 여기서 고정하는 것은 세 가지뿐이다.
 *   1. 조합이 확정되면 한글이 걸러진다
 *   2. 한자·이모지·공백은 통과한다 (#374 에서 정한 범위)
 *   3. ⭐ 로그인 비밀번호 칸은 제한이 걸리지 않는다 — 이건 확실히 잡는다
 *
 * 조합 중 동작은 **사람이 실제 한글 키보드로** 확인해야 한다.
 */

/** 조합 중 input(isComposing=true) → compositionend → 확정 input 순서로 흉내낸다. */
async function composeInto(input: Locator, text: string) {
  await input.evaluate((element, value) => {
    const field = element as HTMLInputElement;
    const setValue = (next: string) => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(
        field,
        next,
      );
    };
    field.focus();
    field.dispatchEvent(new CompositionEvent('compositionstart', { bubbles: true }));
    setValue(field.value + value);
    field.dispatchEvent(
      new InputEvent('input', { bubbles: true, isComposing: true, data: value }),
    );
    field.dispatchEvent(
      new CompositionEvent('compositionend', { bubbles: true, data: value }),
    );
  }, text);
}

/** 이메일 인증을 거쳐 비밀번호 단계까지 간다. 공용 헬퍼를 쓴다. */
async function gotoPasswordStep(page: Page) {
  await openSignup(page);
  await advanceSignupToPassword(page);
  await expect(page.getByLabel('비밀번호 확인', { exact: true })).toBeVisible();
}

test('조합이 확정되면 한글만 걸러내고 앞서 입력한 값은 남는다', async ({ page }) => {
  await gotoPasswordStep(page);
  const password = page.getByLabel('비밀번호', { exact: true });

  await password.fill('Abcd1234!');
  await expect(password).toHaveValue('Abcd1234!');

  await composeInto(password, '한글');

  await expect(password).toHaveValue('Abcd1234!');
});

test('낱자만 조합해도 값이 남지 않는다', async ({ page }) => {
  await gotoPasswordStep(page);
  const password = page.getByLabel('비밀번호', { exact: true });

  await composeInto(password, 'ㅂㅣㄷ');

  await expect(password).toHaveValue('');
});

test('붙여넣기로 들어온 한글은 걸러내고 한자·이모지·공백은 통과시킨다', async ({ page }) => {
  await gotoPasswordStep(page);
  const password = page.getByLabel('비밀번호', { exact: true });

  await password.fill('비둘기23222Ok');
  await expect(password).toHaveValue('23222Ok');

  await password.fill('漢字🙂 Abc1!');
  await expect(password).toHaveValue('漢字🙂 Abc1!');
});

test('로그인 비밀번호 칸은 대조용이라 한글이 그대로 남는다', async ({ page }) => {
  await page.goto('/login');
  const loginPassword = page.getByLabel('비밀번호', { exact: true });

  await composeInto(loginPassword, '한글');

  // 막히면 이미 한글 비밀번호로 가입한 계정이 로그인을 못 하게 된다.
  await expect(loginPassword).toHaveValue('한글');
});
