# Travel optimization continuation

Adapted from upstream OrcaSlicer #16492, commit
69193d5681fddf8ed3d63bf510bb307c21f5a0d1. This patch is based on development
commit 1677c4bec9bd4c2e86bacf8ac071de4be0097c3a.

## Behavior

- Exact shortest path chains for small sets; larger chains use bounded local
  refinement and a nearest-next candidate, preserving allowed path directions.
- Exact object/island tours for up to ten points; larger tours add local run
  relocation to existing 2-opt/crossing removal.
- Nearby sparse-infill line ends join into fewer extrusion paths without closing
  new loops, crossing existing lines, or reversing direction-locked paths.
  Unlike pure travel reordering, these joins add short extruded connectors and
  can change material use. Review the resulting toolpaths and estimated usage.

No profiles, defaults, network plugins, printer connection code, PA/nozzle
routing, or live services are changed. Existing no-sort flags still protect
monotonic/concentric/forced-order and flow-calibration collections. The algorithm
has no additional user setting, matching upstream.

## Adaptation to this fork

This fork retains hierarchical extrusion collections in G-code export. Refine
paths in each sortable collection through its existing cloned-path entry point;
do not import upstream's broader G-code flattening and const-pointer ownership
changes. This limits optimization to the existing collection boundaries.

Both chaining overloads retain the custom empty-support-path safeguards. The
existing narrow-solid concentric fallback and forced-order safeguards remain.
Upstream's relaxation of the multiline-lightning path-count test was not copied;
the fork's stricter check is included in the travel test selection.

## Automated validation for the owner

Build using the existing Linux updater, then run:

```bash
ctest --test-dir build -C Release --output-on-failure --no-tests=error -L '^TravelOptimization$'
```

The shared label covers 16 test cases: shortest-path comparisons, path identity
and direction, exact/large tours, line joins, collection cloning/order,
empty-support entries, nearest-start selection for zero to three points, and
the existing multiline-lightning check. The local
desktop updater runs this group after its existing five cloud/height cases and
before runtime replacement. The test fixtures do not contact printers.

The owner's 2026-10-25 updater run compiled the application but stopped during
test compilation: the collection-geometry fixture stored this fork's 3D path
coordinates in a 2D vector. That fixture now uses Points3. The updater did not
reach deployment, and the installed runtime metadata still identifies the
previous version. Rebuilding and all 16 travel cases remain pending; no tests or
builds were run by Codex. A green cloud/height group alone does not validate
travel optimization. Representative slicing/performance checks also remain
pending despite positive owner feedback on the installed application.

## Slicing review

Using copied profiles and no physical print, compare the same project and preset
on the previous runtime and the patched runtime:

1. Single- and dual-nozzle plates; multiple islands/objects under Default and
   Snake order. Default may change order; Snake should retain its strategy.
2. Sparse rectilinear, grid, gyroid and multiline infill; supports and ironing.
   Compare travel distances and inspect joins, holes, thin regions, anchors, and
   model boundaries. Check for lost/duplicated extrusion, unintended crossings,
   extrusions outside the model, or changed direction of oriented paths.
3. Monotonic and forced surface order, concentric fills, and the custom flow
   calibration. Their required internal ordering must remain intact.
4. Check slice time and memory on a plate with many paths. The algorithm trades
   additional planning time for shorter travel; no performance gain is promised
   until representative models have been measured.
5. Confirm custom nozzle assignments, PA, and shrinkage behavior remain correct.

The owner handles builds and deployment. These checks need no printer connection
or physical print. Do not change Olympus or send a print to validate this patch.
