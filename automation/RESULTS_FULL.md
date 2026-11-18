# RESULTS_FULL.csv

`RESULTS_FULL.csv` reconstructs one row for every current smoke, core, and
official case in `RESULTS_CURRENT.csv` (46 rows: 10 smoke, 30 core, 6
official). Functional/exact status is taken from `RESULTS_CURRENT.csv`;
timing, iteration, and phase fields are reconstructed from preserved run
directories, proof packages, and logs.

Standalone `add`/`mul`/`rem` rows are intentionally omitted. Their current
proofs are the smoke/core counterparts: the smoke `mul` row includes a
separately measured 6.99 s final contract check, and the core `rem` row has a
known 8.5 h no-activity plan gap removed and carries the former `rem` attempt
history (17 iterations).

Counts: **46 rows, 35 functionally proved, 11 open.**

## What the columns mean

### Identity and status

| column | meaning |
|---|---|
| `tier`, `family`, `case`, `function` | current case identity |
| `functional_status` | current functional result (`proved` or `open`) from `RESULTS_CURRENT.csv` |
| `exact_status` | current exactness result from `RESULTS_CURRENT.csv` |
| `evidence_class` | evidence class from `RESULTS_CURRENT.csv` |
| `evidence_package` | current selected evidence package/run |

### Attempts and time to induction

| column | meaning |
|---|---|
| `iterations` | number of preserved proof attempts counted for this row. Includes failed baseline/full-budget attempts and build-only attempts. Each final logs-only package counts as one attempt. |
| `iterations_source` | how `iterations` was formed, including attempts with no recorded wall time |
| `time_to_induction_s` | elapsed proof time from the first counted attempt through the final `proved`/`ACCEPT` attempt, in seconds. Blank when induction was not reached. |
| `time_to_induction_class` | `measured`, `measured_lower_bound`, or `not_reached` |
| `time_to_induction_source` | how the time was reconstructed |
| `time_to_induction_note` | case-specific caveats, including the user's recollection for hard cases |
| `time_to_induction_user_estimate_s` | explicit user recollection where available (`mulh`: 36,000 s = 10 h); not a measured value |
| `time_spent_known_s` | sum of all known attempt walls. For open rows this is the cumulative effort spent, not a time to induction. |
| `attempts_without_timing` | counted non-build proof attempts for which no wall time was preserved. Build-only attempts still count in `iterations` but do not by themselves make the row a lower bound. |

`time_to_induction_s` is a sum of recorded attempt walls plus the final
logs-package active window. It is not a calendar span across days. Attempts
without timing make the value a lower bound; those rows are marked
`measured_lower_bound`.

### Final-attempt phase split

These fields describe the **final accepted attempt** (or the last preserved
attempt for an open row where one is available).

| column | meaning |
|---|---|
| `final_attempt_wall_s` | wall time of the final attempt |
| `final_attempt_source` | run directory or logs package used for the split |
| `build_s` | build/elaboration time from `build.json`; blank when not preserved |
| `plan_s` | planning, decomposition, helper/sketch construction, and refinement time |
| `engine_wall_s` | wall time of engine execution |
| `engine_compute_s` | engine-reported BMC + induction compute time; may exceed `engine_wall_s` when engines run concurrently |
| `bmc_s` | BMC portion of engine compute; 0 when no BMC engine was run |
| `induction_s` | induction/k-induction/IC3 portion of engine compute |
| `check_s` | certificate/kernel check duration; blank when the logs package does not record it |
| `other_s` | residual time inside the final attempt, including report/audit or post-log package finalization |

For structured runs the phases are normalized to be additive to
`final_attempt_wall_s`. When an older report measured `engine_wall_seconds`
over a window that also covered build/plan/check, the engine wall was reduced
to the residual; this is why `engine_wall_s` can differ slightly from
`report.json.timing.engine_wall_seconds`.

`engine_compute_s` is the sum of engine-reported per-run times, so it can
exceed `engine_wall_s` when engine runs overlap. For `smoke_nerv_reg`, the
final package runs two IC3 properties concurrently: 163.46 + 169.94 =
333.40 s compute against 170.00 s engine wall.

For logs-only packages, `plan_s = final_attempt_wall_s - engine_wall_s -
other_s`. `other_s` is the gap between the last cill log and package
finalization. It is **not verified as certificate-check time** and is labelled
as such in `missing_reason`.

### Legacy fields

`old_time_s`, `old_engine_s`, `old_tried`, `old_inv`, and `old_attempts` are
copied from the older `RESULTS.csv`/`SUMMARY.csv` for traceability. They used
looser backend checks and are not the authority for the current statuses.
For smoke rows `old_time_s` is the old cumulative smoke attempt time; for core
rows it is usually the old final-attempt wall. The two are not directly
comparable.

## Reconstruction method

1. **Status is not reconstructed.** Every row keeps the `functional_status`,
   `exact_status`, `evidence_class`, and `evidence_package` from
   `RESULTS_CURRENT.csv`.
2. **Attempt inventory.** Attempts were collected from:
   - `pcd/runs/**/run.json`
   - `pcd/experiments/case_binding_eval/results-20261103/`
   - `pcd/experiments/case_binding_eval/fullbudget-20261104/`
   - `pcd/experiments/case_binding_eval/lui-ic3-20261104/`
   - `pcd/experiments/case_binding_eval/lb-confirmed-20261103/`
   - logs-only packages under `pcd/experiments/formal_reproof/`
   Historical copies (`historical-*`) were excluded to avoid double counting.
