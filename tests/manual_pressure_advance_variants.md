# Per-variant pressure advance checks

Adapted from OrcaSlicer #15986. Build and runtime verification are pending.
No saved user presets were edited by this patch. Save a temporary preset copy
when testing; numerical examples below are routing markers, not calibrated values.

1. Open an older filament preset with one PA value. All supported variants should
   initially inherit that value. In Vulcan's filament settings, select Direct
   Drive Standard and Bowden Standard and set distinct temporary PA values,
   such as 0.021 and 0.037. Switch back and forth: each value and its enable
   checkbox must be independent. Save/reopen the temporary preset and repeat.
2. Export a simple project with that filament mapped to each nozzle in turn.
   Verify the emitted PA command (or the PA value used by start/change G-code)
   follows the selected extrusion variant. Test initial filament and subsequent
   filament changes; assigning another filament to that same nozzle must use
   that filament's own variant value. Do not print arbitrary test values.
3. Repeat with adaptive PA using distinct valid models per variant. Each model,
   bridge override and enable state must remain separate, and generated
   PA_CHANGE tags/model predictions must use the resolved configuration column.
4. Save/reopen an older multi-filament 3MF with per-filament PA values. Migration
   must copy each filament's PA to its variants without borrowing the next
   filament's value or changing already variant-specific flow ratios.
5. Export start/change G-code containing pressure_advance[initial_extruder] or
   the appropriate filament-indexed placeholder. It must resolve to the variant
   chosen for that filament, not directly index the expanded variant array.
6. Check PA Line/Pattern/Tower sweeps still emit their requested test values.
   The Bambu calibration wizard still saves its results through the existing
   printer calibration path; this patch does not redirect device K records into
   local filament presets. Enter locally calibrated PA in the selected variant
   and save the filament preset normally.
7. Repeat a normal Heaphtus single-nozzle slice: its existing PA behavior should
   remain unchanged. Recheck one-spool sync, completed slice validity, Ellis
   object settings, mixed nozzle widths and the prior stability fixes.

Automated regression cases cover static/adaptive PA routing on one- and
two-extruder configurations, custom start placeholders, scalar migration and
older multi-filament project migration. They have not been run in this patch.
