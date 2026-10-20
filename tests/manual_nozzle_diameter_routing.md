# X2D/H2D nozzle-diameter routing checks

Backport of OrcaSlicer #14125, adapted to the custom sidebar. Pressure advance,
shrinkage compensation and the preceding stability patch are not changed here.
Build and runtime verification are pending.

1. In an unsaved Vulcan project, set the two sidebar nozzle diameters to 0.4
   and 0.6 mm. Both must remain independently selected without the old dialog
   forcing a single diameter. Changing one diameter in the printer settings
   must not mirror it to the other nozzle. Restore the values before any print
   unless those physical nozzles are actually installed.
2. Set wall/support widths to 100% for this check, use a layer height compatible
   with both nozzles, and assign a model to filament 1. Map that filament to each
   nozzle in turn. Reslice: Preview line width must follow the assigned nozzle
   (0.4 or 0.6), not the filament's position in the list.
3. Add a third filament and map it to a nozzle already used by another filament.
   Check wall/infill widths, ironing, brim and support/interface flows follow
   the assignments. Repeat with conventional and tree support. Explicit mm line
   widths remain explicit; they are not expected to scale like percentage widths.
4. Repeat with both nozzles at 0.4 mm. Existing same-diameter results should be
   unchanged. Switching from mixed diameters back to a uniform selection must
   actually restore both diameters, not leave the second at its previous value.
5. Save/reopen the project and confirm diameter values and filament mappings
   persist. Sync with only one spool loaded and confirm only one filament slot
   appears; completed slices must remain valid after the background refresh.
6. Check Heaphtus's single 0.6 mm nozzle still slices normally. PA values,
   calibration object overrides, LAN retention and print-tab preferences must
   be unchanged.
7. Run the two new [Config][Regression] nozzle-diameter tests. They cover swapped
   assignments, multiple filaments per nozzle, fallback and non-Bambu routing.
