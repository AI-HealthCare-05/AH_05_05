# Dashboard Chat Response Statistics Design

## Goal

Replace the hard-coded AI chatbot dashboard card with statistics derived from chat data and add a five-star satisfaction visualization backed by `chat_sessions.score`.

## Data model

- Add nullable `score` to `chat_sessions` because a session can exist before a user submits a rating.
- Store integer ratings from 1 through 5.
- Set the database/model description to `채팅 별점`.
- Add an Aerich schema migration. Existing sessions remain valid with `NULL` scores.

## Statistics

- Only `chat_messages` whose role is `ASSISTANT` participate in response counts.
- Only terminal messages completed during the selected dashboard period participate.
- `total` is `COMPLETED + FAILED`; pending and streaming messages are excluded.
- `completed` counts `COMPLETED` assistant messages.
- `failed` counts `FAILED` assistant messages.
- Satisfaction is the average of non-null `chat_sessions.score` values for sessions created during the selected period.
- The average is rounded to one decimal. With no rating, the API returns `null`.

## API and UI

- Extend `GET /api/v1/admin/dashboard/summary` with `chatResponses`.
- Replace fixed card values with API-backed total, completed, and failed counts.
- Replace `자동 해결률` with `챗봇 만족도`.
- Render five stars, including a proportional fill for fractional averages, and also display `N.N / 5.0`.
- With no rating, show empty stars and `데이터 없음`.
- Display the copy `챗봇 사용자의 별점 평균을 나타냅니다.`.

## Scope

This change does not add an endpoint for users to submit a rating. It adds storage, migration, dashboard aggregation, and dashboard rendering only.
