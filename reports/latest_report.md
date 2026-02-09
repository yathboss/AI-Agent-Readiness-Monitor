# Agentic Web Observability — Phase 2 Report
Generated: `2026-02-06T19:01:49Z`

## Filters
```txt
site:   http://localhost:3000
domain: (any)
task:   all
since:  (any)
until:  (any)
```
## Task success rate
| task | total_runs | success_runs | success_rate_pct |
| --- | --- | --- | --- |
| pricing | 6 | 5 | 83.33 |
| refund | 4 | 3 | 75.00 |
| contact | 4 | 3 | 75.00 |

## Failure reason distribution
| final_fail_reason | failures |
| --- | --- |
| unknown | 3 |

## Top failing URLs
| final_url | failures | unique_runs |
| --- | --- | --- |
| http://localhost:3000 | 3 | 3 |

## Example failure traces
Hotspot URL: `http://localhost:3000`\n\n### Run `287487be5c-contact` — task `contact` — reason `unknown`
Sequence:\n```txt
http://localhost:3000
```
Steps (first 25):\n| step_num | url | status | fail_reason | latency_ms |
| --- | --- | --- | --- | --- |
| 1 | http://localhost:3000 | fail | unknown | 3013 |
\n### Run `836bf0b5b4-refund` — task `refund` — reason `unknown`
Sequence:\n```txt
http://localhost:3000
```
Steps (first 25):\n| step_num | url | status | fail_reason | latency_ms |
| --- | --- | --- | --- | --- |
| 1 | http://localhost:3000 | fail | unknown | 2993 |
\n### Run `931b8e778a-pricing` — task `pricing` — reason `unknown`
Sequence:\n```txt
http://localhost:3000
```
Steps (first 25):\n| step_num | url | status | fail_reason | latency_ms |
| --- | --- | --- | --- | --- |
| 1 | http://localhost:3000 | fail | unknown | 4129 |
\n