# Plate filament mapping regression checks

These GUI checks require a build containing the patch. They have not been run
against the running instances; no profile or project format changes are needed.

1. Import a 3MF containing a Manual-mode plate with two `filament_volume_maps`
   entries into a single-filament P1S project (the reported Heaphtus case).
   Slice, wait for completion and the following background settings update.
   The preview must remain populated, Print plate must remain enabled, and the
   log must not immediately reset the G-code result for unchanged settings.
2. Save and reopen that project. Its plate maps should have one entry and an
   unchanged slice should remain valid. Repeat after restoring a project backup.
3. With a dual-nozzle printer and two filaments, test Manual and Nozzle Manual
   modes with distinct valid assignments. Import, slice, then trigger an unchanged
   settings refresh. Both assignments and the selected mapping mode must remain
   unchanged, and the completed preview must remain valid.
4. Repeat with automatic mapping, then add and remove a filament. Existing map
   entries must be preserved, removed entries discarded, and new entries use the
   existing defaults (extruder 1, nozzle 0, Standard volume). Actual setting changes
   must still invalidate the affected slice normally.
5. On Vulcan/X2D, sync with only A1 loaded. There should be one filament selector,
   not a second blank selector. Slice, wait for background refresh and confirm
   Print plate stays enabled. Reopen the project/restart after saving and confirm
   no extra filament appears. Both printer nozzles must remain available.
6. Keep two project filaments but assign geometry only to filament 1. Slice in
   automatic matching mode, wait for refresh and repeat the slice. Both filament
   maps must retain two entries and the completed result must remain valid.
   Assign geometry to filament 2 afterwards: it must invalidate and reslice using
   that filament's configured nozzle and material settings.
