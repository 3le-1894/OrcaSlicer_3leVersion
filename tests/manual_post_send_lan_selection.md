# Preserve the selected LAN connection after transfer

## Evidence and scope

Two owner-observed Heaphtus crashes on 2026-10-22 occurred roughly ten seconds
after `print_job: send ok.`. Both logs show same-printer LAN disconnect/reconnect
immediately after transfer; both systemd stacks end inside the 02.08.01 networking
plugin at offset 0x362f35, through bambu_network_send_message_to_printer. A plugin
connection-lifetime race is suspected, not proven.

The candidate mitigation skips redundant same-LAN-printer selection in
Plater::print_job_finished. It does not rely on transient connection-health flags.
Ordinary device selection/reconnect, different-printer selection, cloud selection,
and the switch-to-monitor preference retain their existing paths. It neither
retries the print nor sends an extra print command. The mitigation does not
establish that the closed plugin has no other lifetime or threading issues.

## Source review / offline GUI fixture

Exercise the completion handler with a fake device manager and no network plugin:

- Already-selected LAN target, including stale/disconnected status: no selection
  call, reset, disconnect, or connect should occur due to completion handling.
- Different target or no current target: retain the existing selection call.
- Already-selected cloud target: retain the existing selection call.
- Switch-to-device preference off: no forced monitor-tab navigation.
- Preference on: retain monitor navigation and status-panel selection.

No executable fake-device fixture exists for this handler in this patch. These
branches were reviewed statically; the executable fixture remains pending. After
building and deploying the mitigation, the owner reported no further crashes
observed so far. This is provisional runtime evidence, not proof that all plugin
lifetime races are resolved. The existing five cloud/height regression cases do
not cover this path.

The owner handles builds and deployment. Any validation involving a physical
printer requires explicit owner approval; do not send a print solely to reproduce
this crash. For an owner-approved normal send, look for the new
`print_job_finished: keeping the selected LAN connection after transfer` message,
absence of a completion-triggered reconnect, and continued device status updates.
