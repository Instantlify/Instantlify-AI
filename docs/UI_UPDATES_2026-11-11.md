# UI updates — 11 November 2026

Implemented: inline community threads with persistent parent replies, non-destructive parent deletion, incremental reply loading and a compact composer; a themed language menu with keyboard support; owner-only XLSX workspace downloads with separate data sheets, frozen/filterable headers, formula-safe text and long-content continuation sheets. The Data & privacy headings still describe the export/deletion controls correctly.

Verification: frontend production build, TypeScript and ESLint passed; 6 browser checks passed using fixture APIs; 23 relevant backend checks passed, followed by 10 focused checks after refinements. The workbook was independently reopened with openpyxl in read-only mode. No customer emails were sent and no actual workspace exports or deletions were requested during testing.

Deployment pending: Docker engine API calls hang, even though Desktop processes run. Next.js reported a full C: drive. Removing only this project's generated `.next/dev/cache` recovered about 830 MB. Docker's normal restart timed out because its processes would not stop; no force-kill, volume removal or database reset was attempted.

After Docker recovers: build backend/frontend; apply `platform_ops.0014_communityreply_parent` before starting the new backend; recreate the backend/frontend services; verify their health. Existing replies migrate with no parent and remain visible. Existing completed export snapshots can be downloaded as Excel without recreating their snapshot. The encrypted snapshot storage and explicit legacy `format=json` API option remain available; the user-facing download is XLSX.
