# Regression findings — 2026-09-07

## Final result

Latest run after the delete-error toast focus fix:

| Chromium viewport | Passed | Failed |
| --- | ---: | ---: |
| 375 × 812 | 11 | 0 |
| 820 × 900 | 11 | 0 |
| 1440 × 900 | 11 | 0 |
| 1366 × 640 | 11 | 0 |
| **Total** | **44** | **0** |

`npm run test:e2e` now exits 0 and the previous snackbar/modal regression is resolved.

## Resolved issue

- Failed delete requests now close the native confirm dialog before the floating error snackbar is shown.
- The snackbar dismiss button is clickable in all tested viewports.
- Focus is restored to the originating chat-options trigger after dismissing the error toast.

## Passing coverage

- Library action/row alignment and body bounds at all requested sizes.
- Right-click, visible ellipsis, Shift+F10, arrow-key menu navigation, and Escape focus restoration.
- Individual chat/PDF and bulk history/library cleanup with correct scope.
- Quiz default follows navigated reader page; explicit page selection persists while reader page changes.
- Ten-question multiple-choice flow, reveal-without-credit behavior, and deterministic scoring.
- Quiz state retention across tool hide/show and tab switching.
- PDF/chat/quiz inner scrolling while control chrome stays fixed.
- Shift+Enter newline and Enter submit-once behavior.

## Notes

- All API mutations in frontend e2e remain isolated via mocked routes; no real backend data is mutated.
- Container/PostgreSQL validation is intentionally excluded from this document by request.