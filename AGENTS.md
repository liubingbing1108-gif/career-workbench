# Career Workbench contributor instructions

Read README.md, docs/PRODUCT_REQUIREMENTS.md, docs/HANDOFF_CONTEXT.md, docs/AGENT_INTEGRATION.md and SECURITY.md before changes. This is a standalone local application. The latest user instructions take priority; historical prototypes do not define a second product.

Preserve the two main views: profile and application management, with a per-job preparation workspace. One job is an independent application. Store original source and verified official destination separately. Preview chosen records before insertion; only explicit application intent enters management. Do not auto-mark submitted or invent recruitment dates.

Education is a website-scoped complete set; internships are selected records with per-record versions and order. Never confuse records with alternative versions. Temporary application edits default to application-only. Attachments are the selected original bytes; no substitute files or fake uploads.

Use the existing executor protocol v1. Validate model references, scan actual controls, protect manual changes, separate filled/verified/save acknowledgement/persisted results. Unknown fields or website constraints must be explicit. Login, CAPTCHA, agreements and final submission belong to the user. No arbitrary script/click or final-submit endpoint.

Only test with fictional data and temporary databases by default. Never inspect, upload or commit another user's .runtime, credentials, resumes, screenshots or application URLs. Any real-site test requires that user's authorization and confirmed materials. New users initialize once; never replace an existing runtime with an empty database.

Run python scripts/run_tests.py (and --ui for interface changes), python scripts/check_docs.py and the publication privacy check. Keep documentation current; record limitations without turning suggestions into confirmed features. The owner has selected MIT and authorized public source releases; personal runtime and evidence remain excluded.


## Repository management contract

Read [GOVERNANCE.md](GOVERNANCE.md), [capability catalog](docs/CAPABILITIES.json) and [Agent playbook](docs/AGENT_PLAYBOOK.md). Reuse the listed implementations; do not duplicate a database, executor or authoritative specification. Every PR needs a new `.changes/<UTC timestamp>-<slug>.json` covering all changed paths, actual validation and compatibility impact. Do not rewrite old fragments. Run `python scripts/check_project.py`, and in the public Git checkout also `python scripts/check_project.py --base <full PR base SHA>`. Planned/partial capability status must not be reported as fully supported. Runtime Agent compatibility requires separate acceptance; reading instructions alone does not establish it.

## Every task and resumed conversation

Before editing, run `python scripts/project_handoff.py status` and read the current [activity index](docs/PROJECT_ACTIVITY.md), handoff, roadmap and affected specifications. Follow [CONTINUITY](docs/CONTINUITY.md): begin a scoped task before writes; record actual changes, validation, status and next steps before handing back or pausing. The command synchronizes the project index. This is the Agent’s standing responsibility; do not wait for repeated user reminders. Check failures remain explicit. Existing tasks must reread current files rather than reuse stale chat context. These commands are development-only; do not change runtime behavior or authorization.
