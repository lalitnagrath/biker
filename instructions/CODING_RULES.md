# Architecture

- Service layer only
- Repository pattern
- No duplicated business logic
- SQLAlchemy ORM only
- Dependency injection where possible

# Database

- SQLite
- Alembic migrations
- No raw SQL unless necessary
- Database is the single source of truth

# Frontend

- Static HTML only
- Never query SQLite directly
- Use API endpoints only
- No business logic in templates

# Backend

- One responsibility per service
- Keep methods small
- Add type hints
- Add tests
- Reuse existing services before creating new ones

# Product Import

- Never modify Amazon data automatically
- Preserve original imported data
- Editorial data is stored separately
- Import must be idempotent

# Editorial

- Editors always have the final decision
- Never overwrite editorial choices
- Recommendations are suggestions only
- All recommendations must include a reason

# Code Quality

- Prefer extending existing classes over creating new ones
- Remove dead code
- No duplicate APIs
- Keep methods under ~100 lines when practical
- Document public methods

# Before Coding

- Search the project for existing functionality first
- Reuse existing code whenever possible
- Avoid adding new dependencies unless necessary
- Update docs/CURRENT_STATE.md after major work
- Update instructions/ROADMAP.md after each completed milestone