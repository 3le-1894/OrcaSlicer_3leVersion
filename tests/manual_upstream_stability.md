# Upstream stability backport checks

Sources: OrcaSlicer PRs #16599 (send-dialog panel selection), #16649 (unused
preset-recording race), and #16065 (release discarded preview buffers).
Shrinkage compensation and print-completion navigation are not changed.

Build/runtime verification is pending; these steps have not been run by the patch.

1. With a single-nozzle slicing profile selected and a plate sliced, open Print
   plate and select Vulcan/X2D as the destination. The dialog must not crash and
   material items must stay in the single mapping panel. Cancel without printing.
2. With Vulcan's normal two-nozzle profile, check both a one-filament plate and a
   two-filament plate assigned across both nozzles. Open Print plate and confirm
   the existing left/right mapping and selections are preserved. Cancel.
3. Slice and reslice a multi-filament project several times. Confirm the completed
   preview stays valid. The removed recorder must not have any remaining callers
   or declaration (`rg record_slice_preset src` should have no matches).
4. Load a large G-code preview, then clear the project or replace it with a small
   file. Confirm toolpaths/colors reload correctly and CPU memory usage drops as
   discarded toolpath buffers are released. OS process memory need not drop by
   the exact buffer size, since other allocators and caches can retain memory.
5. Run the fff_print test tagged [GCodeProcessor][Regression]; repeated reset must
   leave both moves and line-end vectors empty with zero capacity.
6. On the next intended print, confirm existing LAN connection retention and the
   current switch-to-Device preference still behave as before.
