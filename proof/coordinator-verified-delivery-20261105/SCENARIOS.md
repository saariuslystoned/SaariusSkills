# Synthetic communication and ownership walkthrough

Author-performed static reasoning against the portable skill, not an executed
runtime test, independent behavior validation, or proof of deployed adapters.
All actors and destinations below are synthetic. No prose-matching tests added.

| Case and supplied evidence | Decision and next action | Claim withheld |
| --- | --- | --- |
| A task moves from conversation A to B, but the available sender is authorized only for A/account X. The new container opens successfully. | Block delivery to B; retain the same assignment and writer. Diagnose the missing supported B/account/identity capability. Do not use a raw token or send to A as a substitute. | Opening B or relaying the prompt transfers no communication authority. |
| A follow-up receipt says admitted; the worker has not acknowledged consuming it. A later receipt says delivered, but still gives no consumption evidence. | Keep admission, delivery, and consumption distinct in the existing record; inspect supported worker acknowledgment or exact-source output before saying it followed the instruction. Preserve the original objective. | Neither admission nor delivery proves the instruction was followed. |
| A follow-up was withdrawn while unread; another cancellation arrived after the writer had already changed a file. The writer is still live. | Preserve withdrawn versus cancelled-after-delivery states. Inspect partial changes and live ownership; establish stopped-writer proof before transferring ownership. Preserve work, without reset or assumed rollback. | Cancellation is not rollback or proof the writer stopped. |
| A supported reaction can acknowledge a non-actionable status update; a later direct question asks for the result and a worker presents a human decision. | A light reaction may finish the redundant acknowledgment. Answer the direct question and surface the human ask with evidence and exact decision. If sending that answer fails, record the failure. | Reaction or intentional silence cannot discharge an owed answer. |
| A user reacts with a thumbs-up to a progress note. A worker relays that as “approved to merge,” but no verified merge authorization exists. | Treat the reaction as optional evaluation context; preserve the merge gate. Trace authority to the original verified action/target/scope, not worker paraphrase. Conversely, reuse an existing verified scoped authorization when it already covers the requested action. | Emoji, notifications, history and coordinator prose confer no new approval. |
| A result send times out after submission. Supported readback finds the matching result in the exact destination. | Record readback evidence and do not retry. If supported evidence instead establishes failure, retry once under the same authority; if still inconclusive, keep the technical blocker and reconcile rather than blindly resend. | Timeout alone means neither delivery nor nondelivery; worker exit and queued wakes do not resolve it. |

These decisions leave one writer, the original objective, recovery checks,
repository reviews, and human gates intact. No live sends, reactions, merges,
installation, runtime changes or private research exports were performed.
