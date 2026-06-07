# Pull Request Summary

## Title
Fix: Cron validator not correct for step values (Issue #1259)

## Issue
https://github.com/go-playground/validator/issues/1259

## Diff
```diff
diff --git a/regexes.go b/regexes.go
index 20c03b8..7f2db37 100644
--- a/regexes.go
+++ b/regexes.go
@@ -77,7 +77,7 @@ const (
 	cveRegexString                   = `^CVE-(1999|2\d{3})-(0[^0]\d{2}|0\d[^0]\d{1}|0\d{2}[^0]|[1-9]{1}\d{3,})$` // CVE Format Id https://cve.mitre.org/cve/identifiers/syntaxchange.html
 	mongodbIdRegexString             = "^[a-f\\d]{24}$"
 	mongodbConnStringRegexString     = "^mongodb(\\+srv)?:\\/\\/(([a-zA-Z\\d]+):([a-zA-Z\\d$:\\/?#\\[\\]@]+)@)?(([a-z\\d.-]+)(:[\\d]+)?)((,(([a-z\\d.-]+)(:(\\d+))?))*)?(\\/[a-zA-Z-_]{1,64})?(\\?(([a-zA-Z]+)=([a-zA-Z\\d]+))(&(([a-zA-Z\\d]+)=([a-zA-Z\\d]+))?)*)?$"
-	cronRegexString                  = `^((@(annually|yearly|monthly|weekly|daily|hourly|reboot))|(@every (\d+(ns|us|µs|ms|s|m|h))+)|(([A-Za-z0-9*?][A-Za-z0-9*?/,#L-]+|[*?0-9])( +([A-Za-z0-9*?][A-Za-z0-9*?/,#L-]+|[*?0-9])){4,6}))$`
+	cronRegexString                  = `^((@(annually|yearly|monthly|weekly|daily|hourly|reboot))|(@every (\d+(ns|us|µs|ms|s|m|h))+)|(([A-Za-z0-9*?][A-Za-z0-9*?,#L-]*(\/\d+)?|[*?0-9])( +([A-Za-z0-9*?][A-Za-z0-9*?,#L-]*(\/\d+)?|[*?0-9])){4,6}))$`
 	spicedbIDRegexString             = `^(([a-zA-Z0-9/_|\-=+]{1,})|\*)$`
 	spicedbPermissionRegexString     = "^([a-z][a-z0-9_]{1,62}[a-z0-9])?$"
 	spicedbTypeRegexString           = "^([a-z][a-z0-9_]{1,61}[a-z0-9]/)?[a-z][a-z0-9_]{1,62}[a-z0-9]$"

```
