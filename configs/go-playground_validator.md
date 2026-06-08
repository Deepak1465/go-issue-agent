# Project rules: go-playground/validator

## Repository layout
| Path | Purpose |
|------|---------|
| `baked_in.go` | Built-in validator functions (`isCron`, `isHostnameRFC1123`, etc.) |
| `regexes.go` | Compiled regex patterns (`cronRegexString`, `hostnameRegexRFC1123`, …) |
| `baked_in_test.go` | Table-driven tests for built-in validators |
| `validator_test.go` | Integration-style validator tests |
| `validator.go` | Core `Validate` struct and registration |

## Conventions
- Validators are functions with signature `func(FieldLevel) bool`
- Register new validators in the `builtInValidators` map in `baked_in.go`
- Regexes use `lazyRegexCompile()` — define the string var, then compile in `regexes.go`
- Follow existing table-driven test style: `tests := []struct { param string; expected bool }{...}`
- Keep fixes minimal — one bug, one root cause, targeted tests

## Validation commands
```bash
go test -run TestIsCron ./...          # cron validator
go test -run TestHostnameRFC1123 ./... # hostname validator
go vet ./...
go test ./...                          # full suite (slower)
```

## Issue selection tips
Good candidates: regex bugs, missing edge cases, incorrect validator logic.
Avoid: large refactors, new validator families, translation/i18n changes, dependency bumps.
