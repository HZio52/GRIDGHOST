# TrackShift reference and implementation alignment

Reference: https://hackculture.io/challenges/trackshift-2026
Read from the rendered official challenge page on 12 September 2026.

Selected theme: Energy & Overtake Intelligence. The page describes a deployment advisor that evaluates passing opportunities while balancing battery availability, later performance and constraints. This is the theme matching the existing team idea; the other two themes are separate projects and are not included.

| Theme need | Application implementation | Limit |
|---|---|---|
| Deployment recommendation | Four-action multi-stage planner | Assumed response model |
| Immediate vs later needs | Terminal buffer and deployment budget | Bounded 24s default, not a full-race optimizer |
| Overtake opportunities | Supplied windows and signed-gap scenarios | No geometry or validated probability |
| Operational interface | Pit wall, editable inputs, charts, replay, evidence | Local single-team prototype |
| Constraints | Auditable model-policy checks | FIA clauses not verified |
| Measurable comparison | Common-seed synthetic controller experiment | Not real-world causal validation |

The public event rules require significant code reuse to be disclosed. This release builds on the earlier AI-assisted backend prototype. The team should describe reused code, current additions, its own work and tool assistance accurately; this document does not determine event eligibility or organizer acceptance.

Visual reference: https://www.haasf1team.com/ (public website inspected on 12 September 2026). Red, white and black inform the visual palette. No private TGR Haas interface was accessed, and no familiarity with the team's actual internal tools is claimed. No team logo is used to imply endorsement.
