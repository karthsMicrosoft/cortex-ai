# Cortex Reminders & Tasks

Round 35 turns any note with a deadline into a Cortex task. There is no
separate task object: the note **is** the task, with `due_at`, `done_at`,
`priority`, `recurring`, and `reminder_sent_at` stored on `notes`.

---

## TL;DR for users

Write naturally — "submit expenses by tomorrow", "ship demo by Friday
#high", "pay rent by 6/10 #monthly" — Cortex detects the deadline as you
type, shows a confirmation pill, and saves the note with the reminder
attached.

You'll get a push notification (or email fallback) at the due time. Mark
done with one tap.

---

## How extraction works

1. You type in Capture.
2. `frontend/src/services/dateExtractor.ts` runs browser regex while you
   type.
3. Cortex renders a live pill like `📅 Tomorrow 11:59pm · High · Weekly`.
   The pill is only a preview — it never blocks save.
4. On save, the browser sends the note plus any extraction hints.
5. The backend stores trusted hints without overwriting user edits.
6. For voice transcripts, OCR, share-target notes, URL imports, and bulk
   imports, `backend/app/services/deadline_extractor.py` runs in the
   pipeline before the LLM.
7. `_auto_tag_and_categorize` is the fuzzy-phrasing safety net for things
   like "when I land" or "before our trip". It fills only fields regex
   missed.
8. NoteDetail and Library cards show an editable `DeadlinePill`; tap it to
   edit, clear, or mark done.

User edits always win. Every extraction layer has a non-overwrite guard.

### Supported phrasings (regex layer)

| Pattern | Example | Resolves to |
|---|---|---|
| `by today` | "Submit by today" | Today 23:59 local |
| `by tomorrow` | "Call John by tomorrow" | Tomorrow 23:59 local |
| `by EOD` / `by end of day` | "Reply by EOD" | Today 17:00 local |
| `by tonight` | "Pack by tonight" | Today 21:00 local |
| `by <weekday>` | "Ship by Friday" | This Friday 23:59, or next Friday if today is past it |
| `by next <weekday>` | "Ship by next Friday" | Next Friday 23:59 |
| `in N hours/days/weeks` | "Renew in 2 weeks" | Now + N units |
| `by M/D` | "by 6/10" | This year's 6/10 23:59 |
| `by M/D/YYYY` | "by 6/10/2027" | That date 23:59 |
| ISO date | "2026-07-15" | That date 23:59 |
| ISO datetime | "2026-07-15T14:30:00-07:00" | Exact |
| `by H am\|pm` | "by 5pm" | Today at that time |
| `by H am\|pm tomorrow` | "by 9am tomorrow" | Tomorrow at that time |
| `#p1` / `#high` | "Fix bug #p1" | `priority=1` |
| `#p2` / `#medium` | "Refactor #p2" | `priority=2` |
| `#p3` / `#low` | "Cleanup #p3" | `priority=3` |
| `#daily` / `#weekly` / `#monthly` | "Standup #weekly" | Recurring rule |

Anything fuzzier — "when I land", "before our trip" — is handled by the
LLM during the pipeline and appears within a few seconds of saving.

---

## Notifications

### Web Push (primary)

- Works on iPhone 15 Pro Max running iOS 16.4+ only when the PWA is
  installed to the home screen.
- Settings → Reminders → toggle **Enable reminder notifications**. The
  browser prompts once.
- Notifications open the relevant note when tapped.

### Email (fallback)

- Sent only when push fails or no subscription is registered.
- Backed by Azure Communication Services Email. Operator setup is below.

---

## Recurring tasks

`daily`, `weekly`, and `monthly` are the only recurrence rules in Round 35
(RRULE is deferred).

When the reminder fires, or when you tap Done, Cortex advances `due_at` by
the period and clears `done_at` plus `reminder_sent_at`. The next instance
is automatically queued.

---

## Operator setup (one-time)

### VAPID keys (Web Push)

1. Generate a VAPID key pair:

   ```powershell
   npm install -g web-push
   web-push generate-vapid-keys
   ```

   This prints `Public Key` and `Private Key`.

2. Set the Container App secrets:

   ```powershell
   az containerapp secret set --name cortexks-api --resource-group cortex-rg --secrets `
     vapid-public-key=<PUBLIC> `
     vapid-private-key=<PRIVATE> `
     vapid-subject=mailto:admin@cortex.app
   ```

3. Bind the secrets to env vars on the container revision:

   ```powershell
   az containerapp update --name cortexks-api --resource-group cortex-rg --set-env-vars `
     VAPID_PUBLIC_KEY=secretref:vapid-public-key `
     VAPID_PRIVATE_KEY=secretref:vapid-private-key `
     VAPID_SUBJECT=secretref:vapid-subject
   ```

4. The reminders dispatcher job needs the same env. The Bicep wires it
   automatically — re-deploy infra if you provisioned the job before adding
   the secrets.

### Azure Communication Services Email (fallback channel, optional)

1. Provision an ACS resource and connect an Azure-managed domain, or your
   own domain.
2. Grab the connection string and sender address.
3. Set `acs-email-connection` and `acs-email-sender` secrets:

   ```powershell
   az containerapp secret set --name cortexks-api --resource-group cortex-rg --secrets `
     acs-email-connection=<CONNECTION_STRING> `
     acs-email-sender=<SENDER_ADDRESS>
   ```

4. Add env vars on both the API container app and the reminders job:

   ```powershell
   az containerapp update --name cortexks-api --resource-group cortex-rg --set-env-vars `
     ACS_EMAIL_CONNECTION=secretref:acs-email-connection `
     ACS_EMAIL_SENDER=secretref:acs-email-sender
   ```

5. If you skip this step, reminders silently no-op the email channel. Push
   still works.

### Reminders dispatcher (Container Apps Job)

- Cron: `* * * * *` — every minute.
- Entrypoint: `python -m scripts.dispatch_reminders`.
- Provisioned via `infra/modules/container-app-job.bicep`; re-deploy infra
  after pulling Round 35.
- Manual run:

  ```powershell
  az containerapp job start --name cortexks-reminders --resource-group cortex-rg
  ```

- Logs:

  ```powershell
  az containerapp job logs show --name cortexks-reminders --resource-group cortex-rg --follow
  ```

Dispatch is race-safe: each job claims due notes with
`UPDATE notes SET reminder_sent_at = now() WHERE id = ANY(:ids) AND reminder_sent_at IS NULL RETURNING id`.
Web push goes first via `pywebpush` + VAPID. Push failures, missing
subscriptions, or deleted subscriptions fall back to email. HTTP 410 Gone
subscriptions are auto-deleted.

### Backfill existing notes

After deploy, fill in due dates for older notes:

```powershell
az containerapp exec --name cortexks-api --resource-group cortex-rg --command "python -m scripts.backfill_due_dates --email iamkarths@gmail.com"
```

---

## Privacy notes

- Push payloads contain the note title and a short snippet.
- Email payloads contain title and a content excerpt.
- Both stop the instant the user toggles reminders off in Settings or
  unsubscribes.

---

## Known limitations

- Recurring is `daily`, `weekly`, and `monthly` only this round.
- iOS web push requires the PWA to be added to the home screen.
- Time-zone extraction defaults to UTC until per-user time zones land in a
  future round.
- The browser regex is English-only; non-English phrasing falls through to
  the LLM.

---

_Round 35 — see PROGRESS.md for context._
