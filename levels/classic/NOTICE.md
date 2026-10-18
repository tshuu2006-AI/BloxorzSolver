# Level data notice

The 33 stages in this folder recreate the levels of the Flash game **Bloxorz** by Damien Clarke
(DX Interactive, 2007; widely played on Coolmath Games). The assignment (section 3.1) allows
recreating classic levels. The original game and its level designs belong to their authors.

**Where the layouts came from.** They were converted from the community transcription
`coolmath.json` in <https://github.com/tkoz0/bloxorz-solver> (a Python BFS solver whose README
says its puzzle encodings were checked with an in-game playthrough). That repository states no
license, so please keep this credit, and list the repository in the report's References.
The six-digit passcodes in that file are not used.

**How it was checked.** Each stage JSON has a `reference_moves` field: the minimum number of
rolls published for that stage by the same repository (1999 in total). `tests/test_classic.py`
runs an exhaustive search on every stage with our rules engine and requires the same minimum, so
the conversion and our rules (fragile tiles, switches, bridges, teleporters, split/merge) agree with
the original game on all 33 stages.

**Format changes.** Tiles map as: `.`->`#` floor, `-`->`F` fragile, `H`->`G` goal, `X`->`x` heavy
switch, `O`->`o` soft switch, `B`/`b`->`B` bridge (open/closed at start), `T`->`p` teleporter.
Switch actions `on`/`off`/`swap` become `open`/`close`/`toggle`, and teleporters carry the
original "selected half" as `"active"`.

If the team prefers not to ship third-party data, delete this folder: the game then shows only
`levels/*.json` (our own stages).
