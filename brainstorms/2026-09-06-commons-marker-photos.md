# Wikimedia Commons marker photos: Brainstorm / Discovery Notes
Date: 2026-09-06 · Goal: a plan for (1) inventorying Joe's existing Commons uploads of THC markers, (2) normalising their metadata from atlas_db.csv to a defined format, (3) matching Immich photos to atlas markers and picking one best photo each, (4) uploading the missing markers with that format.

## Summary / key decisions — the plan

**Scope.** One photo per atlas row (thc#): whole plate frontal and readable, post/medallion included, no people; medallion-only RTHLs → the medallion. Subject photos (`subject:wikimedia_commons`) out of scope and never edited. Superseded rows (isActive=False) and missing markers are in scope (historical record). Everything in Immich is Joe's own work.

**File page format (new uploads and rewritten existing files).**
- Filename: `Historical Marker-<atlas name>.jpg`; on collision `Historical Marker-<name> (<County> County, Texas).jpg`; same-county collision adds the city. Existing files are never renamed.
- `{{Information}}`: identification line (marker #thc, "name", city, county, "Erected <start_date>", "Recorded Texas Historic Landmark" when RTHL; "Marker reported missing as of <date>" / "superseded by marker #N" when applicable) + the full inscription from atlas `Marker Text` (atlas text is complete; only OSM's 255-char tag limit truncates) + References: THC atlas URL and hmdb URL (atlas only when no hmdb link). `date` = photo EXIF date (existing files keep their date), `source` = `{{own}}`, `author` = HominyGrits007, `{{Location}}` = atlas verified coordinate.
- License **CC0 1.0**. Caption (en): `Texas Historical Commission marker <thc#>: <name> (<city>, <County> County, Texas)`.
- SDC: copyright status public domain + license CC0; creator HominyGrits007 (Wikimedia username); source of file = original creation by uploader; inception = EXIF date; depicts = historical marker; coordinate location = atlas verified coord.
- Categories: always `Texas Historical Commission plaques in <County> County, Texas`; RTHL rows also `Recorded Texas Historic Landmarks in <County> County`; nothing else by hand; never remove others' categories; own files moved out of the typo category `…plaques in tarrant`.

**Category creation (before any upload).** Create every missing `Texas Historical Commission plaques in <County> County, Texas` (131) with the verbatim wikitext `{{Counties of Texas|prefix=:Category:Texas Historical Commission plaques in|suffix=}}` / `[[Category:Texas Historical Commission plaques by county|<County>]]` / `[[Category:Historical markers in <County> County, Texas]]`, and its missing parent `Historical markers in <County> County, Texas` (~152) as `{{Counties of Texas|prefix=:Category:Historical markers in|suffix=}}` / `[[Category:Historical markers in Texas by county|<County>]]` / `[[Category:History of <County> County, Texas]]` / `[[Category:Signs in <County> County, Texas]]`. RTHL county categories (231 exist) only when a file needs one.

**Phase 1 — inventory existing uploads.** All 344 HominyGrits007 uploads are candidates. Match to atlas rows on: atlas `wikimedia_commons` naming the file; description vs `Marker Text`; filename/caption vs name confirmed by county; EXIF GPS from the Immich original (Commons sha1 == Immich checksum) within the distance tiers. One strong or two agreeing weak signals → auto; otherwise review CSV. Subject photos: atlas `subject:wikimedia_commons` → subject; inscription in description → marker; the ~134 unclassified + odd cases classified by Claude viewing thumbnails; Joe confirms only subject/uncertain verdicts; verdicts stored in the atlas columns. Confirmed marker matches write `File:` into `wikimedia_commons`.

**Phase 2 — normalise matched files.** Regenerate the whole `{{Information}}` block (overwrite whatever was there, no salvage), keep everything else on the page and all categories (add county/RTHL), set caption + SDC, only own files, never subject photos, one batch edit summary.

**Phase 3 — match Immich photos to markers.** Candidates: geotagged assets (any date) within 30 m of the verified coord, 60 m for estimated-only rows. Tiers: ≤15 m auto-pick; 15–30 m only with strong CLIP marker-likeness + OCR plate-title match + visual check, else ask Joe; estimated-coord rows always ask. Drop already-on-Commons (checksum) and bursts; rank CLIP → distance → recency. Pick check: OCR must find the atlas name on the plate and the plate must be THC design (guards against city/county markers standing nearby). Claude picks as many as possible; only low-confidence markers go to Joe; markers with only subject shots nearby get no upload and a note.

**Phase 4 — upload.** Originals untouched (full res, EXIF+GPS). One photo per marker from Joe (any prior own file for the marker blocks a second); other people's photos never block. Joe's file replaces another person's in the atlas `wikimedia_commons` slot; OSM follows on the next tag push. Duplicate-thc# rows: own photo per row when positions differ, shared file when they coincide.

**Tooling.** Bot password `HominyGrits007@thc-toolkit` (grants: basic, high-volume editing, edit existing pages, create/edit pages, upload new files, upload/replace files) in `~/.config/thc-toolkit/commons.env` + Vaultwarden; plain `requests` against api.php with a Wikimedia UA. Everything lives in **`.claude/skills/commons-sync/`** (real directory, gitignored, backed up by the machine backups, never pushed): `inventory.py`, `categories.py`, `normalise.py`, `match.py`, `upload.py`, `references/decisions.md`, ledger `state/commons_uploads.csv` (thc#, file, sha1, Immich asset, date, phase) as resumable state and the one-per-marker check. Only atlas column changes are committed. `hmdb-update`'s last step becomes "run commons-sync".

**Order and gates.** (1) bot password, read-only inventory sanity run; (2) categories; (3) inventory + classification, Joe sees subject/uncertain rows; (4) normalise dry-run, Joe looks at 2–3 rendered pages, apply; (5) match, low-confidence picks to Joe with thumbnails; (6) upload dry-run list, first run capped at ~20 files, then batches of ~50 a few seconds apart; (7) after each batch: atlas updated, SQLite rebuilt, ledger written, verification re-reads every touched page (caption, thc#, county category, no "missing SDC copyright license"). Corrections (wrong marker → fix in place; non-marker/self-duplicate → speedy deletion; bad batch → revert by summary) are proposed with evidence and applied only after Joe verifies. hmdb-photo tiebreaker deferred.

## Discovered before Q1 (looked up, not asked)
- Commons account: **HominyGrits007** (userid 7941427, registered 2019-07-15, 1,108 edits, autoconfirmed, no bot flag). Latest uploads 2026-09-02: `Historical_Marker-R._N._Younger_Home.jpg`, `Historical_Marker-Bennett-Richardson_House.jpg`, `Historical_Marker-Mary_Florence_Cowell.jpg`.
- Existing upload shape (2026 files): filename `Historical Marker-<atlas name>.jpg`, license **CC0**, description = the marker inscription text, categories `CC-Zero`, `Self-published work`, plus the maintenance category **"missing SDC copyright license"** (structured data incomplete).
- atlas_db.csv: 966 rows carry `wikimedia_commons`; 98 of them are `File:Historical_Marker-*` (Joe's pattern), 868 are other people's files (e.g. `File:Texas Electric Railway Allen Marker 127.jpg` by Jphill19, CC BY-SA 4.0, category "Texas Historical Commission plaques in Collin County, Texas"). 136 rows carry `subject:wikimedia_commons`.
- 11,989 atlas rows are hmdb-linked with a verified coordinate and have no `wikimedia_commons` value.
- Immich: 20,245 geotagged assets; 289 atlas rows with a verified coord have ≥1 photo within 30 m (953 photos), 48 estimated-coord rows have one within 60 m. Immich smart search ("historical marker", CLIP) ranks marker photos well; `/api/map/markers` gives every asset position in one call, so matching needs no downloads. Pull script prototype: `scripts/tmp/immich_pull.py`; key at `~/.config/thc-toolkit/immich.env` and in Vaultwarden.
- No Commons tooling in the repo yet (`wikimedia_commons` only flows atlas → OSM tags and OSM → atlas). Memory rule: reverse-flow `wikimedia_commons` OSM → atlas before any forward push.
- Inventory baseline (Commons `allimages` by user): **344 uploads** by HominyGrits007 — 114 `Historical_Marker-*`, 46 other names containing "marker", 184 without "marker" in the name (Denton parks, charging stations, courthouse…; some may still be marker photos). By year: 2021 22 · 2022 21 · 2023 82 · 2024 17 · 2025 31 · 2026 171.
- Category tree on Commons (looked up 2026-09-06): `Texas Historical Commission plaques in <County> County, Texas` exists for 123 counties (parent `Texas Historical Commission plaques by county` + `Historical markers in <County> County, Texas`); `Historical markers in <County> County, Texas` exists for 102 Texas counties; `Recorded Texas Historic Landmarks in <County> County` (no ", Texas") exists for 231 counties. Malformed: `…plaques in Goliad County` is a category redirect (0 files), `…plaques in tarrant` is a red category with 1 file. `Texas Historical Commission plaques` (root) holds 35 files.
- Joe's own files in the atlas: 158 referenced by `wikimedia_commons` (marker photos), 52 by `subject:wikimedia_commons` (subject photos, e.g. `Bedford Cemetery.jpg`, `Cooke County Courthouse.jpg`, and oddly `Historical Marker-Ash Creek Baptist Church.jpg`), 29 rows use one of his files for both. ~134 of the 344 are classified by neither column.
- **Commons ↔ Immich exact linkage works:** Joe uploads originals unmodified, so Commons `imageinfo.sha1` == Immich asset `checksum` (base64 SHA1). Verified on `Historical Marker-Mary Florence Cowell.jpg` → Immich asset 79761461 (`20260830_094835.jpg`); Immich `search/metadata` accepts `checksum` as a filter. Gives: EXIF GPS/time for every existing upload (phase 1 signal), and exact "already on Commons" detection for phase 3.
- Radius calibration (Joe: "30m seems far"): 130 of his existing marker uploads resolved to Immich originals with GPS; distance photo→atlas verified coord: median 4.7 m, p75 9.4 m, p90 19.4 m, p95 25.9 m, max 129 m. Within 10 m 98, 15 m 109, 20 m 119, 30 m 125. Outliers: Riverside Methodist Church 30 m, General W. J. Worth 52 m, Hotel Texas 64 m, Pioneer Birdville Schools 100 m, E. M. Daggett 129 m (tall downtown buildings / marker moved?).
- Edge-case sizing among the 289 rows with photos ≤30 m: 170 already have a `wikimedia_commons` file (most of them Joe's own → skipped by the one-per-marker rule; ~119 new uploads expected from today's library), 85 are RTHL designations (medallion likely the photo), 5 have no hmdb link, 3 are isMissing=True, 1 sits in a duplicate-thc# group, 0 isActive=False.

## Q&A log
### Q1 — what counts as "the" marker photo
- Asked: one photo per thc#, frontal readable plate incl. post/medallion, no people; medallion-only for medallion RTHLs; subject photos out of scope for now?
- Captured: **agreed** as recommended.
- Flags: none

### Q2 — filename convention + existing files
- Asked: keep `Historical Marker-<name>.jpg`, county suffix only on collisions (rec.) vs thc# always?
- Captured: Joe leans **county suffix when duplicated**; confirmed as the decision since the thc# will be carried in description/caption/SDC, so the filename need not be machine-parseable. Never rename existing files.
- Also captured (Joe): the file page must include **the thc ref#, the THC atlas URL and the hmdb URL** (caption or description), and the category **"Texas Historical Commission plaques in <XX> County, Texas"**.
- Looked up: that category exists for 123 counties, missing for 131 (Andrews, Angelina, Armstrong, Bailey…); two malformed variants exist ("…in Goliad County", "…in tarrant"). Collin's parents: `Historical markers in Collin County, Texas`, `Texas Historical Commission plaques by county`.
- Flags: category creation policy → resolved in Q5

### Q3 — description block
- Asked: `{{Information}}` layout with identification line, inscription, References (atlas + hmdb URLs), EXIF date, {{own}}, author, {{Location}} from the verified coord; inscription from hmdb for linked rows because atlas text is truncated; include erected year + RTHL.
- Captured: (1) **Correction from Joe**: atlas `Marker Text` is NOT truncated — OSM's tag length limit is what truncates on push. "I would pull from atlas_db and not hmdb." Verified: 16,112 texts, max 5,114 chars, no cap signature. Memory `feedback_no_inscription_push` rewritten accordingly. (2) Erected year + RTHL in the identification line: **OK**.
- Flags: none

### Q4 — caption + structured data + license
- Asked: caption format; SDC set (copyright/license, creator, source, inception, depicts, coordinates); keep CC0?
- Captured: **CC0 confirmed.** Caption and SDC set accepted as recommended (no additions, no removals raised).
- Flags: none

### Q5 — categories + county category creation
- Asked: always county plaque cat, RTHL cat when RTHL, nothing else, create missing county cats lazily, existing files get cats added not removed; or create all 131 up front?
- Captured: **create all counties first, before uploading** (Joe). Joe supplied the index page `Category:Texas Historical Commission plaques by county` and the canonical wikitext (Denton example): `{{Counties of Texas|prefix=:Category:Texas Historical Commission plaques in|suffix=}}` + `[[Category:Texas Historical Commission plaques by county|Denton]]` + `[[Category:Historical markers in Denton County, Texas]]`. Verified identical on Anderson. Rest of the recommendation stands (RTHL cat when RTHL, no topic cats, never remove others' cats, fix the "tarrant" typo cat for own files).
- Looked up: the parent `Historical markers in <County> County, Texas` is itself missing for ~152 counties; its shape recorded above so both levels get created in the same pass.
- Flags: none (category-creation flag resolved)

### Q6 — phase 1 inventory + matching existing uploads
- Asked: all 344 as candidates, four-signal matching, review-CSV gate, reverse flow into `wikimedia_commons`; or hand-classify the 230 non-prefixed files?
- Captured: **agreed, treat all as candidates**; matching/review/reverse-flow as recommended.
- Flags: none

### Q7 — phase 2 rewrite policy
- Asked: regenerate the Information block, keep date/other content/categories, set caption+SDC, own files only, batch summary; salvage hand-written non-inscription text under "Notes"?
- Captured: "regenerate the whole information block and rewrite anything I previously had" — **no salvage**. Exception: "a small minority of images that are subject and not the actual marker itself. I don't want to change anything on those, but I don't know how to identify a photo that is not a marker."
- Flags: subject-photo identification method → Claude to propose (Q7b)

### Q7b — identifying subject photos
- Asked: atlas columns first, inscription-in-description signal, Claude views thumbnails for the rest and writes a review CSV, verdicts stored in the atlas; OK for Claude to classify visually?
- Captured: **"you can classify."**
- Flags: none

### Q8 — Immich matching + best photo
- Asked: 30 m / 60 m radius, checksum + burst dedup, CLIP → distance → recency ranking, auto top pick with a top-3 review CSV; is 30 m right, and review step or straight to upload?
- Captured: "I want you to pick as many as possible, but if there is low confidence you can ask me." → auto-pick with visual confirmation; ask only on low confidence. Radius not disputed (30 m stands; revisit if matches look sparse).
- Flags: none

### Q8b — distance tiers
- Asked: ≤15 m auto, 15–30 m needs CLIP + visual else ask, >30 m not searched (60 m for estimated rows, always ask)?
- Captured: **agreed.** "I stand close to markers when I take a photo so they should be quite close. There are use cases where I take photos not so close, but those feel rare."
### Q9 — uploads vs existing photos by others
- Asked: upload originals untouched, paced batches; markers already carrying another person's photo?
- Captured: Joe reframed: "if I have a photo of Marker X but someone has already uploaded a photo of Marker X … I don't mind duplicate authors, I don't want duplicate photos that I took." → upload his photo regardless of others; never upload a second photo of his own for the same marker.
- Flags: resolved in Q9b

### Q9b — atlas `wikimedia_commons` precedence
- Asked: leave occupied slots (other people's files) alone, track Joe's upload in a ledger; or Joe's photo always wins?
- Captured: rare case, "I typically only focus on finding the 'unmapped' markers, or markers without images … in that case I would rather use mine." → **Joe's file replaces the other person's in the atlas** (and OSM follows). Ledger kept regardless.
- Flags: none

### Q10 — auth + client
- Asked: bot password + requests (rec.) vs OAuth / Pywikibot?
- Captured: **"bot password and requests"**.
- Flags: Joe to create the bot password and write `~/.config/thc-toolkit/commons.env` (COMMONS_USER, COMMONS_BOT_PASSWORD) before phase 1 writes → Joe

### Q11 — packaging / routine
- Asked: first-class `thc commons` in the toolkit + `commons-sync` skill + ledger in data_files, hooked into hmdb-update; or lighter skill scripts?
- Captured: "You decide … I don't want to commit and push this to github for other people to use … personal activity." → **Decision: skill scripts only, in `.claude/skills/commons-sync/` (gitignored), ledger beside them, no toolkit module, no tracked data file.** Atlas column edits still committed.
- Flags: none

### Q12 — execution order + gates
- Asked: the 7-step order with two look-points (normalise examples, first 20 uploads)?
- Captured: **"yes, I agree"**.
- Flags: none

### Q13 — authorship of Immich photos
- Asked: all photos in Immich taken by Joe? else what distinguishes others' photos?
- Captured: **"Yes, everything in immich was taken by me."**
- Flags: none

### Q14 — edge cases
- Asked: upload missing markers with a note; per-row photos in duplicate-thc# groups; no-hmdb rows fine; superseded rows never uploaded?
- Captured: "I think the superseded rows would be uploaded per the same rationale as missing markers" → superseded rows ARE matched and uploaded; the plate wording assigns the photo to the superseded vs the active row (looked up: the 5 isActive=False rows are replaced/reissued/duplicate records, not different markers). Rest accepted.
- Flags: none

### Q15 — corrections + verification
- Asked: fix-in-place for wrong-marker photos, speedy deletion only for non-markers/self-duplicates, revert-by-summary for bad batches, post-run verification?
- Captured: "I generally agree, but I'd like to manually verify before 'fixing'" → corrections are proposed with evidence and applied only after Joe's OK.
- Flags: none

### Q16 — completeness backstop
- Asked: hmdb photo as tiebreaker (default skip), timing (after bot password), anything else?
- Captured: "there may be some city or county historical marker photos in immich. However they are not documented in atlas_db so I don't think you would even identify these as possible markers." → true for matching, but a city marker beside a THC marker could be mis-picked; added the OCR plate-title check + THC plate-design check to the pick criteria. Defaults on hmdb tiebreaker and timing accepted by silence.
- Flags: none

## Open flags (pending input)
- Create the Commons bot password and `~/.config/thc-toolkit/commons.env` → Joe (needed before any write; reads work without it)

## Build notes (2026-09-06, after the interview)
- Skill built at `.claude/skills/commons-sync/` (scripts: commons_api, immich_api, render, inventory, categories, normalise, match, upload, verify; SKILL.md; references/decisions.md). Read-only steps run; nothing written to Commons or the atlas.
- Refinements made while building: `{{Object location}}` (the marker's own coordinate) instead of `{{Location}}`; SDC coordinate as P1259 only when the file has none (Commons' EXIF-derived one stays); depicts = Wikidata Q127432731 "Texas Historical Marker" (+ Q7302881 RTHL) rather than the generic plaque item; county category pages omit `History of…`/`Signs in…` parents that do not exist (265 absent); the rewrite drops a county category of our own family whose county differs from the atlas (e.g. Mary Florence Cowell filed under Cooke as well as Grayson).
- Inventory result: 344 files → 176 marker photos, 59 subject photos, 109 other (Redmond WA parks, Denton parks, charging station…). 213 auto-matched to a thc#; 4 manual overrides (Pickettville → thc#4872, Richard Williams keyed on hmdb 307955, Denton County 1207 and Van Zandt 2936 promoted after visual title match). 172 files eligible for phase-2 normalisation.
- Categories: 131 plaque + 152 markers county pages missing (283 creates) — dry-run rendered, waiting for the bot password.
- Match (read-only, with OCR): 176 markers have an un-uploaded photo of Joe's nearby (680 candidates; 167 markers already hold one of his files). Tiers: auto 86, auto-ocr 18, check 24, ask 48 (estimated-coord rows); 23 of the 176 are flagged missing, 2 superseded. OCR read the atlas name on 72 of the 104 auto picks; the other 32 go through the visual check before upload. Biggest counties: Denton 41, Marion 28, Tarrant 25, Dallas 21.
- **Q5 revised by Joe during the first apply run:** do not create `Historical markers in …` pages; create the plaque category only for counties with a photo available. Run stopped at 61 pages (30 markers-kind, 31 plaque pages for counties without photos; Andrews→Deaf Smith). Under the new rule only Lamar, Presidio and Runnels were still missing among the 22 photo counties.
- **Q5 final (evening):** Joe reconsidered — plaque category pages for ALL Texas counties (97 remaining created after he reviewed the county list); `Historical markers in …` pages are not created (the 30 made before the stop remain). Always list the counties before an apply run.
- **Categorising other people's files (evening):** 763 files by other uploaders received their county plaque category across 162 counties — atlas-known 27, matcher auto 290 (phrase + broader search + depicts), county-only resolution 376, Joe's two review-game rounds 91 (534 files judged, 428 'not a marker'), hand review 4. 1,278 low-confidence photos parked unreviewed at Joe's request (`state/categorise_others_parked_search.csv`). Review game: `scripts/review_game.py` (localhost:8765, verdicts CSV, --apply).
