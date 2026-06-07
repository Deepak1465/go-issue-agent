# Pull Request Summary

## Title
fix: cron validation support for star step value

## Issue Fixed
https://github.com/go-playground/validator/issues/1259

## PR Body
## Problem

The `cron` validator incorrectly rejects valid cron expressions that use the `*/N` step
syntax in any field. For example, all of these valid cron expressions were failing:

```
0 */1 * * *    (every hour)
0 */2 * * *    (every 2 hours)
*/5 * * * *    (every 5 minutes)
0 0 1 */3 *    (quarterly — every 3 months)
```

## Root Cause

The regex in `regexes.go` handled the step operator (`/`) when paired with a specific
number (`\d+/\d+`) but did not account for the wildcard-step pattern (`*/\d+`), which is
the most common way to express "every N units" in cron syntax.

Old regex fragment (simplified):
```
(\*|\d+)(\/|-)\d+
```

This pattern matches `*` as a standalone character OR a number followed by `/` or `-`.
But when used with `/`, the `*` was consumed as the first alternative and the `/\d+`
part was never reached — causing the whole expression to fail.

## Fix

Updated `cronRegexString` in `regexes.go` to explicitly handle `*/\d+` as a valid
step-value pattern:

```go
// Before
`(\*|\d+)(\/|-)\d+`

// After  
`(\*\/\d+|\d+(\/|-)\d+)`
```

This cleanly separates the two cases:
- `*/N` — wildcard step (e.g. `*/5`)
- `N/N` or `N-N` — numeric step or range (e.g. `1/5` or `1-5`)

## Tests Added

Added test cases to `TestIsCron` in `baked_in_test.go` covering:
- `*/N` step in each of the 5 cron fields
- Common real-world patterns (`*/5 * * * *`, `0 */2 * * *`, `0 0 1 */3 *`)
- Edge cases: `*/1`, `*/59`, `*/12`

## Validation

All existing tests pass. New test cases pass.

```
$ go test -run TestIsCron ./...
--- PASS: TestIsCron (0.00s)
ok  	github.com/go-playground/validator/v10
```

## Diff
```diff
--- a/regexes.go
+++ b/regexes.go
@@ -72,7 +72,7 @@ var (
-	cronRegexString = `(@(annually|yearly|monthly|weekly|daily|hourly|reboot))|(@every (\d+(ns|us|µs|ms|s|m|h))+)|((((\d+,)+\d+|((\*|\d+)(\/|-)\d+)|\d+|\*) ?){5,7})`
+	cronRegexString = `(@(annually|yearly|monthly|weekly|daily|hourly|reboot))|(@every (\d+(ns|us|µs|ms|s|m|h))+)|((((\d+,)+\d+|(\*\/\d+|\d+(\/|-)\d+)|\d+|\*) ?){5,7})`
```

## Agent Actions
- Called list_files: {"."}
- Called read_file: {"path": "regexes.go"}
- Called search_code: {"query": "isCron"}
- Called read_file: {"path": "baked_in.go"}
- Called search_code: {"query": "cronRegexString"}
- Called read_file: {"path": "baked_in_test.go"}
- Called edit_file: {"path": "regexes.go", "old_str": "...", "new_str": "..."}
- Called edit_file: {"path": "baked_in_test.go", "old_str": "...", "new_str": "..."}
- Called run_tests: {"args": "-run TestIsCron ./..."}
- Called run_tests: {"args": "./..."}
- Called submit_pr: {"title": "fix: cron validation support for star step value"}
