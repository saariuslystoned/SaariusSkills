# Live Cursor ACP smoke proof

Outcome: passed
Route: /Users/bobbybones/.local/bin/cursor-agent acp
Model: cursor-grok-4.6-high
Disposable workspace: /var/folders/gf/qz1h4gs951b_qssp_gxmfpr80000gn/T/cursor-acp-live-p0Nv21

## Evidence

```json
{
  "workspace": "/var/folders/gf/qz1h4gs951b_qssp_gxmfpr80000gn/T/cursor-acp-live-p0Nv21",
  "route": "/Users/bobbybones/.local/bin/cursor-agent",
  "model": "cursor-grok-4.6-high",
  "readiness": {
    "ready": true,
    "model": {
      "requestedModel": "cursor-grok-4.6-high",
      "selectedModelId": "grok-4.6[effort=high,fast=true]",
      "currentModelId": "grok-4.6[effort=high,fast=true]",
      "availableModelCount": 38,
      "matchingModelIds": [
        "grok-4.6[effort=high,fast=true]"
      ]
    },
    "version": "2026.08.11-e8db854",
    "sessionOpened": true
  },
  "completion": {
    "jobId": "d6a42a33-d6a4-45ff-ac7d-41c7d54e5067",
    "status": "completed",
    "model": "grok-4.6[effort=high,fast=true]",
    "handoff": "I'll run `pwd` once in the supplied workspace and report the binding check without changing files or touching the network.**Workspace path:** `/private/var/folders/gf/qz1h4gs951b_qssp_gxmfpr80000gn/T/cursor-acp-live-p0Nv21`\n\n**Selected model:** Cursor Grok 4.6\n\n**Handoff:** Read-only binding check passed (`pwd` only); no files modified, no secrets or network accessed.",
    "proof": {
      "state": "/Users/bobbybones/.codex/worktrees/328f/SaariusSkills/runs/cursor-acp-delegation-20260918/live/state/runs/d6a42a33-d6a4-45ff-ac7d-41c7d54e5067/STATE.md",
      "events": "/Users/bobbybones/.codex/worktrees/328f/SaariusSkills/runs/cursor-acp-delegation-20260918/live/state/runs/d6a42a33-d6a4-45ff-ac7d-41c7d54e5067/events.jsonl",
      "proof": "/Users/bobbybones/.codex/worktrees/328f/SaariusSkills/runs/cursor-acp-delegation-20260918/live/state/runs/d6a42a33-d6a4-45ff-ac7d-41c7d54e5067/PROOF.md"
    }
  },
  "steering": {
    "accepted": true,
    "requestId": "b3cba5cf-b398-4654-ba40-31785febd3c3:steer:e4b0c01c-8a40-4c76-aaf3-79ab0d5d1881",
    "finalStatus": "completed",
    "proof": {
      "state": "/Users/bobbybones/.codex/worktrees/328f/SaariusSkills/runs/cursor-acp-delegation-20260918/live/state/runs/b3cba5cf-b398-4654-ba40-31785febd3c3/STATE.md",
      "events": "/Users/bobbybones/.codex/worktrees/328f/SaariusSkills/runs/cursor-acp-delegation-20260918/live/state/runs/b3cba5cf-b398-4654-ba40-31785febd3c3/events.jsonl",
      "proof": "/Users/bobbybones/.codex/worktrees/328f/SaariusSkills/runs/cursor-acp-delegation-20260918/live/state/runs/b3cba5cf-b398-4654-ba40-31785febd3c3/PROOF.md"
    }
  },
  "cancellation": {
    "requested": true,
    "finalStatus": "cancelled",
    "proof": {
      "state": "/Users/bobbybones/.codex/worktrees/328f/SaariusSkills/runs/cursor-acp-delegation-20260918/live/state/runs/283a35bf-8dda-4bb7-96c1-3ce6d48adf07/STATE.md",
      "events": "/Users/bobbybones/.codex/worktrees/328f/SaariusSkills/runs/cursor-acp-delegation-20260918/live/state/runs/283a35bf-8dda-4bb7-96c1-3ce6d48adf07/events.jsonl",
      "proof": "/Users/bobbybones/.codex/worktrees/328f/SaariusSkills/runs/cursor-acp-delegation-20260918/live/state/runs/283a35bf-8dda-4bb7-96c1-3ce6d48adf07/PROOF.md"
    }
  }
}
```



Raw ACP transcripts, thought streams, credentials, and auth logs are intentionally not recorded.
