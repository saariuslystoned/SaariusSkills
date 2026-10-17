# Status

As of **2026-10-17**, against the owner's isolated test store on the live
DinkusKit services. The screenshots and label PDFs stay on the owner's machine,
because they show private account details.

| Case | Result |
| --- | --- |
| Full run from a new Stripe TEST checkout | **Passed live, unattended.** The store opened Stripe's test Checkout, the test paid with the 4242 card, Commerce Orders showed the order paid and Processing, Ship made a Pitney Bowes sandbox label (USPS Ground Advantage, not charged) with a real PDF, Commerce's 5-minute check collected it on its own, and Commerce marked the order Completed with the same tracking number. The proof listed the store's plugins as Commerce 0.2.2 and Payments 0.2.8. |
| Commerce's 5-minute check collects the label | **Passed live**, about 2.5 minutes into the wait with nobody opening the store admin. It had failed because DinkusKit.com answered too slowly for EmDash's 5-second limit on the check; DinkusKit.com fixed that (dinkuskit#45), and Commerce gives the check 25 seconds from its next release (commerce#125). |
| Finish an existing paid TEST order | **Passed live, unattended.** Ship had the order, made a Pitney Bowes sandbox label, its tracking number and PDF matched, and Commerce Orders showed the order Completed with the same tracking. Both sign-ins used emailed links or codes the test read itself. |
| Opening Commerce Orders collects the label | **Passed live.** The label was collected as soon as the test opened Commerce Orders. |
| The thank-you page confirms the order and empties the cart | **Not yet passed; new step.** In the full run above, the shopper landed on "We couldn't confirm your order" with the item still in the cart, though the payment went through and Commerce recorded the order. The store's status route answered in a shape its own page couldn't read (template-store#92 fixes it). This step checks it from the next run on. |
| A checkout left pending by a failed run | **Passed live.** The next full run paid that checkout's own Stripe session instead of starting a second one, so one order took one payment. |

Update this page after each live run that changes a result. Never record sign-in
links, codes, store keys, private addresses or account identifiers here.
