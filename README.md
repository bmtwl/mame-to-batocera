# MAME to Batocera Gamelist Converter

A Python utility that transforms MAME DAT files and extras into a Batocera-compatible gamelist.xml and media folder structure.

## Overview

This tool automates the conversion of MAME metadata and media assets into the format required by Batocera's emulation frontend. It handles zipped DAT files, extracts media from extras archives, and intelligently merges with existing gamelist.xml data to preserve screenscraper.fr metadata.

## Why?

I made this because scraping well-known sites was both inefficient and resulted in a very incomplete, unsatisfying experience in Batocera.

Since MAME already _has_ a great Extras setup and DAT (xml) files with a lot of the required information, I made this to leverage these already existing and widely available resources to do a "good enough" job without having to scrape for days and days.

## Features

- Parses MAME DAT files from zip archives (ROMs, CHDs, and artwork)
- Extracts and organizes media files (screenshots, flyers, marquees) from zipped extras. Files work exactly as you downloaded them.
- Generates Batocera-compatible gamelist.xml with proper field mappings
- Merges with existing gamelist.xml, preserving screenscraper.fr metadata
- Hides unplayable games
- Uses relative paths for media files (so it works with remotely mounted filesystems)
- Supports dry-run mode for testing
- Comprehensive logging with verbose output option

## Requirements

- Python 3.6 or higher
- Standard library modules: `argparse`, `os`, `sys`, `tempfile`, `xml.etree.ElementTree`, `pathlib`, `zipfile`, `shutil`, `re`
- Sufficient disk space for temporary file extraction

## Usage

There is no install. Just download the `mame_to_batocera.py` script

### Basic Command

```bash
python3 mame_to_batocera.py \
    --dat-zip "/path/to/mame/dat/files" \
    --extras-dir "/path/to/mame/extras" \
    --roms-dir "/path/to/batocera/roms/mame" \
    --verbose
```

### Command-Line Options

- `--dat-zip PATH`: Path to folder containing just the MAME DAT zip files
- `--extras-dir PATH`: Path to MAME EXTRAs directory containing snap.zip, flyers.zip, etc. (required)
- `--roms-dir PATH`: Path to Batocera ROMs directory where gamelist.xml will be created (required)
- `--extract-temp PATH`: Temporary directory for file extraction (optional, defaults to system temp)
- `--no-merge`: Do not merge with existing gamelist.xml, create from scratch
- `--dry-run`: Show what would be done without making any changes
- `--verbose`: Enable detailed logging output

### Example

```bash
python3 mame_to_batocera.py \
    --dat-zip "/home/user/MAME 0.282 DATs" \
    --extras-dir "/home/user/MAME 0.282 EXTRAs" \
    --roms-dir "/userdata/roms/mame" \
    --verbose \
    --dry-run
```

Remove the `--dry-run` flag to perform the actual conversion after verifying the output.

## Input Requirements

### DAT Files
The script expects the following zipped DAT files:
- ROM DAT zip (e.g., `MAME ROMs (merged).zip`)
- CHD DAT zip (e.g., `MAME CHDs (merged).zip`)
- Artwork DAT zip (e.g., `artwork.zip`)

Each zip should contain a single XML file with game metadata.

### Extras Directory Structure
The extras directory should contain:
- `snap.zip` - In-game screenshots
- `flyers.zip` - Box art/flyers
- `artwork.zip` - Additional artwork including marquees

All media files should be in PNG format at the root of each zip file.

## Output

### Directory Structure
The script creates the following structure in the specified ROMs directory:

```
roms/
└── mame/
    ├── gamelist.xml
    └── media/
        ├── screenshots/
        ├── covers/
        └── marquees/
```

### Gamelist.xml Fields
The generated gamelist.xml includes:
- `path` - Path to ROM file
- `name` - Game title (preserves existing screenscraper data)
- `desc` - Game description (preserves existing screenscraper data)
- `image` - Screenshot path
- `thumbnail` - Thumbnail path (same as screenshot)
- `marquee` - Marquee path
- `video` - Video path (placeholder, preserves existing)
- `rating` - Game rating (preserves existing screenscraper data)
- `releasedate` - Release date in ISO 8601 format
- `developer` - Game developer
- `publisher` - Game publisher
- `genre` - Game genre (defaults to "Arcade")
- `players` - Number of supported players
- `hidden` - Hidden flag for non-working games

## Data Merging Strategy

When merging with an existing gamelist.xml:
- Screenscraper.fr data takes precedence over MAME DAT data
- MAME DAT fills in missing fields only
- Existing games not present in MAME DAT are preserved
- Description, rating, and genre from screenscraper are retained
- MAME data provides fallback for missing metadata

## Supported MAME DAT Fields

The script converts the following MAME DAT fields to Batocera format:
- `description` → `name` and `desc`
- `year` → `releasedate` (converted to ISO 8601)
- `manufacturer` → `developer` and `publisher`
- `input players` → `players`
- `driver status` → `hidden` flag

## Temporary Files

The script extracts files to a temporary directory during processing. By default, it uses the system temporary directory (`/tmp` on Linux). The `--extract-temp` option allows specifying a custom location. Temporary files are automatically cleaned up after completion.

## Troubleshooting

### No XML file found in zip
Ensure the DAT zip files contain XML files with game metadata.

### Media files not found
Verify that extras zips contain PNG files at the root level.

### Permission errors
Ensure write permissions for the target ROMs directory and media subdirectories.

### Existing gamelist.xml not merging
Check that the existing gamelist.xml is valid XML and uses the expected structure.

## Limitations

- Only tested with merged ROMsets/DATs/Extras from pleasuredome
- Only processes PNG format media files
- Does not handle video files
- Does not rename ROM files
- Assumes standard MAME DAT XML structure
- Uses relative paths only
- I basically only ever ran the final version of this script once

## Contributing

Contributions are welcome. Please ensure all changes maintain compatibility with standard MAME DAT formats and Batocera's gamelist.xml specifications.
