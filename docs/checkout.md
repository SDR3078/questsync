# Hosted-plan checkout page

A **static** landing + PayPal-subscribe page (`index.html`) for the hosted QuestSync
plan. It has no backend: PayPal's JS SDK creates the subscription entirely in the
browser, stamping the subscriber's identity into the subscription's `custom_id`.
[WardStone](../../wardstone) (private) binds the entitlement when PayPal delivers the
`BILLING.SUBSCRIPTION.ACTIVATED` webhook. **This page never talks to WardStone**, so
the open engine reveals nothing about the private billing backend.

## Files

| File | Purpose |
|------|---------|
| `index.html` | the page — self-host pitch + Habitica-ID field + PayPal subscribe button |
| `custom-id.js` | the **one** `custom_id` encoder, imported by both the page and the test |
| `custom-id.golden.json` | golden vectors **generated from WardStone's own codec** |
| `custom-id.test.mjs` | asserts the JS encoder reproduces every golden vector |
| `.nojekyll` | serve files verbatim (no Jekyll processing of `.js` / `.mjs` / `.json`) |

## Configure (both values are public — safe to commit)

Edit the `CONFIG` block at the bottom of `index.html`:

- `PAYPAL_CLIENT_ID` — your PayPal app's client-id (sandbox first).
- `PLAN_ID` — the subscription plan id (`P-…`).
- `PRODUCT` — leave `"questsync"`. **It must equal the product this `PLAN_ID` maps to in
  WardStone's `WARDSTONE_PAYPAL_PLAN_MAP`** (e.g. `WARDSTONE_PAYPAL_PLAN_MAP="P-xxxx:questsync"`).
  If they disagree, WardStone's `_resolve_link` cross-check fails and the payment is
  *parked*, not bound — the subscriber pays and gets no access.

## The codec contract (why the golden file exists)

The subscriber's Habitica User ID is stamped into `custom_id` as
`1|b64url(product)|b64url(subject)` (URL-safe base64, padding stripped). The browser's
encoder and WardStone's Python decoder must agree exactly, or people pay and silently get
no access. `custom-id.golden.json` is generated from WardStone's real
`encode_custom_id`, so the JS test passing is proof the two languages agree.

```bash
node docs/custom-id.test.mjs        # JS encoder matches WardStone's vectors
```

If the codec ever changes in WardStone, regenerate the golden file and both sides' tests
flag the drift.

## Publish (GitHub Pages, no Actions workflow needed)

Repo **Settings → Pages → Build and deployment**: Source = *Deploy from a branch*,
Branch = `main`, Folder = `/docs`. The repo is public, so free-plan Pages serves it. The
site is public (as intended — it's marketing); it exposes only the two public PayPal ids.

## Going live (gated — see session notes)

Sandbox is for clicking through the flow. Before real money: (1) create a **live** PayPal
plan and swap `ENV`/ids; (2) resolve the Habitica **ToS GO/NO-GO** — the API is silent on
paid token-brokering proxies, and their API guidelines' "reviewable in a public repo" rule
is satisfied by QuestSync (public) but WardStone is deliberately private; (3) use this page
itself as a **willingness-to-pay** smoke test first.
