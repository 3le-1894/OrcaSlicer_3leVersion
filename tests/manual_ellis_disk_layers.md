# Ellis disk layer-count regression checks

Requires a build containing the patch; runtime checks have not yet been run.

1. On Heaphtus, select 0.24 mm layer height and 0.30 mm initial layer height.
   Generate a NEW Ellis Extrusion Multiplier test, then slice. Each 3 mm disk
   should have 12 body layers: 2 bottom, 2 sparse and 8 top-shell layers. The
   raised labels are above the disk and do not count toward these 12 layers.
   Sparse infill should be present at Z 0.78 and 1.02 mm. The first internal
   bridge belongs to the top shell, not the sparse-layer count.
2. Repeat with 0.16 / 0.20 mm and 0.20 / 0.20 mm layer/initial-layer heights.
   Confirm exactly two sparse layers in the disk body for both profiles.
3. Generate a NEW Contour Compensation test with 0.24 / 0.30 mm. It shares
   the shell setup and should likewise have two sparse layers and eight top
   layers, with no changes to its 50 mm diameter or 3 mm modeled height.
4. Confirm the shell/infill overrides remain on the calibration objects only;
   global process settings and saved profiles must remain unchanged.
5. Existing generated disks retain their old object overrides. Regenerate the
   test to verify this fix rather than merely reslicing an older project.
