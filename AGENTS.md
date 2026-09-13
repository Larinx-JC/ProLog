# ProLog collaboration rules

Read [PROJECT_STATUS.md](PROJECT_STATUS.md), [docs/outline.md](docs/outline.md),
[docs/decisions.md](docs/decisions.md), and [CONTRIBUTING.md](CONTRIBUTING.md)
before continuing work.

- The owner requires a section approval gate. Implement only the authorized
  section. The authorization to advance has this form:
  "Yes, I verify the production of {completed section name} and you can
  proceed to the production of {next section name}".
  Ordinary requests can authorize planning and corrections within the current
  section. Do not reinterpret those requests or passing CI as section sign-off.
- Once a section or correction is authorized, finish its implementation,
  relevant tests, documentation, and PR preparation without repeatedly asking
  for permission for routine steps.
- Keep accepted decisions stable. Ask about unresolved product behavior before
  implementing it; proposed defaults are not owner decisions.
- Use the dedicated Anaconda environment `prolog`. Do not install project
  dependencies into base or add a standalone Python installation.
- Preserve user work. The design reference lives under
  `prototype/Production Dashboard Frontend/`; inspect git status and stage
  only intended files.
- Use reusable domain/service classes and shared UI components. Document each
  written function and test important success, rejection, and error behavior.
- Measured quantities/calculated results use Decimal/DECIMAL. Initial scale is
  2 except thickness in mm at scale 3; the owner requires Admin-configurable
  accuracy settings. Follow the current decision log for supported precision,
  policy scope, and rounding. IDs, discrete counts, and whole-second intervals
  use integers. Keep UTC storage and Asia/Shanghai factory presentation.
- Production transitions and snapshot copying/immutability are Section 4
  service responsibilities. All entry paths must eventually use those writers.
- Use one branch/PR per section and update its acceptance evidence. Match CI
  results to the actual commit; never infer executed checks from job duration.
- Before asking the owner to approve a section, review the entire section diff
  against its base, including implementation, migrations, tests, documentation,
  and agreed requirements. Rerunning checks or reviewing only the latest fix is
  insufficient. Present findings with severity, evidence, and remaining limits;
  after fixes, review the affected changes and rerun relevant verification.
- At handover, update project status and affected docs, and state what was
  tested and what remains unverified. Do not merge/advance without the owner's
  section verification.
