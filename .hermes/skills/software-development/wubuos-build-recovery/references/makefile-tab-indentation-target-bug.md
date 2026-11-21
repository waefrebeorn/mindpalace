# Makefile target accidentally tab-indented into previous recipe (session fix)

## Symptom
A Makefile target like `test_kvfs:` that begins with a **tab** character is
parsed by GNU Make as a **recipe command** of the preceding rule, not as a
new target rule. This causes:

```
make: test_kvfs:: No such file or directory
make: *** [mk/tests.mk:931: test_hw_gpu] Error 127
```

The `::` double-colon and "No such file or directory" error are the
giveaway: Make is trying to *execute* `test_kvfs:` as a shell command.

## Root Cause
In `mk/tests.mk`, the `test_kvfs:` line was indented with a TAB:

```make
test_hw_gpu: ...deps...
	$(CC) ... -o $(KERNEL)/test_hw_gpu
	$(KERNEL)/test_hw_gpu

	test_kvfs:          # ← TAB here! Make treats this as a recipe command
	$(CC) ... -o $(KERNEL)/wubu_kvfs_selftest
	$(KERNEL)/wubu_kvfs_selftest
```

The blank line between `$(KERNEL)/test_hw_gpu` and `\ttest_kvfs:` doesn't
help — Make continues the recipe. The `\ttest_kvfs:` becomes part of
`test_hw_gpu`'s recipe, and Make tries to run `test_kvfs:` as a shell command.

## The Fix
Remove the leading TAB so `test_kvfs:` starts at column 0 (a target rule):

```make
	$(KERNEL)/test_hw_gpu

test_kvfs:                    # ← no tab, starts at column 0
	$(CC) ... -o $(KERNEL)/wubu_kvfs_selftest
	$(KERNEL)/wubu_kvfs_selftest
```

## Detection
When a make error says `No such file or directory` or `Error 127` for what
looks like a valid target name (with `::`), check that the target line
starts at column 0 — NOT indented with a tab.

## Verification
Run `make <target>` and confirm the previously-failing target now appears as
a proper Make target (not a shell command).