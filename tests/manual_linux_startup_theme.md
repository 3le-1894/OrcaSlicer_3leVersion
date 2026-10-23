# Linux startup theme regression

The initial label colours and cached widget theme flag were computed before
non-Windows desktop appearance detection updated the saved dark-mode setting.
That left custom widgets in light mode while native controls followed the dark
desktop theme. Refresh both after appearance detection, before main UI creation.

On 2026-10-22, Heaphtus startup logs showed cached mode 0 and Vulcan showed 1,
while both saved configurations and desktop appearance were dark. After the owner
rebuilt and deployed the correction, the owner confirmed the graphical issue was
resolved. Windows/macOS and a full light/dark matrix have not been validated.

For repeatable validation, use temporary copied datadirs with cloud sync disabled
and no printer connections. Set the saved theme opposite to the desktop theme in
the copies before launching. Verify both launch orders, the main sidebar, and
Material settings including Notes. All backgrounds, labels, and modified-state
indicators should follow the detected theme. Repeat with a light desktop theme.
Do not edit operational profiles to construct this fixture.
