# Standards

Standards are Ezra's durable, reusable rules for how the user wants things done (D-001).
This folder holds their **format**. The user's actual Standards are personal, so they live in
`standards/private/`, which is gitignored and never leaves this machine (D-013).

**Nothing reads these files yet.** Under D-008 the Standards library is built from evidence in
Phase 3. Until it's wired in, Standards here are a record, not something Ezra enforces.

## Layout

```
standards/
├── README.md                     this file (public)
├── templates/standard-template.md the format (public)
└── private/                      gitignored, local only
    ├── global/                   STD-G-*.md
    ├── departments/              STD-D-*.md
    ├── projects/                 STD-P-*.md
    └── CHANGELOG.md
```

## Rules

- **One requirement per file**, using the template's frontmatter and sections.
- **Severity** uses the single D-001 scale: `critical` (automatic fail), `major` (must be fixed
  before PASS), `minor` (a note, never blocks).
- **Source** keeps confirmed and inferred apart. `user_confirmed` means the user stated it;
  `learner_inferred` means Learner proposed it from patterns; `system_defined` means it comes
  from Ezra's own design. Nothing is written as `user_confirmed` unless the user said it.
- **Status:** every Standard starts as `draft`. It can only become `active` once it has a Guardian
  validation record (D-006), which doesn't exist until Phase 3.
- **Scope:** don't repeat a global Standard in a department or project file. Narrower scopes add
  rules or name an exception; they don't copy.
- **Versions are never edited in place.** A change makes a new version with `supersedes` set to
  the old one, and a changelog entry. Tasks record the versions they started with.

## Lifecycle (from Phase 3)

1. The user states a Standard, or Learner proposes one with evidence.
2. Guardian validates evidence and consistency with existing Standards.
3. Ezra activates it (D-006). An inferred Standard is a D-009 Level 2 change, so the user is told
   right away with a one-step rollback. A user-confirmed one goes in the daily digest (Level 3).
4. New tasks snapshot the active Standards that apply into their Acceptance Criteria.

## Changelog entry format

| Field | Example |
|-------|---------|
| Standard | STD-G-001 |
| Version | 1 → 2 |
| Date | 2026-11-20 |
| Change type | added · revised · deprecated · archived · rolled back |
| What changed | … |
| Why | … |
| Evidence | task ids or the user's words |
| Guardian validation | record id, or `none (draft)` |
| Status after | draft · active · … |