3. **Structured attempts.** For runs with `report.json`/`run.json`, the wall
   time is `report.timing.wall_seconds` when available, otherwise
   `run.wall_seconds`. `plan_s` is the gap from build completion to the first
   engine statistic start. `check_s` is `check.json` mtime minus
   `discharge.json` mtime when the mtimes are usable.
4. **Logs-only attempts.** The active window is the earliest cill log
   timestamp through `generation.json.generated_at` (or the latest
   `check.json`/`proof.json` mtime when no generation time exists). Log
   timestamps are UTC; file mtimes are local (+08:00). Engine wall is the sum
   of per-log wall times, capped to the active window when logs overlap. BMC
   and induction values are summed from `CIll Statistic` lines when present.
   For rIC3 IC3-only logs that do not emit `CIll Statistic`, the per-property
   `Statistic { time: ... }` values (or `generation.json.engine_runs[].seconds`)
   are summed as induction time, and `bmc_s` is 0 because no BMC engine was run.
5. **No fresh engine runs.** All values are from preserved artifacts. Missing
   values are left blank and explained in `missing_reason`; they are not
   imputed.

## Main results

- Proved rows: 35. Median measured time to induction: **677.4 s** (about 11
  minutes). Range: 82.6 s to 183,468.9 s.
- Simple smoke/core/official rows are mostly in the **hundreds to low
  thousands of seconds**.
- Hard cases:

| row | iterations | time_to_induction_s | class | note |
|---|---:|---:|---|---|
| smoke `serv` `reg` | 338 | 183,468.9 | measured_lower_bound | full 14-run search; 49,258.5 s active wall, 176,488.0 s (49.0 h) engine compute, 12,383.5 s planning/refinement; 203.9 h calendar span including idle |
| core `rem` | 17 | 28,196.3 | measured_lower_bound | merged former `rem` attempts; about 7.8 h after removing an 8.5 h no-activity plan gap |
| smoke `mul` | 12 | 17,101.6 | measured | includes a measured 6.99 s final contract check |
| official `mulh` | 3 | 15,615.2 | measured_lower_bound | measured lower bound; user recollection about 10 h |
| core `div` | 5 | 11,168.9 | measured | about 3.1 h |
| core `mulh` | 9 | 10,102.4 | measured_lower_bound | measured lower bound; user recollection about 10 h |
| core `remu` | 5 | 4,522.3 | measured | about 1.26 h |
| official `divu` | 3 | 3,127.2 | measured | about 52 min |

The measured `mulh` values are below the user's recollection of about 10 h.
The user estimate is preserved separately in
`time_to_induction_user_estimate_s=36000` rather than overwriting the measured
lower bound.

Smoke `serv` `reg` is the largest search in the table. The full history has
**338 engine logs over 14 run directories**, including failed and superseded
obligation sets. Cumulative attempt wall is **183,468.9 s (51.0 h)**; the
active session span is **49,258.5 s (13.7 h)**; aggregate engine compute is
**176,488.0 s (49.0 h)**; and non-engine active planning/refinement is
**12,383.5 s (3.4 h)**. The final 96-replay package alone is 3,343 s wall and
70,396.2 s compute. The 203.9 h calendar span includes idle time and is not
used as the wall-time value.

## Known limitations

- Some historical attempts have no wall time; rows with such attempts are
  marked `measured_lower_bound`.
- Logs-only packages do not record build or certificate-check durations.
  `plan_s` and `other_s` are derived from log gaps and package finalization.
- `other_s` for logs-only packages is not a verified certificate check.
- The smoke `serv` `reg` row is a **full-search aggregate**, not a single
  final logs package. Its `engine_compute_s` sums 338 per-log engine times
  (176,488.0 s); `engine_wall_s` is the union of engine-active intervals
  (36,553.0 s); `plan_s` is the remaining non-engine active time
  (12,383.5 s); `other_s` is the final-package finalization gap (322 s). Nine
  logs have no timestamps, so the wall fields are lower bounds.
- The smoke `serv` `reg` final 96-replay package alone is 3,343 s wall and
  70,396.2 s compute; those values are retained in the case note rather than
  the aggregate row fields.
- The smoke `mul` row adds a separately measured **6.99 s** final contract
  check of the existing proof package. It is not part of the original cill log
  window.
- The core `rem` row subtracts **30,600 s (8.5 h)** from `plan_s` for a known
  no-activity gap. This is a manual correction, not an artifact-derived value.
  It also merges 12 former standalone-`rem` proof attempts; because those
  attempts have no wall time, the corrected time is a lower bound.
- Standalone `add`, `mul`, and `rem` rows are omitted; their current proofs are
  represented by the smoke/core rows named above.
- Open rows have no `time_to_induction_s`; their `time_spent_known_s` is the
  cumulative known effort, not a time to induction.
- Old `RESULTS.csv`/`SUMMARY.csv` values are included only for traceability and
  may use looser backend checks.

## Validation

- 46 data rows and 33 columns.
- 35 `proved`, 11 `open`.
- 10 smoke, 30 core, 6 official.
- No proved row has a blank `time_to_induction_s` or `final_attempt_wall_s`.
- No open row has a `time_to_induction_s`.
- Final-attempt phase fields sum to `final_attempt_wall_s` within rounding.
