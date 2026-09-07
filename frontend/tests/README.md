# Isolated Vue regression suite

Run `npm run test:e2e` from the frontend directory against the existing server at
http://localhost:5173. Install Chromium once with `npx playwright install chromium`
if needed. `npm run test:e2e:headed` shows the browsers; `npm run test:e2e:report`
opens the last HTML report. To run a subset, pass e.g.
`npm run test:e2e -- --project=phone-375x812` or `--grep "failed DELETE"`.

The default does not start or stop servers. Set `PLAYWRIGHT_START_SERVER=1` to
opt into starting/reusing Vite on localhost:5173. `PLAYWRIGHT_BASE_URL` can select
another existing frontend URL. No backend or credentials are needed.

Every test gets a fresh Chromium context and mutable in-memory mock store.
An automatic fixture installs a catch-all `page.route` **before navigation**.
API/fetch/XHR calls never pass through to a real server. Only same-origin GET
assets are allowed through; unexpected API calls and mutations are blocked and
fail the test. Service workers are disabled. No uploads, real accounts, real
documents, snapshots of user data, or backend mutations are used.

All scenarios run at 375×812, 820×900, 1440×900, and 1366×640. These are Chromium
viewport tests, not physical touch-device emulation or cross-browser coverage.
Below 901px, study tools intentionally overlay the reader; tests close that
panel using its visible close button before interacting with covered controls.
Dates, locale, timezone, mock content, and reduced motion are deterministic.
Two workers and zero retries make genuine failures visible.

Coverage includes library action geometry/body bounds; right-click, ellipsis and
keyboard chat menus; native delete confirmation and failed-delete toast hit
testing/dismissal; individual PDF/chat and bulk history/library cleanup; reader
page quiz defaults and explicit scopes; ten-question generation, answer locking,
reveal credit, incomplete scoring, hide/show and tab retention; PDF/quiz/chat
inner scrolling with stationary chrome; Enter versus Shift+Enter.

Screenshots at key states, per-test API-call attachments, failure screenshots,
failure traces, HTML reports, and machine-readable results are written only to
ignored `test-results/` and `playwright-report/`. Screenshots are diagnostic
artifacts, not pixel baselines. Internal PDF/quiz/chat/nav scrolling is permitted
and explicitly exercised; assertions prohibit **body** overflow, not all scrolling.

Not covered: real auth/upload/backend/LLM integration, speech synthesis, network
race/abort behavior, every API failure shape, quiz regeneration/reset, >100-page
picker pagination, drag resizing, and browsers other than Chromium. Failures are
not marked expected, retried into green, or repaired by changing app source.