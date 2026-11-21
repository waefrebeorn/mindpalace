---
name: wubu-ecosystem-of-spheres
category: mlops
description: "Ecosystem AGI: many hyperbolic spheres, physics router (potential wells), fractal stacking on sphere surfaces, small active params."
---

# Ecosystem of Spheres — the WuBu colony doctrine

## Trigger
Use when designing WuBu's sparse architecture: MoE routing, hyperbolic
experts, nesting, active-parameter efficiency, fractal packing, or the
amoeba's growth/specialization. THEORY/10 is the full doc; this is the
operating skill.

## The thesis (user's directives, verbatim)
- "the secret to getting effective usage is the smallest active parameter
  but an effective large system"
- "our amoeba structure needs to have ecosystem... a full ecosystem AGI of
  our spheres, and we just need to have a bunch of spheres and use physics"
- "as much data as possible in a small space while effectively having our
  AGI function"
- "fractal stacking on the surface of the sphere on top of the hyperbolic
  embedding we can really cram a lot into the empty space"

## Design rules
1. **Small active / huge total**: active/total is the design lever.
   DeepSeek V3: 671B/37B (5.5%), 8 of 256 experts. WuBu target ~12%.
2. **Physics IS the router**: no learned routing weights. Each ball k has
   potential φ_k(x) = gyro-distance² from center, weighted by curvature.
   Input is attracted by F_k = -∇φ_k; top-K deepest wells fire. Möbius
   add the outputs: y = y ⊕_c (w_k · exp_0^{c_k}(proj_k(x))).
3. **Three layers of density**:
   - hyperbolic interior: exponential volume growth (Sarkar: trees embed
     in Poincaré ball with arbitrarily low distortion in 2D)
   - sphere-surface fractal stacking: space-filling curves on the ideal
     boundary (sphere at infinity) = infinite addressable shelf
   - nesting: ball-in-ball, surface of A = interior of A+1
4. **The hive IS the ecosystem**: GROW (mitosis, curvature inherited,
   gate-zeroed daughter), SHRINK (dead ball → freelist), SPECIATE (balls
   drift in curvature space → ecological niches).
5. **Cold-start guard**: 1-2 always-on "heart" balls (core trunk) so the
   colony never misroutes everything.

## Existing pieces (already built, Lean-verified)
| Module | Role |
|--------|------|
| `src/wubu_hyper.c` | mobius_add, exp_0, log_0, gyration |
| `src/wubu_nested_ssm.c` | K Poincaré balls, K curvatures |
| `src/wubu_moe_hyperbolic.c` | hyperbolic expert cores |
| `src/wubu_poincare_gqa.c` | gyro-rotated attention within ball |
| `src/wubu_moe.c` | 256-expert candidate pool |
| `src/wubu_hive.c` | grow/shrink/specialize lifecycle |

## New pieces to build
- **physics router**: potential-well top-K (closed-form, no learned weights)
- **surface fractal index**: space-filling curve addressing on the ball
  boundary (≥2^20 sites in <1MB, collision-free, round-trip exact)

## Gates
- `test_ecosystem`: 64-ball colony, synthetic clusters → top-k purity >90%,
  active params <12% of total, grow/shrink stable (no thrash)
- `test_fractal_index`: ≥2^20 addresses, 0 collisions, exact round-trip

## Pitfalls
- **Ball collapse**: all curvatures → 0 turns the colony into a dense
  model — curvature floor + diversity regularizer required
- **Cold-start misroute**: without heart balls, early inputs can miss all
  experts — always-on core trunk mandatory
- MoE load balancing still applies: potential wells can skew; renormalize
  well depth by ball utilization (the hive's immune signals)
