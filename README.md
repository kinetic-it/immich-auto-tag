# immich-auto-tag

Create hierarchical tags in [Immich](https://immich.app/) from an external
library's folder structure. Unlike
[immich-folder-album-creator](https://github.com/Salvoxia/immich-folder-album-creator)
(which flattens folder levels into one album name), this script preserves
Immich's native `/` tag nesting — so `Trip/2026/06` on disk can become the
nested tag `Trip/2026`, with the `06` (month) level skipped entirely.

> **AI assistance disclosure:** This project was built with the assistance of
> an AI coding assistant (Claude). Review the code before running it against
> your own Immich instance, especially before disabling `DRY_RUN`.

> **Not affiliated with Immich.** This is an independent, unofficial
> community tool that talks to the public Immich API. It is not endorsed by,
> sponsored by, or affiliated with the Immich project or its maintainers.

## Status

Early / personal project, validated against a real library (~11,500 assets,
~17 folder-derived tags created successfully). The glob-pattern matching for
`IGNORE` / `PATH_FILTER` is new and less battle-tested than the core
folder-to-tag mapping logic. Use `DRY_RUN=true` (the default) to check the
planned tags before writing anything.

## How it works

1. Fetches all assets from Immich via `POST /search/metadata`.
2. For each asset's `originalPath`, strips `ROOT_PATH` and looks at the
   folder structure below it.
3. Builds a nested tag name from up to `TAG_LEVELS` folder levels.
4. If a level has a configured regex (`TAG_LEVEL_<n>_REGEX`) and the folder
   name doesn't match, the hierarchy stops at the previous level for that
   asset — deeper levels (matching or not) are never included.
5. Creates the tag via `PUT /tags` (idempotent) and assigns it to all
   matching assets via `PUT /tags/assets`, in configurable chunks.

## Example

Folder structure:

```
/mnt/photos/Zoo Trip/2025/06/photo1.jpg
/mnt/photos/Zoo Trip/2026/photo2.jpg
/mnt/photos/Vacation/photo3.jpg
```

With:

```
TAG_LEVELS=2
TAG_LEVEL_2_REGEX=^\d{4}$
```

Results in tags:

- `Zoo Trip/2025` (photo1.jpg — the `06` month folder is skipped)
- `Zoo Trip/2026` (photo2.jpg)
- `Vacation` (photo3.jpg — no matching level-2 folder, so it stops at level 1)

## Configuration

See [`.env.example`](.env.example) for the full list of environment
variables and their meaning.

Required Immich API key scopes: `asset.read`, `tag.create`, `tag.read`,
`tag.asset`.

## Usage

```bash
cp .env.example .env
# edit .env: set API_URL, API_KEY, ROOT_PATH, and your desired tag rules

docker compose run --rm immich-auto-tag
```

Leave `DRY_RUN=true` for the first run to see which tags *would* be created
and how many assets each would get, without writing anything to Immich.
Once the planned tags look right, set `DRY_RUN=false` and run again.

### Without Docker

```bash
pip install -r requirements.txt
export $(grep -v '^#' .env | xargs)
python3 immich_auto_tag.py
```

## Caveats

- `ROOT_PATH` must match the path Immich itself uses internally for the
  external library (i.e. the mount path inside the Immich
  server/container), not necessarily the path on your NAS.
- Bulk-tagging large batches can take a while server-side; a smaller
  `CHUNK_SIZE` gives more frequent progress log lines.
- No automatic cleanup of tags from assets that were moved or deleted —
  unlike immich-folder-album-creator's `SYNC_MODE`, this is not (yet)
  implemented here.

## License

MIT, see [LICENSE](LICENSE).
