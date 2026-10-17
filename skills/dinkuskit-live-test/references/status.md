# Status

As of **2026-10-17**, against the owner's isolated test store on the live
DinkusKit services. The screenshots and label PDFs stay on the owner's machine,
because they show private account details.

| Case | Result |
| --- | --- |
| Finish an existing paid TEST order | **Passed live, unattended.** Ship had the order, made a Pitney Bowes sandbox label (USPS Ground Advantage, not charged), its tracking number and PDF matched, and Commerce Orders showed the order Completed with the same tracking. Both sign-ins used emailed links or codes the test read itself. |
| Opening Commerce Orders collects the label | **Passed live.** The label was collected as soon as the test opened Commerce Orders. |
| Commerce's 5-minute check collects the label | **Failing on the test store.** The label waited until Commerce Orders was opened. This is a Commerce bug under investigation, not a test fault. |
| Full run from a new Stripe TEST checkout | **Not yet passed live.** The checkout leg hasn't run live yet. |

Update this page after each live run that changes a result. Never record sign-in
links, codes, store keys, private addresses or account identifiers here.
