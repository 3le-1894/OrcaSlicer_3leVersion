# Dual-nozzle preset reliability continuation

Adapted from upstream OrcaSlicer #16355 (cloud variant layout), #16075 (variant UI),
and #16313 (height validation). Base: custom commit
510b1b10a70623801017e0df66de9e26032fe801.

The owner handles builds and deployment. On 2026-10-22, the owner-built Linux
runtime passed all five targeted CTest cases (cloud round-trips and build-height
checks) and was installed using the local updater. This does not validate real
cloud synchronization or printer interaction. The broader GUI checks, existing
routing suites, and a known companion slicing job remain pending.

## Automated regression checks for the owner

- `libslic3r_tests "*synced to the cloud*"`: in-memory serialization and reload;
  no external cloud service is called. Covers four process/nozzle variants,
  legacy payloads missing layout metadata, a legacy scalar value, filament
  temperatures, and nullable retraction overrides.
- `fff_print_tests "The build height check*"`: compensated models that fit,
  models that exceed height only after Z compensation, already-oversized models,
  raft height, and a single generated layer above the volume limit.
- Existing PA variant routing, nozzle routing, and first-slice shrinkage
  regression checks must also pass. Their source files and manual procedures
  are retained in this fork.

These suites require an owner-configured test build (`BUILD_TESTS=ON`). The five new targeted cases passed in the owner build; existing routing suites
and broader runtime checks are not yet verified.

## GUI checks for an owner-built test runtime

Use temporary copies of Vulcan and Heaphtus data; disable cloud preset sync in
those copies and do not connect to printers or send a print.

1. In the dual-nozzle configuration, change a per-nozzle process value. Both the
   selected and unselected variant buttons must retain their modified-state
   indicators when switching variants. Switching to a page without variant
   controls must clear stale indicators.
2. Repeat with filament variants, including nullable overrides. Reloading or
   changing the selected preset must not leave old modified-state colors behind.
3. Check the per-nozzle icons and checkbox alignment on Setting Overrides;
   inspect light/dark themes and non-default display scaling. The icon and sync
   button must rescale correctly.
4. Confirm the existing independent nozzle-diameter cards and their mappings are
   unchanged. Check the single-nozzle Heaphtus configuration and the existing
   guard that hides variant controls for non-variant multi-extruder printers.
5. Confirm the custom calibration menus, PA behavior, first-slice shrinkage,
   retained LAN behavior, and completed-slice preservation remain unchanged.

The sidebar font/card overhaul and later scrolling-switch implementation are not
imported: this adapts the relevant modified-state and icon/alignment behavior to
the custom controls already present. Bambu network plugin support stays unchanged
at the existing supported ABI series; #16202 is deliberately excluded.
