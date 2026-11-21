# Measured Assertions Pattern

**Definition:** A test assertion that verifies a specific numerical value, invariant, or statistical property - not just a boolean pass/fail. Examples: dup rate = 0.294, lineage survival = 0.94, quality score > 0.6, bucket index = K-1.

## Why Measured Assertions?

When completing feature goals with a criterion like "forward verified" or "with measured assertions", the test must assert concrete, measurable values. This distinguishes:
- **Basic regression**: "does not crash", "returns non-NULL"
- **Measured verification**: exact rates, bounds, counts, invariant checks

## Pattern Structure

```c
/* Measured assertion on <property>
 * Value: <measured_value> -- assert <expected_behavior>
 */
T(measured_property == expected, "description");
```

## Where to Place Measured Assertions

1. **Near the end** of the test function, after structural checks
2. **In a dedicated section** labeled "Measured values" or "<feature> metrics"
3. **Each assertion should comment the expected value** for future audit

## Examples from Recent Sessions

### Quality Filter (BRAIN #245)
```c
double sp = wubu_quality_score(prose);
T(sp > 0.6, "real prose scores high (> 0.6)");
T(ss < sp, "numeric spam scores below prose");
```

### Length Bucket (BRAIN #246)
```c
T(wubu_length_bucket(64, bounds, k) == 1, "L==64 -> bucket 1");
T(wubu_length_bucket_pad(5000, bounds, k) == 1024, "overflow pad == last bound");
```

### Rollback (AGENT #312)
```c
T(wubu_rollback_step(&rb, 0) == WUBU_ROLLBACK_RESTORE, "K-th divergence: RESTORE fired");
T(wubu_rollback_fires(&rb) == 1, "restore count == 1");
```

### Lineage (AGENT #313)
```
winning lineage 1: 8 gens, best 3.00, survival 0.94
extinction pass: 1 soft-extinct (winner alive=1)
```

## Checklist for New Measured Assertions

- [ ] Value is numerically verifiable (not a range check unless intentional)
- [ ] Expected value is documented in comments
- [ ] Assertion tests both happy path AND boundary conditions
- [ ] Test name describes what is being measured (e.g., "dup rate 0.294")
- [ ] For statistical assertions: sample size is large enough (>= 1000 events typical)

## Common Measured Assertion Types

| Type | Pattern | Example |
|------|---------|---------|
| Score/Value | `score > threshold` | `sp > 0.6` |
| Exact Count | `count == N` | `wins == 10` |
| Index Mapping | `func(X) == Y` | `bucket(L) == idx` |
| Statistical Rate | `rate = count/total` | `0.294` |
| Boundary Condition | `L <= bound ? A : B` | `pad(L) >= L` |
| Invariant | `property never exceeds max` | `streak <= K` |