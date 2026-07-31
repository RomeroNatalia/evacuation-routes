# Floorplan Correction Log

This file records manual corrections made from marked graph-review images. Generated preprocessing outputs are regenerated after each input correction.

## FP02 — School Administration Building

- Removed all diagonal graph edges.
- Corrected marked exit, door, navigation-node, and hallway positions.
- Added missing nodes and straight horizontal/vertical connections.
- Removed isolated and incorrect nodes.
- Added geometry-audit coverage and overlapping-node rendering offsets.
- Verified one connected component, no isolated nodes, every room reaching every exit, and every door having degree 2.

## FP03 — Dormitory

- Removed the isolated `A2` node.
- Added support for half-column coordinates such as `E_A9`, meaning halfway between columns E and F.
- Moved `DOOR_16` to `E_A9` and `DOOR_21` to `E_A13`.
- Added `F9` and rebuilt the straight Door 15/16 hallway connections.
- Shifted the marked `M:V10.5` and `M:V11.5` node rows to `.25` coordinates.
- Replaced `H14.5` with `H14` and connected `H13–H14–I14`.
- Added `D18`, `D20`, and `E19`; removed the two marked D19 diagonals and replaced them with straight edges.
- Merged unnecessary duplicate navigation nodes ending in `_2`.
- Added `N22` and replaced the marked `N21/O22/N23` diagonals with a straight vertical chain.
- Corrected the marked connections for `DOOR_13`, `DOOR_14`, `DOOR_15`, and `DOOR_26`.
- Added `DOOR_45` at `Q21`, connected to `Q22` and `EXIT_STAIRWELL`.
- Added `D21` and the straight `D20–D21` connection.
- Removed the direct `S20–EXIT_STAIRWELL` shortcut.
- Removed the overlapping `AA13` navigation node and rebuilt the Supply Closet around `DOOR_19` using straight `AA12–DOOR_19` and `AA14–DOOR_19` connections.
- Reconnected `START_R15` through the upper and lower Supply Closet grid so the room remains reachable.
- Updated doorway validation to allow degree 3 only when two straight room-grid branches meet at a single physical doorway.
- Verified no diagonal edges, no long edges over two grid units, one connected component, no isolated nodes, every room reaching every exit, and all doors having valid degree 2 or 3.

## FP04 — Museum

- Moved `START_R06` from `C14` to `D14` and restored `C14` as a normal navigation node.
- Moved `START_R05` from `S8` to `R8` and restored `S8` as a normal navigation node.
- Removed `O13` and `O15`; added `Q13` and `Q15` with straight `Q13–Q14–Q15` connections.
- Added the straight horizontal connections `N13–P13` and `N15–P15` across the intentionally omitted O-column positions.
- Regenerated all FP04 preprocessing outputs.
- Verified no diagonal edges, one connected component, no isolated nodes, every room reaching every exit, and every door having degree 2.

## FP05 — Clinic

- Added the marked room-center connections `START_R08–C7`, `START_R04–E7`, `START_R05–G7`, `K7–START_R06`, `M7–START_R07`, and `O7–START_R03`.
- Added the marked bathroom connections `L12–START_R10` and `N12–START_R11`.
- Added the missing straight hallway connection `P32–P33`.
- Renamed `B27.5`, `C27.5`, `F27.5`, `G27.5`, `I27.5`, and `J27.5` to `B28`, `C28`, `F28`, `G28`, `I28`, and `J28`, updating all incident edges.
- Removed the old `DOOR_26–J28` connection and added the straight `DOOR_26–I28` connection.
- Removed the overlapping `N12` navigation node, moved `START_R11` from `O12` to `N12`, removed its former `O11` connection, and connected it directly to `N11`; `DOOR_15` remains at `O12`.
- Regenerated all FP05 preprocessing outputs.
- Verified no diagonal edges, no edges longer than two grid units, one connected component, no isolated nodes, every room reaching every exit, and every door having degree 2.

### FP05 follow-up: Bathroom B doorway connection

- Added the straight edge `START_R11–DOOR_15`.
- `START_R11` remains at `N12`; `DOOR_15` remains at `O12`.
- The doorway now has three valid straight connections.
