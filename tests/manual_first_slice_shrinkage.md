# First-slice filament shrinkage compensation

Backport of upstream f1658855c8 (PR #16312). Compensation is determined from the
incoming model before constructing PrintObject transformations, rather than from
PrintObjects left over from a previous slice. No profile values or defaults change.

## Manual checks

Use temporary project/filament edits; do not overwrite saved presets. Repeat on
Vulcan and Heaphtus. Compare sliced geometry/toolpaths, not the unscaled Prepare mesh.

1. Start a new project with a 20 mm cube. Set X-Y contour compensation to 0 and
   filament XY shrinkage to 90% (an exaggerated diagnostic value, not a printing
   recommendation). Slice once: the middle-layer slice should be about 22.22 mm
   wide. Force a second slice without changing shrinkage: dimensions must agree.
2. Change shrinkage to 100% and reslice: the middle-layer slice should return to
   20 mm. At 100% XY and Z, existing output should remain unchanged.
3. Separately test 100% XY and 95% Z: the compensated cube should be about
   21.05 mm tall, subject to layer-height rounding. First and repeat slices should
   agree. Restore 100% before testing normal calibration projects.
4. Add an unused filament with a different shrinkage value. It must not disable
   compensation for the filament actually assigned to the object/features.
5. Assign two different shrinkage values to used filaments (including a support,
   feature, modifier, or height-range assignment). Compensation should be disabled
   with the existing shrinkage-mismatch warning, rather than applying one
   material's scale to the other. The check conservatively includes assigned
   features even if those features ultimately produce no toolpaths.
6. Confirm normal Ellis/contour generation and slicing still work with 100% XY/Z,
   and that the recent PA and per-nozzle choices remain unchanged. Non-100% Z
   changes the sliced height and may change calibration disk layer counts.

## Automated coverage

The existing fff_print test files now cover XY/Z scaling, repeat apply, changing
shrinkage after slicing, clearing cached state, unused versus conflicting used
filaments, height ranges, modifiers, physical components of mixed filaments, and
the wipe tower filament. Filter the suite by `*shrinkage compensation*`.

No build or test execution was performed while preparing this patch.
