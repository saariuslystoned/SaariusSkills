# Browser Automation Verification Matrix

This document defines the 6 mandatory capability verification categories for the `/browser` skill.

## Capability Matrix

| Category | Target Elements & Interactions | Expected State & Verification Criteria |
| :--- | :--- | :--- |
| **1. Text Typing & Input** | - Agent Codename input<br>- Direct Comm Channel email input<br>- Multiline Tactical Directives textarea | Keystrokes dispatched cleanly; DOM input values match target string; telemetry log records change events. |
| **2. Checkboxes, Radios & Dropdowns** | - Operational Paradigm dropdown (`select`)<br>- Spectral Theme Matrix radio group (`radio`)<br>- Subsystem Capabilities multi-select (`checkbox`) | Values and checked attributes toggle correctly; UI styling updates to match theme; change events emitted. |
| **3. Action Buttons & Clicks** | - `⚡ Apply Directives` button<br>- Brush style selector buttons<br>- Vector preset buttons (`Draw Starburst`, `Cyber Spiral`) | Button click triggers dynamic HUD synchronization, state badge update (`NEURAL-SYNC: ACTIVE`), and canvas triggers. |
| **4. Drag & Drop Interaction** | - Drag `🔐 Cryptographic Security Key`<br>- Drop onto `⬇ Drop Security Key Here to Authorize Matrix` | Drop event handled; security token parsed; target updates to `✅ MATRIX AUTHORIZATION VERIFIED [TOKEN_779 ACCEPTED]`. |
| **5. Vector Canvas Rendering** | - HTML5 2D Vector Canvas<br>- Multi-point radiant starbursts<br>- Cybernetic Archimedean spirals<br>- Neural resonance nodes & glowing beams | Canvas render context produces 150+ vector strokes; glowing bloom effects applied; stroke count HUD increments. |
| **6. Visual Proof Capture** | - Full-page viewport screenshot | Screenshot captures clean visual evidence of all previous five categories in their terminal verified state. |
