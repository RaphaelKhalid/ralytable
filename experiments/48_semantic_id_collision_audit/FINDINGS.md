# Loop 29 findings

Status: executed.

The falsification target was an ID sensitive to decorative metadata or silent
hash collisions. Full hashes, truncated hashes with collision checking, and
the unchecked truncated hash all passed equivalence, metadata invariance, and
mutation sensitivity. Only the collision-checked truncated and full hashes
passed the collision test; the unchecked 2-hex-digit hash merged two distinct
literal nodes at ID `94`. Raw hashes failed equivalence and decorative
invariance because metadata ordering/content entered the address.

Decision: canonicalize semantic fields, exclude explicitly decorative
metadata, and require collision detection if digest truncation is used. A
collision rejection path is preferable to silently merging nodes. This is a
narrow identity contract, not evidence of learned coder-model capability.
