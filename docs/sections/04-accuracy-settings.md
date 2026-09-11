# Measurement & Accuracy Settings

Status: owner-added scope, 2026-09-08. Backend implementation belongs to
Section 4; production endpoints to Section 5; the new Admin page to Section
11D. This extends the supplied prototype. The Section 4 backend and migration
are implemented, reviewed and CI verified; the API and page remain scheduled
for their approved later sections. See [implementation](../run-lifecycle.md).

## Confirmed behavior

- Use maximum individual-point target deviation for the alarm; show maximum
  variation about the four-point mean separately as uniformity.
- Factory-wide decimal-place settings; material-specific alarm limits.
- Initial scales: resistance 2, thickness 3, speed 2, measured length 2,
  calculated results 2. Scales may be set to integers from 0 through 6.
- Admin chooses half-up (initial default) or half-even rounding.
- Transfer physical quantities/results as decimal strings. Reject input beyond
  the configured scale. Compare alarm limits before rounding calculated results.
- Each new run captures the effective accuracy policy, including rounding;
  later changes preserve existing runs. Material detection rules retain their
  existing full run snapshot.
- Initial target-deviation tolerance is 2.00%, adjustable by Admin per material.
- Thickness values such as 0.006 mm must survive entry, storage and readback.

## Admin page

Provide a Measurement & Accuracy Settings entry in the Admin navigation.
Show each quantity's unit, decimal places and an example value; show the
rounding choice with halfway examples. Reuse the material editor for target,
upper/lower resistance limits, thickness limits, deviation tolerance and check
switches. Uniformity is informational, not an additional enabled alarm.

On save, validate supported scales and existing material-rule compatibility,
then persist the new policy and audit actor, server time and before/after
settings atomically. Show which policy new runs will use. Existing runs and
their exports use their captured policy. Do not silently modify material
standards to fit a lower precision.

## Types and storage direction

| Value | Type / rule |
| --- | --- |
| Decimal places | Integer 0–6, independently selected per quantity group |
| Rounding mode | Controlled choice: half-up or half-even |
| Measurements and thresholds | Python Decimal / MySQL DECIMAL; no binary-float conversion |
| API quantities | Decimal strings formatted according to the run policy |
| IDs, versions, intervals, sample counts | Integer |
| Policy/audit event times | Authoritative server UTC; display Asia/Shanghai |

Migration `b6d84e19a203` widens numeric storage to `DECIMAL(24,6)` so six-place
settings can be used without changing tables from the Admin page. Physical
input retains eight integer digits; calculated results have extra capacity
for percentages against very small targets. MySQL DECIMAL scale
sets its stored fractional capacity; a form setting alone cannot increase it.
See [MySQL's exact numeric types](https://dev.mysql.com/doc/refman/8.4/en/fixed-point-types.html).

Store policy versions immutably and reference the effective version from a
run. A current-policy pointer selects defaults for new runs. Existing records
need an explicit legacy policy preserving their original scale and computation
meaning; do not relabel historical prototype values or recalculate old results
under the new formula. Narrowing a database on downgrade must reject data that
cannot be represented exactly, instead of silently discarding fractional digits.

An additional current operational switch lets Admin enable/disable Operator
work on their own Abnormal runs. Its initial value is enabled. Unlike captured
numeric policy, this permission switch is checked against current settings on
every write and takes effect immediately for existing runs.

## Class/data flow and delivery sections

```mermaid
flowchart LR
    Admin[Admin settings page - Section 11D] --> API[Settings API - Section 5]
    API --> Service[AccuracySettingsService - Section 4]
    Service --> Policy[Immutable accuracy policy]
    Service --> Audit[Audit log in same transaction]
    Policy --> Run[RunService captures policy and material rules]
    Run --> Measurement[MeasurementService validates and calculates]
    Measurement --> Detector[Target and limit checks before rounding]
    Measurement --> Result[Results formatted with run policy]
    Result --> Readers[Screens, search and exports]
```

Share the numeric policy and calculators across manual and future automated
entry. Settings updates and run creation must use a consistent transaction
lock order so a run never sees a partially changed policy.

## Acceptance additions

1. Admin-only settings writes; Operators/Reviewers cannot bypass authority.
2. Verify scales 0, 3 and 6, invalid scales and invalid rounding choices.
3. Preserve 0.006 mm and 0.008 mm exactly in real MySQL and API serialization.
4. Show that a policy change affects a new run while an existing run keeps
   its entry validation, calculations, formatting and historical audit meaning.
5. Reject precision decreases incompatible with current material standards;
   do not silently round those standards or measurements.
6. Verify half-up/half-even halfway results and alarms just inside/on/outside
   a boundary before display rounding.
7. Test settings-update versus run-start races, stale updates, retry deduplication
   and rollback if auditing or persistence fails.
8. Test populated upgrade, legacy interpretation, drift and lossless downgrade
   behavior against MySQL. Update the schema and operating documentation.

Confirmed lifecycle choices are recorded in the main
[Section 4 plan](04-run-lifecycle.md) and [decision register](../decisions.md).
