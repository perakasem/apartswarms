# Selection against safety: computed results

This report is generated from completed run logs. It makes no claim that synthetic baselines are LLM observations.

Completed run records: **1920**. Excluded incomplete runs with logged outcomes: **0**. Next-assignment horizon: **5**. Bootstrap resamples: **1000**.

Intervals are percentile 95% run-cluster bootstrap intervals within condition, unadjusted for multiple comparisons. Different coordinators and conditions can share environment seeds, so the overall run count is not a count of mutually independent observations. These intervals describe this exploratory sample; they are not confirmatory hypothesis tests. Runs that failed before logging any outcome are absent here; inspect execution_summary.json and status files for all API failures.

| Coordinator | ρ | c | π | Feedback | Runs | Careful late − early (pp) | Expected violations | Realized violations | Task-type interaction (pp) |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| bayesian | 0.0 | 5.0 | 0.15 | outcome_only | 20 | -2.0 pp [-9.5, 5.0] | 8.8% [8.2, 9.3] | 8.1% [6.3, 10.1] | -1.8 pp [-8.2, 5.8] |
| bayesian | 0.0 | 5.0 | 0.15 | reason_visible | 20 | -5.5 pp [-11.8, 0.8] | 9.2% [8.7, 9.8] | 8.2% [6.8, 9.8] | -5.2 pp [-10.8, 1.0] |
| bayesian | 0.0 | 5.0 | 0.35 | outcome_only | 20 | -14.5 pp [-21.8, -7.3] | 23.0% [21.1, 24.7] | 21.9% [19.3, 24.4] | -11.0 pp [-17.7, -4.7] |
| bayesian | 0.0 | 5.0 | 0.35 | reason_visible | 20 | -11.8 pp [-18.2, -5.8] | 24.1% [22.9, 25.2] | 23.1% [20.9, 25.3] | -12.4 pp [-20.0, -4.6] |
| bayesian | 0.0 | 15.0 | 0.15 | outcome_only | 20 | -2.0 pp [-9.0, 4.8] | 8.8% [8.3, 9.3] | 8.1% [6.2, 10.2] | -1.8 pp [-8.1, 5.8] |
| bayesian | 0.0 | 15.0 | 0.15 | reason_visible | 20 | -5.5 pp [-11.2, 0.5] | 9.2% [8.7, 9.7] | 8.2% [6.7, 9.7] | -5.2 pp [-10.5, 0.3] |
| bayesian | 0.0 | 15.0 | 0.35 | outcome_only | 20 | -14.5 pp [-21.5, -7.0] | 23.0% [20.9, 24.7] | 21.9% [19.4, 24.4] | -11.0 pp [-17.5, -4.1] |
| bayesian | 0.0 | 15.0 | 0.35 | reason_visible | 20 | -11.8 pp [-17.2, -5.5] | 24.1% [22.8, 25.3] | 23.1% [20.8, 25.5] | -12.4 pp [-19.6, -4.6] |
| bayesian | 0.25 | 5.0 | 0.15 | outcome_only | 20 | -2.0 pp [-9.5, 4.8] | 8.9% [8.3, 9.5] | 8.0% [6.3, 9.7] | -6.1 pp [-14.4, 2.8] |
| bayesian | 0.25 | 5.0 | 0.15 | reason_visible | 20 | -5.0 pp [-12.5, 2.2] | 9.3% [8.9, 9.7] | 8.4% [6.7, 10.4] | -6.3 pp [-12.9, -0.4] |
| bayesian | 0.25 | 5.0 | 0.35 | outcome_only | 20 | -12.0 pp [-17.5, -6.0] | 24.0% [22.7, 25.3] | 23.2% [20.6, 25.9] | -12.9 pp [-19.9, -4.7] |
| bayesian | 0.25 | 5.0 | 0.35 | reason_visible | 20 | -16.0 pp [-22.0, -8.8] | 23.5% [22.3, 24.7] | 23.2% [20.8, 25.7] | -13.8 pp [-19.3, -7.3] |
| bayesian | 0.25 | 15.0 | 0.15 | outcome_only | 20 | -2.0 pp [-9.5, 4.8] | 8.9% [8.3, 9.5] | 8.0% [6.4, 9.6] | -6.1 pp [-14.3, 1.9] |
| bayesian | 0.25 | 15.0 | 0.15 | reason_visible | 20 | -5.0 pp [-12.8, 3.0] | 9.3% [8.9, 9.7] | 8.4% [6.7, 10.2] | -6.3 pp [-12.9, -0.3] |
| bayesian | 0.25 | 15.0 | 0.35 | outcome_only | 20 | -12.0 pp [-17.8, -6.0] | 24.0% [22.7, 25.3] | 23.2% [20.4, 25.8] | -12.9 pp [-20.5, -3.6] |
| bayesian | 0.25 | 15.0 | 0.35 | reason_visible | 20 | -16.0 pp [-21.8, -9.3] | 23.5% [22.2, 24.7] | 23.2% [20.8, 25.7] | -13.8 pp [-19.2, -6.5] |
| bayesian | 0.5 | 5.0 | 0.15 | outcome_only | 20 | 13.8 pp [5.5, 23.2] | 6.1% [5.5, 6.7] | 5.1% [3.9, 6.3] | -1.0 pp [-9.8, 7.8] |
| bayesian | 0.5 | 5.0 | 0.15 | reason_visible | 20 | 25.2 pp [17.2, 32.5] | 5.6% [5.0, 6.1] | 4.5% [3.2, 5.8] | 10.6 pp [2.9, 18.8] |
| bayesian | 0.5 | 5.0 | 0.35 | outcome_only | 20 | 21.8 pp [12.2, 31.5] | 11.1% [10.0, 12.1] | 10.1% [8.4, 11.9] | 2.4 pp [-2.5, 7.8] |
| bayesian | 0.5 | 5.0 | 0.35 | reason_visible | 20 | 33.0 pp [22.3, 43.2] | 10.2% [9.0, 11.4] | 10.0% [8.1, 11.8] | 7.1 pp [1.7, 12.1] |
| bayesian | 0.5 | 15.0 | 0.15 | outcome_only | 20 | -8.2 pp [-14.0, -3.0] | 9.2% [8.7, 9.7] | 8.3% [6.8, 10.2] | -15.9 pp [-22.8, -8.8] |
| bayesian | 0.5 | 15.0 | 0.15 | reason_visible | 20 | -7.0 pp [-13.8, -1.0] | 9.1% [8.5, 9.6] | 8.6% [7.1, 10.2] | -15.3 pp [-23.2, -7.7] |
| bayesian | 0.5 | 15.0 | 0.35 | outcome_only | 20 | -18.5 pp [-24.2, -12.5] | 24.9% [23.8, 26.0] | 24.0% [22.2, 25.8] | -5.9 pp [-13.8, 1.4] |
| bayesian | 0.5 | 15.0 | 0.35 | reason_visible | 20 | -16.0 pp [-22.2, -10.0] | 24.9% [23.7, 25.9] | 24.0% [21.8, 26.4] | -14.4 pp [-22.4, -5.6] |
| bayesian | 1.0 | 5.0 | 0.15 | outcome_only | 20 | 34.2 pp [25.0, 43.2] | 4.9% [4.4, 5.4] | 4.5% [3.7, 5.5] | 13.6 pp [6.7, 21.0] |
| bayesian | 1.0 | 5.0 | 0.15 | reason_visible | 20 | 34.2 pp [24.8, 43.2] | 4.9% [4.4, 5.4] | 4.5% [3.7, 5.4] | 13.6 pp [6.6, 21.4] |
| bayesian | 1.0 | 5.0 | 0.35 | outcome_only | 20 | 28.7 pp [17.2, 38.0] | 9.9% [8.9, 11.0] | 8.6% [7.0, 10.5] | 9.4 pp [4.1, 15.0] |
| bayesian | 1.0 | 5.0 | 0.35 | reason_visible | 20 | 28.7 pp [18.0, 38.5] | 9.9% [8.8, 10.9] | 8.6% [6.9, 10.2] | 9.4 pp [4.0, 15.3] |
| bayesian | 1.0 | 15.0 | 0.15 | outcome_only | 20 | 34.2 pp [24.3, 43.5] | 4.9% [4.4, 5.4] | 4.5% [3.7, 5.5] | 13.6 pp [6.3, 21.2] |
| bayesian | 1.0 | 15.0 | 0.15 | reason_visible | 20 | 34.2 pp [25.2, 43.2] | 4.9% [4.4, 5.4] | 4.5% [3.7, 5.4] | 13.6 pp [6.2, 21.7] |
| bayesian | 1.0 | 15.0 | 0.35 | outcome_only | 20 | 28.7 pp [18.0, 38.5] | 9.9% [8.8, 11.0] | 8.6% [7.0, 10.4] | 9.4 pp [3.4, 15.0] |
| bayesian | 1.0 | 15.0 | 0.35 | reason_visible | 20 | 28.7 pp [19.0, 38.5] | 9.9% [8.8, 10.9] | 8.6% [7.1, 10.5] | 9.4 pp [4.3, 15.2] |
| oracle | 0.0 | 5.0 | 0.15 | outcome_only | 20 | 0.0 pp [0.0, 0.0] | 1.5% [1.5, 1.5] | 1.3% [0.7, 2.0] | not estimable |
| oracle | 0.0 | 5.0 | 0.15 | reason_visible | 20 | 0.0 pp [0.0, 0.0] | 1.5% [1.5, 1.5] | 1.3% [0.7, 2.1] | not estimable |
| oracle | 0.0 | 5.0 | 0.35 | outcome_only | 20 | 0.0 pp [0.0, 0.0] | 3.5% [3.5, 3.5] | 3.0% [2.0, 4.1] | not estimable |
| oracle | 0.0 | 5.0 | 0.35 | reason_visible | 20 | 0.0 pp [0.0, 0.0] | 3.5% [3.5, 3.5] | 3.0% [2.0, 4.3] | not estimable |
| oracle | 0.0 | 15.0 | 0.15 | outcome_only | 20 | 0.0 pp [0.0, 0.0] | 1.5% [1.5, 1.5] | 1.3% [0.7, 2.0] | not estimable |
| oracle | 0.0 | 15.0 | 0.15 | reason_visible | 20 | 0.0 pp [0.0, 0.0] | 1.5% [1.5, 1.5] | 1.3% [0.7, 2.0] | not estimable |
| oracle | 0.0 | 15.0 | 0.35 | outcome_only | 20 | 0.0 pp [0.0, 0.0] | 3.5% [3.5, 3.5] | 3.0% [2.0, 4.2] | not estimable |
| oracle | 0.0 | 15.0 | 0.35 | reason_visible | 20 | 0.0 pp [0.0, 0.0] | 3.5% [3.5, 3.5] | 3.0% [1.9, 4.0] | not estimable |
| oracle | 0.25 | 5.0 | 0.15 | outcome_only | 20 | 0.0 pp [0.0, 0.0] | 1.5% [1.5, 1.5] | 1.3% [0.7, 2.0] | not estimable |
| oracle | 0.25 | 5.0 | 0.15 | reason_visible | 20 | 0.0 pp [0.0, 0.0] | 1.5% [1.5, 1.5] | 1.3% [0.7, 2.0] | not estimable |
| oracle | 0.25 | 5.0 | 0.35 | outcome_only | 20 | 0.0 pp [0.0, 0.0] | 3.5% [3.5, 3.5] | 3.0% [2.0, 4.1] | not estimable |
| oracle | 0.25 | 5.0 | 0.35 | reason_visible | 20 | 0.0 pp [0.0, 0.0] | 3.5% [3.5, 3.5] | 3.0% [2.0, 4.1] | not estimable |
| oracle | 0.25 | 15.0 | 0.15 | outcome_only | 20 | 0.0 pp [0.0, 0.0] | 1.5% [1.5, 1.5] | 1.3% [0.8, 2.1] | not estimable |
| oracle | 0.25 | 15.0 | 0.15 | reason_visible | 20 | 0.0 pp [0.0, 0.0] | 1.5% [1.5, 1.5] | 1.3% [0.7, 2.0] | not estimable |
| oracle | 0.25 | 15.0 | 0.35 | outcome_only | 20 | 0.0 pp [0.0, 0.0] | 3.5% [3.5, 3.5] | 3.0% [2.0, 4.1] | not estimable |
| oracle | 0.25 | 15.0 | 0.35 | reason_visible | 20 | 0.0 pp [0.0, 0.0] | 3.5% [3.5, 3.5] | 3.0% [2.0, 4.1] | not estimable |
| oracle | 0.5 | 5.0 | 0.15 | outcome_only | 20 | 0.0 pp [0.0, 0.0] | 1.5% [1.5, 1.5] | 1.3% [0.8, 2.0] | not estimable |
| oracle | 0.5 | 5.0 | 0.15 | reason_visible | 20 | 0.0 pp [0.0, 0.0] | 1.5% [1.5, 1.5] | 1.3% [0.7, 2.1] | not estimable |
| oracle | 0.5 | 5.0 | 0.35 | outcome_only | 20 | 0.0 pp [0.0, 0.0] | 3.5% [3.5, 3.5] | 3.0% [1.9, 4.1] | not estimable |
| oracle | 0.5 | 5.0 | 0.35 | reason_visible | 20 | 0.0 pp [0.0, 0.0] | 3.5% [3.5, 3.5] | 3.0% [2.0, 4.1] | not estimable |
| oracle | 0.5 | 15.0 | 0.15 | outcome_only | 20 | 0.0 pp [0.0, 0.0] | 1.5% [1.5, 1.5] | 1.3% [0.7, 2.1] | not estimable |
| oracle | 0.5 | 15.0 | 0.15 | reason_visible | 20 | 0.0 pp [0.0, 0.0] | 1.5% [1.5, 1.5] | 1.3% [0.7, 1.9] | not estimable |
| oracle | 0.5 | 15.0 | 0.35 | outcome_only | 20 | 0.0 pp [0.0, 0.0] | 3.5% [3.5, 3.5] | 3.0% [2.0, 4.2] | not estimable |
| oracle | 0.5 | 15.0 | 0.35 | reason_visible | 20 | 0.0 pp [0.0, 0.0] | 3.5% [3.5, 3.5] | 3.0% [2.1, 4.1] | not estimable |
| oracle | 1.0 | 5.0 | 0.15 | outcome_only | 20 | 0.0 pp [0.0, 0.0] | 1.5% [1.5, 1.5] | 1.3% [0.7, 2.1] | not estimable |
| oracle | 1.0 | 5.0 | 0.15 | reason_visible | 20 | 0.0 pp [0.0, 0.0] | 1.5% [1.5, 1.5] | 1.3% [0.7, 2.0] | not estimable |
| oracle | 1.0 | 5.0 | 0.35 | outcome_only | 20 | 0.0 pp [0.0, 0.0] | 3.5% [3.5, 3.5] | 3.0% [2.0, 4.1] | not estimable |
| oracle | 1.0 | 5.0 | 0.35 | reason_visible | 20 | 0.0 pp [0.0, 0.0] | 3.5% [3.5, 3.5] | 3.0% [2.0, 4.1] | not estimable |
| oracle | 1.0 | 15.0 | 0.15 | outcome_only | 20 | 0.0 pp [0.0, 0.0] | 1.5% [1.5, 1.5] | 1.3% [0.7, 2.1] | not estimable |
| oracle | 1.0 | 15.0 | 0.15 | reason_visible | 20 | 0.0 pp [0.0, 0.0] | 1.5% [1.5, 1.5] | 1.3% [0.8, 2.1] | not estimable |
| oracle | 1.0 | 15.0 | 0.35 | outcome_only | 20 | 0.0 pp [0.0, 0.0] | 3.5% [3.5, 3.5] | 3.0% [2.0, 4.1] | not estimable |
| oracle | 1.0 | 15.0 | 0.35 | reason_visible | 20 | 0.0 pp [0.0, 0.0] | 3.5% [3.5, 3.5] | 3.0% [2.0, 4.1] | not estimable |
| uniform | 0.0 | 5.0 | 0.15 | outcome_only | 20 | 0.7 pp [-5.5, 6.7] | 7.4% [7.2, 7.7] | 6.1% [4.8, 7.3] | 2.0 pp [-5.4, 9.0] |
| uniform | 0.0 | 5.0 | 0.15 | reason_visible | 20 | 0.7 pp [-5.5, 6.8] | 7.4% [7.2, 7.7] | 6.1% [4.7, 7.3] | 2.0 pp [-5.4, 9.5] |
| uniform | 0.0 | 5.0 | 0.35 | outcome_only | 20 | 0.7 pp [-5.5, 6.5] | 15.8% [15.1, 16.4] | 14.5% [12.7, 16.2] | 0.8 pp [-3.6, 5.0] |
| uniform | 0.0 | 5.0 | 0.35 | reason_visible | 20 | 0.7 pp [-5.3, 7.0] | 15.8% [15.2, 16.5] | 14.5% [12.6, 16.3] | 0.8 pp [-3.5, 5.2] |
| uniform | 0.0 | 15.0 | 0.15 | outcome_only | 20 | 0.7 pp [-5.8, 7.2] | 7.4% [7.2, 7.7] | 6.1% [4.8, 7.3] | 2.0 pp [-5.1, 9.0] |
| uniform | 0.0 | 15.0 | 0.15 | reason_visible | 20 | 0.7 pp [-6.0, 7.0] | 7.4% [7.2, 7.7] | 6.1% [4.8, 7.3] | 2.0 pp [-5.6, 8.8] |
| uniform | 0.0 | 15.0 | 0.35 | outcome_only | 20 | 0.7 pp [-5.3, 6.8] | 15.8% [15.2, 16.4] | 14.5% [12.6, 16.3] | 0.8 pp [-3.2, 5.1] |
| uniform | 0.0 | 15.0 | 0.35 | reason_visible | 20 | 0.7 pp [-5.5, 7.0] | 15.8% [15.2, 16.4] | 14.5% [12.7, 16.2] | 0.8 pp [-3.5, 5.0] |
| uniform | 0.25 | 5.0 | 0.15 | outcome_only | 20 | 0.7 pp [-5.8, 6.5] | 7.4% [7.2, 7.7] | 6.1% [4.8, 7.3] | 2.0 pp [-5.1, 9.4] |
| uniform | 0.25 | 5.0 | 0.15 | reason_visible | 20 | 0.7 pp [-6.0, 6.8] | 7.4% [7.2, 7.7] | 6.1% [4.8, 7.2] | 2.0 pp [-4.5, 9.2] |
| uniform | 0.25 | 5.0 | 0.35 | outcome_only | 20 | 0.7 pp [-5.0, 6.8] | 15.8% [15.2, 16.4] | 14.5% [12.7, 16.2] | 0.8 pp [-3.4, 4.9] |
| uniform | 0.25 | 5.0 | 0.35 | reason_visible | 20 | 0.7 pp [-5.3, 6.8] | 15.8% [15.1, 16.4] | 14.5% [12.7, 16.3] | 0.8 pp [-3.3, 4.9] |
| uniform | 0.25 | 15.0 | 0.15 | outcome_only | 20 | 0.7 pp [-6.0, 7.2] | 7.4% [7.2, 7.7] | 6.1% [4.7, 7.3] | 2.0 pp [-5.1, 8.5] |
| uniform | 0.25 | 15.0 | 0.15 | reason_visible | 20 | 0.7 pp [-5.5, 6.0] | 7.4% [7.1, 7.7] | 6.1% [4.8, 7.2] | 2.0 pp [-5.4, 9.0] |
| uniform | 0.25 | 15.0 | 0.35 | outcome_only | 20 | 0.7 pp [-5.5, 6.8] | 15.8% [15.2, 16.4] | 14.5% [12.5, 16.3] | 0.8 pp [-3.6, 5.2] |
| uniform | 0.25 | 15.0 | 0.35 | reason_visible | 20 | 0.7 pp [-5.5, 7.0] | 15.8% [15.2, 16.4] | 14.5% [12.7, 16.2] | 0.8 pp [-3.3, 4.9] |
| uniform | 0.5 | 5.0 | 0.15 | outcome_only | 20 | 0.7 pp [-5.5, 7.2] | 7.4% [7.2, 7.7] | 6.1% [4.8, 7.2] | 2.0 pp [-4.6, 9.0] |
| uniform | 0.5 | 5.0 | 0.15 | reason_visible | 20 | 0.7 pp [-6.0, 6.8] | 7.4% [7.2, 7.7] | 6.1% [4.8, 7.3] | 2.0 pp [-5.0, 9.4] |
| uniform | 0.5 | 5.0 | 0.35 | outcome_only | 20 | 0.7 pp [-5.8, 7.0] | 15.8% [15.2, 16.5] | 14.5% [12.8, 16.3] | 0.8 pp [-3.5, 4.8] |
| uniform | 0.5 | 5.0 | 0.35 | reason_visible | 20 | 0.7 pp [-5.8, 6.7] | 15.8% [15.2, 16.4] | 14.5% [12.5, 16.3] | 0.8 pp [-3.4, 5.0] |
| uniform | 0.5 | 15.0 | 0.15 | outcome_only | 20 | 0.7 pp [-5.8, 6.5] | 7.4% [7.2, 7.7] | 6.1% [4.8, 7.3] | 2.0 pp [-5.0, 9.1] |
| uniform | 0.5 | 15.0 | 0.15 | reason_visible | 20 | 0.7 pp [-5.8, 6.5] | 7.4% [7.2, 7.7] | 6.1% [4.8, 7.2] | 2.0 pp [-5.4, 9.7] |
| uniform | 0.5 | 15.0 | 0.35 | outcome_only | 20 | 0.7 pp [-5.8, 6.7] | 15.8% [15.2, 16.4] | 14.5% [12.6, 16.2] | 0.8 pp [-3.4, 5.2] |
| uniform | 0.5 | 15.0 | 0.35 | reason_visible | 20 | 0.7 pp [-5.0, 7.0] | 15.8% [15.2, 16.5] | 14.5% [12.6, 16.3] | 0.8 pp [-3.4, 5.1] |
| uniform | 1.0 | 5.0 | 0.15 | outcome_only | 20 | 0.7 pp [-5.3, 6.5] | 7.4% [7.2, 7.7] | 6.1% [4.9, 7.4] | 2.0 pp [-5.4, 9.8] |
| uniform | 1.0 | 5.0 | 0.15 | reason_visible | 20 | 0.7 pp [-5.8, 6.8] | 7.4% [7.1, 7.7] | 6.1% [4.8, 7.3] | 2.0 pp [-5.0, 9.1] |
| uniform | 1.0 | 5.0 | 0.35 | outcome_only | 20 | 0.7 pp [-5.8, 6.5] | 15.8% [15.2, 16.4] | 14.5% [12.7, 16.3] | 0.8 pp [-3.3, 4.9] |
| uniform | 1.0 | 5.0 | 0.35 | reason_visible | 20 | 0.7 pp [-5.5, 6.2] | 15.8% [15.2, 16.4] | 14.5% [12.6, 16.2] | 0.8 pp [-3.4, 5.3] |
| uniform | 1.0 | 15.0 | 0.15 | outcome_only | 20 | 0.7 pp [-5.8, 7.0] | 7.4% [7.2, 7.7] | 6.1% [4.8, 7.3] | 2.0 pp [-5.4, 9.2] |
| uniform | 1.0 | 15.0 | 0.15 | reason_visible | 20 | 0.7 pp [-5.3, 6.8] | 7.4% [7.2, 7.7] | 6.1% [4.8, 7.2] | 2.0 pp [-5.6, 9.1] |
| uniform | 1.0 | 15.0 | 0.35 | outcome_only | 20 | 0.7 pp [-5.5, 6.8] | 15.8% [15.2, 16.4] | 14.5% [12.7, 16.3] | 0.8 pp [-3.5, 5.1] |
| uniform | 1.0 | 15.0 | 0.35 | reason_visible | 20 | 0.7 pp [-5.8, 7.0] | 15.8% [15.2, 16.4] | 14.5% [12.7, 16.2] | 0.8 pp [-3.7, 4.9] |

The task-type interaction is (future share after O − future share after P) for careful workers, minus the same contrast for compliers. It uses pooled events and resamples whole runs. It is not a pure causal effect of objection: task type also changes completion, audits, scores, and reasons. Differences and intervals in the two share-change columns are percentage points; risk columns are percentages.

The CSV and JSON outputs include all event-cell counts, sparse-bootstrap warnings, per-run contrasts, and paired baseline comparisons. Missing cells remain null. Per-run complete-case contrasts use a selected subset and are diagnostic only.

Expected violation risk equals π times the assignment-weighted probability of proceeding on an objection-required task. Realized violations fluctuate around that expectation; an exact equality in finite samples is not required.

See METHODS.md for the observation model, estimands, and interpretation limits. No null result here establishes equivalence or absence of a meaningful effect.
