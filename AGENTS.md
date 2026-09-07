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
- Measured quantities/calculated results use Decimal/DECIMAL with scale 2.
  IDs, discrete counts, and whole-second intervals use integers. Follow the
  UTC storage convention and resolve API/rounding choices in the decision log.
- Production transitions and snapshot copying/immutability are Section 4
  service responsibilities. All entry paths must eventually use those writers.
- Use one branch/PR per section and update its acceptance evidence. Match CI
  results to the actual commit; never infer executed checks from job duration.
- At handover, update project status and affected docs, and state what was
  tested and what remains unverified. Do not merge/advance without the owner's
  section verification.
