# Annotator select, rails, undo, and time

Approved 20 Sep 2026. Incremental upgrade; `App.tsx` stays orchestrator.

## Canvas
- Select tool: click a mask. Focused mask stronger in its class color; others dimmer outlines/fills.
- Class dropdown beside the focused mask (also after a new SAM2/brush mask). Save still writes class.
- Undo/redo: in-frame history including one step after Save (pixels + class). Not delete/tracking. Rounded-square buttons, short arc, large arrowheads. Ctrl+Z / Ctrl+Y.

## Rails
- Right: modern defect rows, From/To modern inputs, tracker card.
- Left: two-column thumbs, trash icon, styled number badges.

## Time
- `media.annotation_seconds`. Project total is the sum.
- Heartbeat while annotator is visible and not idle ~60s.
- Clock chip on project cards, video cards, live pulse in annotator header.
