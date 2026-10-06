# Local job pipeline

## What runs on the Mac

- `com.jsbasics.jobpipeline` runs the scraper and scores at most 24 recent jobs every two hours. It only analyzes jobs first seen in the last three days and does not tailor resumes.
- `com.jsbasics.selectedworker` watches the selection queue. Selecting a job from the review page triggers resume tailoring and PDF generation; matching previously tailored roles reuse their existing output.
- `com.jsbasics.applicationworker` opens queued employer applications in Chrome, fills known fields and the tailored resume, and waits for explicit approval in the review page. It submits only a clean, single-page form on supported ATS platforms.
- `com.jsbasics.jobreview` serves the private review page on `127.0.0.1:8765`.
- `com.jsbasics.keepawake` keeps macOS awake while the Mac is connected to power. Leave the lid open and the charger connected.

## Install or reload the local services

From this repository, run:

```zsh
./install_local_services.sh
```

The script stores generated review credentials in the ignored `.env` file with owner-only permissions. The username is `jobs`; read `REVIEW_PASSWORD` from that local file when signing in. Never commit `.env`.

The scheduled scraper uses Indeed, Google, and LinkedIn through JobSpy. LinkedIn detail fetching is enabled because JobSpy can sometimes extract an outbound employer/ATS application URL from a LinkedIn posting. LinkedIn states that third-party tools may not scrape or automate activity on its site; using this source may violate its terms or risk account restrictions. JobSpy may also be blocked or omit the direct apply URL, in which case the review page keeps the LinkedIn posting link and the worker cannot start the employer form automatically.

To bring in a LinkedIn posting you found yourself, paste its URL, title, company, and optional location into **Match a LinkedIn job**. The Mac worker searches Indeed and Google Jobs for that company and title, accepts only an exact normalized company and a close title match, then scores the external posting. A direct employer link from LinkedIn detail fetching or an external match is preferred for application preparation.

## Open the review page from your phone

Install Tailscale on the Mac and phone and sign both into the same tailnet. On the Mac, configure Tailscale Serve to expose only the local review service:

```zsh
tailscale serve --bg http://127.0.0.1:8765
tailscale serve status
```

Open the private HTTPS tailnet URL shown by `tailscale serve status` on your phone and sign in with the credentials in `.env`. Tailscale Serve is private to the tailnet; do not use Tailscale Funnel or expose port 8765 publicly.

## Application flow

1. Select a job to prepare its tailored resume.
2. For a job with a direct employer/ATS link, select **Prepare application**. Chrome opens on the Mac, follows any Apply step on that employer site, fills known profile fields, and uploads the tailored resume.
3. Review the filled-field report and screenshot in the private phone review page. **Approve & submit** appears only for supported forms with no unanswered or unrecognized fields. The worker submits only after that approval.
4. Workday advances through clearly labeled steps only when detected fields are filled; it stops on a step with unanswered/unknown fields or an interstitial. Workday submission still requires a clean final form and your approval. Jobs without a direct employer link remain manual; the worker starts from the captured external ATS link rather than navigating LinkedIn.

Keep the Mac awake, signed in, connected to power, and online while the worker runs. Phone access through the review page requires Tailscale installed and signed in on both devices, then Tailscale Serve configured as above. The autofill profile has a street-address value saved as provided; verify it is complete before applying. Review the saved standard answers in `autofill_profile.json` for accuracy before using approval.
