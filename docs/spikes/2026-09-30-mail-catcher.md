# Spike: mail-catcher

Date: 2026-09-30   Timebox: 0.5 h, used 0.1 h (07:52 to 07:58 UTC)
Stopped because: answered
Location: none (registry queries and one local container run)
Prior work: none

## Question

Is the MailHog image the brief names still maintained, and is there a drop-in with the same SMTP (1025) and UI (8025) ports?

## Answered looks like

Last-updated dates for both images from Docker Hub, and a local run of the candidate printing its version.

## Operative inputs

- Brief: MailHog, UI :8025, SMTP :1025 (master prompt 10). Docker 29.7.2, x86_64 (this machine).
- Network here is slow (git clone ran at 77 KiB/s), so image size matters for a clean-checkout `docker compose up`.

## Answer

no: `mailhog/mailhog` was last pushed 2020-08-11 (145.5 MB). `axllent/mailpit` was pushed 2026-09-27 (13.7 MB), uses the same ports, and a copy (`public.ecr.aws/supabase/mailpit:v1.30.2`) already runs on this machine.

## Findings

| Time (UTC) | Finding | Evidence |
| --- | --- | --- |
| 07:55 | MailHog latest and v1.0.1 both last updated 2020-08-11, 145,545,376 bytes | Docker Hub tags API, `mailhog/mailhog` |
| 07:55 | Mailpit v1.31 updated 2026-09-27, 13,692,427 bytes | Docker Hub tags API, `axllent/mailpit` |
| 07:56 | Local Mailpit runs | `docker run --rm --entrypoint /mailpit public.ecr.aws/supabase/mailpit:v1.30.2 version` -> `v1.30.2 compiled with go1.26.4 on linux/amd64` |
| 07:56 | Postgres 16-alpine and 17-alpine images are already local | `docker images` |

Measured on: laptop.

## Not run or not measured

- MailHog was not pulled or run (145 MB on a slow link). Its behaviour is from its documentation: SMTP 1025, UI and API on 8025.
- Mailpit's REST API (`/api/v1/messages`) for e2e assertions was not exercised; it is documented upstream.

## Tried and discarded

- None.

## Recommendation

adopt Mailpit (`axllent/mailpit:v1.31`) as the SMTP test inbox, presented as "MailHog-compatible" in docs; decided at the Phase 3 checkpoint.

Reasoning: it is maintained, a tenth of the size, and the app code is identical (plain SMTP to port 1025). If judges or the brief insist on the MailHog name, swapping the image line is the whole change.

## Follow-up

- Task: "Compose service `mailhog` running the Mailpit image, ports 1025 and 8025" (tracker: none)
- ADR needed: yes (Phase 3)

## Throwaway

No code was written.
