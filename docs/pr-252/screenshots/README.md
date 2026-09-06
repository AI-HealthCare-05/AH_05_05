# F screenshot evidence

Captured on 2026-09-05 with installed Google Chrome / Playwright, at viewport widths 375 and 390 px (height 844 px, Asia/Seoul timezone). These are deterministic fixture screenshots, not real patient records or live-backend acceptance evidence.

Home uses the existing `home-medication-compression.spec.ts` prescription fixtures through intercepted API responses in the real-API frontend build, with time fixed to 2026-08-25 12:00 KST. Chat and medication notes use the existing mock frontend and mock identity/data. No application files were modified for capture.

| Required state | 375 px | 390 px |
| --- | --- | --- |
| Home, one prescription | [image](375-home-1-prescription.png) | [image](390-home-1-prescription.png) |
| Home, three prescriptions | [image](375-home-3-prescription.png) | [image](390-home-3-prescription.png) |
| Home, expanded | [image](375-home-expanded.png) | [image](390-home-expanded.png) |
| Home, completed | [image](375-home-completed.png) | [image](390-home-completed.png) |
| H-5, positive evaluation | [image](375-H5-positive.png) | [image](390-H5-positive.png) |
| H-6, negative evaluation | [image](375-H6-negative.png) | [image](390-H6-negative.png) |
| E-8, notes list | [image](375-E8-note-list.png) | [image](390-E8-note-list.png) |
| E-9, note create | [image](375-E9-note-create.png) | [image](390-E9-note-create.png) |
| E-10, note edit | [image](375-E10-note-edit.png) | [image](390-E10-note-edit.png) |
| E-11, delete confirmation | [image](375-E11-note-delete-confirm.png) | [image](390-E11-note-delete-confirm.png) |

All 20 captured states passed the document-width overflow check (`document.documentElement.scrollWidth <= viewport width`). Both evaluation states at both widths kept the submit button inside the initial 844 px viewport. Capture checks verify fixture rendering and layout only; they do not demonstrate persistence through the real server. Screenshots are full-page captures, so tall forms can exceed 844 px in the saved image.
