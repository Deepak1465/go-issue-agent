# Pull Request Summary

## Title
fix: reject hostname_rfc1123 values with out-of-range IPv4 octets

## Issue
https://github.com/go-playground/validator/issues/1561

## Branch
`agent/fix-issue-1561`

## Description
## Problem

The `hostname_rfc1123` validator accepts strings like `277.168.0.1` that look like IPv4 addresses but contain octets outside 0–255. Per RFC 1123, such dotted-decimal forms should not be valid hostnames.

## Root cause

`isHostnameRFC1123` only checked the RFC 1123 hostname regex, which allows digit-only labels and therefore accepts invalid dotted-quad strings.

## Fix

- Add `hasOutOfRangeIPv4Octets` helper in `baked_in.go`
- Reject hostname candidates with any octet > 255 before regex matching
- Add regression tests in `TestHostnameRFC1123Validation`

## Validation

```
go test -run TestHostnameRFC1123 ./...
```

Resolves #1561.

## Diff
```diff
diff --git a/baked_in.go b/baked_in.go
--- a/baked_in.go
+++ b/baked_in.go
@@ -2890,7 +2890,34 @@ func isHostnameRFC952(fl FieldLevel) bool {
 }
 
 func isHostnameRFC1123(fl FieldLevel) bool {
-	return hostnameRegexRFC1123().MatchString(fl.Field().String())
+	val := fl.Field().String()
+	if hasOutOfRangeIPv4Octets(val) {
+		return false
+	}
+	return hostnameRegexRFC1123().MatchString(val)
+}
+
+// hasOutOfRangeIPv4Octets reports dotted-decimal strings with an octet outside 0-255.
+func hasOutOfRangeIPv4Octets(s string) bool { ... }
```

## Agent Actions
- **list_files** `{"path": "."}`
- **search_code** `{"query": "hostname_rfc1123"}`
- **search_code** `{"query": "isHostnameRFC1123"}`
- **read_file** `{"path": "baked_in.go"}`
- **read_file** `{"path": "regexes.go"}`
- **read_file** `{"path": "validator_test.go"}`
- **edit_file** `{"path": "baked_in.go", "old_str_chars": 89, "new_str_chars": 612}`
- **edit_file** `{"path": "validator_test.go", "old_str_chars": 28, "new_str_chars": 98}`
- **run_go** `{"args": "test -run TestHostnameRFC1123 ./..."}`
- **run_go** `{"args": "vet ./..."}`
- **submit_pr** `{"title": "fix: reject hostname_rfc1123 values with out-of-range IPv4 octets"}`
