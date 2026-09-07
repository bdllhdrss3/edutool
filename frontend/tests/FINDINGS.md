# Regression findings — 2026-09-07

## Final result

Two consecutive full runs of the final, unchanged suite each produced:

| Chromium viewport | Passed | Failed |
| --- | ---: | ---: |
| 375 × 812 | 10 | 1 |
| 820 × 900 | 10 | 1 |
| 1440 × 900 | 10 | 1 |
| 1366 × 640 | 10 | 1 |
| **Total** | **40** | **4** |

44 cases, two workers, zero retries, no skipped or expected-failure tests.
The final run took approximately 1.4 minutes and exited with code 1, correctly
preserving the confirmed UI regression. Chromium 153.0.8010.12 (Playwright
browser build v1243) was installed because the binary was initially absent.

## Confirmed bug: error snackbar is visible but cannot be dismissed over a modal

Reproduces at all four viewport sizes:

1. Open the options for the mocked “Understanding transactions” conversation.
2. Choose **Delete chat**, then confirm the deletion.
3. The mock returns HTTP 500 with “Mock deletion failed. Nothing was removed.”
4. The error snackbar renders visibly above the still-open native confirmation.
5. **Dismiss error** cannot receive pointer input. `elementFromPoint` at its
   center returns the confirmation dialog, and an ordinary Playwright click
   times out with “confirm-dialog intercepts pointer events.”

The toast host matches `:popover-open` and the confirmation matches `:modal`.
This is not a missing snackbar, clipped bounds, transient animation, or backend
failure to delete: it is modal interaction blocking despite visual top-layer
placement. The toast is outside the modal's DOM subtree. Rendering it in the
modal subtree or using an in-dialog error is a possible follow-up, not a change
made by this task.

The test's `finally` checks also confirm that Cancel remains enabled, restores
focus to the menu trigger, and preserves all three mocked conversations. After
the confirmation closes, the snackbar can be dismissed normally. Exactly one
mock DELETE request is recorded.

Evidence is available in the ignored HTML report and each failed test's trace,
`toast-hit-target` attachment, and `delete-error-over-modal` /
`delete-dialog-before-cancel` screenshots. The automatic failure screenshot is
taken after recovery, so use the named screenshots to inspect the open dialog.

## Passing coverage

- Library action/row alignment and body bounds at all requested sizes.
- Right-click, visible ellipsis, Shift+F10, arrow-key menu navigation, and
  Escape focus restoration.
- Individual chat/PDF and bulk history/library cleanup, related-chat removal,
  active-chat message clearing, unchanged unrelated data, and reload consistency.
- Quiz default follows a navigated reader page; explicit pages 1 and 3 remain
  selected after reader navigation; generation sends `question_count: 10`.
- Ten question controls; selection and locking; revealed correct answer earns
  zero credit; correct/wrong/unanswered statuses; cancelable incomplete submission
  and the expected 1/10 score with seven unanswered questions.
- Quiz question/answer/reveal state survives tool hide/show and tab switching.
- PDF, quiz, and chat inner scrolling leaves their tested header/footer/composer
  bounds fixed, without body overflow. Internal scrolling is intentionally allowed.
- Shift+Enter inserts a newline; Enter sends the multiline message exactly once;
  empty Enter sends nothing.
- No unhandled mock API calls or uncaught browser errors in the final runs.

## Harness corrections, not UI bugs

The initial browser launch required installing Chromium. Initial tablet tests
also tried to click reader controls behind the intentionally overlaid tools
panel. The tests now use that panel's visible close button before reader
navigation, rather than force-clicking or changing application layout.

Standalone strict TypeScript checking of the Playwright config/helpers/fixtures/
spec passed, and editor checks reported no errors in the new TypeScript files.
Git ignore checks confirmed that results and HTML reports are ignored. No app
component, stylesheet, backend, package lock, or existing user data was changed
by this task; all API mutations were fulfilled by the isolated mock fixture.

## Untested

Real authentication, uploads/PDF parsing, backend or model integration, speech,
network races/abort handling, other DELETE error shapes, reset/regeneration,
large page-picker pagination/limits, drag resizing, physical touch behavior,
Firefox and WebKit. The normal application build was not rerun; the prior clean
build was supplied as context, not claimed as a new result here.