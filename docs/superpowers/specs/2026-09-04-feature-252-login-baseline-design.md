# Feature 252 Login Baseline Design

## Scope

Implement the first reviewable screen for issue #252: Figma frame `A-2 login / 기본` (`616:167`) from section `09 Main 기준 재작성 / 2026.09.04` (`614:161`) in file `3qUR2z0rh6aYJfeJSxiUmg`.

This is a visual-system baseline, not a login behavior rewrite. Existing authentication requests, validation, error handling, session handling, and redirect behavior remain unchanged.

## Visual authority

The Figma frame is the visual source of truth. The implementation must use the existing React, TypeScript, Tailwind CSS v4, Radix, and shared UI patterns rather than pasting generated absolute-positioned markup.

Only the Light mode is implemented. Do not add a theme toggle or Dark-mode CSS.

## Required layout

- The mobile canvas is 390 × 844 in the review screenshot and remains centered on wider viewports.
- The screen surface is white (`surface/default`).
- Header: 64px tall, back affordance on the left, title `로그인 · 회원가입`, subtle bottom border.
- Authentication tabs: 350 × 48 at 20px horizontal gutter, subtle background, selected `로그인` tab on a white surface with teal text.
- Heading: `다시 만나서 반가워요`.
- Supporting copy: `로그인하면 저장한 복용약과 영양제를 이어서 볼 수 있어요.`.
- Email and password controls are 52px tall with 12px corners and `border/control` outlines.
- Supporting copy below password: `입력한 정보는 안전하게 보호해요.`.
- Password reset copy sits above the primary CTA.
- Primary CTA is 350 × 52 and says `로그인`.
- Footer contains only `이용약관 | 개인정보 처리 안내`; the RxVita logo and bottom navigation are absent.

## Light semantic tokens used by this screen

| Figma token | Value | Existing code alias |
|---|---:|---|
| `surface/canvas` | `#F7F9F9` | `background` |
| `surface/default` | `#FFFFFF` | `card` |
| `surface/subtle` | `#F2F4F5` | `muted-bg` |
| `text/primary` | `#202525` | `foreground` |
| `text/secondary` | `#596462` | `muted-foreground` |
| `text/tertiary` | `#6A7472` | new `tertiary-foreground` alias |
| `text/disabled` | `#879290` | `disabled-foreground` |
| `border/subtle` | `#E1E7E6` | `border` |
| `border/control` | `#879290` | `input` |
| `action/default` | `#077A74` | `primary` |
| `action/pressed` | `#055F5A` | `primary-strong` |
| `action/soft` | `#DDF4F1` | `primary-bg` |
| `action/content` | `#FFFFFF` | `primary-foreground` |

## Interaction and accessibility

- Existing login API call and error copy remain intact.
- Inputs keep their current accessible labels and browser autocomplete behavior.
- Interactive targets are at least 44px.
- Keyboard focus remains visible.
- The login/signup tab exposes selection with `aria-pressed` or the existing Radix selected state.
- No horizontal scrolling occurs at 390px.

## Review gate

After the implementation passes typecheck and the focused Playwright test, capture `/login` at 390 × 844. The user reviews that screenshot before any additional #252 screen is implemented.
