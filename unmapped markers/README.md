# Unmapped Texas Historical Markers

Every file in this folder describes **Texas Historical Commission markers that
nobody has documented on [hmdb.org](https://www.hmdb.org) yet** — markers with
no photographs and no field-verified record. Think of them as a hunting list:
each pin is a marker that would benefit from someone driving out, finding it,
and photographing it.

The files are generated from `atlas_db.csv` (the master database in the repo
root) and are refreshed as markers get found and documented. Don't edit them by
hand — a rebuild will overwrite your changes.

## What's in here

| File | What it is |
|---|---|
| `Texas_statewide_unmapped_part1of2.kml` | Western half of the state, one file ready for Google My Maps |
| `Texas_statewide_unmapped_part2of2.kml` | Eastern half of the state, same idea |
| `Texas_statewide_unmapped.kml` | The whole state in a single file (fine for Google Earth or QGIS; also imports into My Maps) |
| `<County>_unmapped_markers.kml` | One county's unmapped markers — handy when you're planning a trip to a specific area |

The two `part` files split the state west/east with counties kept whole, so
each covers a coherent region.

## Importing into Google My Maps

1. Go to [mymaps.google.com](https://www.google.com/mymaps) and sign in.
2. Click **Create a New Map**.
3. In the panel on the left, click **Import** (under the "Untitled layer").
4. Drag in one of the `.kml` files.

That's it — the marker names become pin labels, and clicking a pin shows the
marker's details. The resulting map also appears in the Google Maps app on
your phone (menu → **Saved** → **Maps**), which is what you want in the field.

For the statewide split, import each part into **its own map** if you find one
map sluggish — each file stays comfortably inside My Maps' limits (5 MB per
file, 2,000 features per layer).

## Reading the pins

- **Red pin** — a normal target: drive out and look for it.
- **Orange pin, name starts with `[PENDING]`** — the marker has been approved
  but may not be physically installed yet. Don't make a special trip.

Clicking a pin shows locating notes (directions, landmarks), the address, and
the marker's inscription text where available.

## Trust the pins, but not blindly

Pin positions come from the best coordinate available for each marker:

- Some are **field-verified** (measured at the marker by earlier visitors) —
  these are accurate to a few metres.
- Most are **estimates** derived from the THC's records or geocoded from the
  marker's address. These are usually within a block or two but are
  occasionally far off — treat them as a starting point, and read the pin's
  locating notes before concluding a marker is gone.

## What's deliberately left out

You won't find these in any file here:

- Markers already documented on hmdb.org (they're mapped — mission
  accomplished).
- Markers **confirmed missing** — nothing to find.
- Markers on **private property** — nothing to visit.
- Superseded/duplicate THC records — the physical marker is documented under
  another record.
- Markers with **no coordinate and no usable address** — they can't be pinned.
  They remain in `atlas_db.csv` (empty `estimated:Latitude`) for anyone who
  enjoys detective work.

## Found one?

Photograph the marker (a straight-on shot of the full text, plus a wider
context shot), note the coordinates where it stands, and consider submitting
it to [hmdb.org](https://www.hmdb.org/markeraddfirst.asp) so it drops off this
list for everyone.
