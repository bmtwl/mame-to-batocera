#!/usr/bin/env python3
"""
MAME to Batocera gamelist.xml converter
Handles zipped DAT files and zipped extras, merges with existing gamelist.xml
"""

import argparse
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import zipfile
import shutil
import re
from datetime import datetime

class MameToBatocera:
    def __init__(self, dat_zip_path: str, extras_dir: str, roms_dir: str, 
                 extract_temp: Optional[str] = None, no_merge: bool = False,
                 dry_run: bool = False, verbose: bool = False):
        self.dat_zip_path = Path(dat_zip_path)
        self.extras_dir = Path(extras_dir)
        self.roms_dir = Path(roms_dir)
        self.extract_temp = Path(extract_temp) if extract_temp else Path(tempfile.mkdtemp(prefix="mame2batocera_"))
        self.no_merge = no_merge
        self.dry_run = dry_run
        self.verbose = verbose

        # Media subdirectories in Batocera
        self.media_dir = self.roms_dir / "media"
        self.screenshots_dir = self.media_dir / "screenshots"
        self.covers_dir = self.media_dir / "covers"
        self.marquees_dir = self.media_dir / "marquees"

        # Ensure directories exist
        self.media_dir.mkdir(exist_ok=True)
        self.screenshots_dir.mkdir(exist_ok=True)
        self.covers_dir.mkdir(exist_ok=True)
        self.marquees_dir.mkdir(exist_ok=True)

        # Track processed games
        self.processed_games: Set[str] = set()

    def log(self, message: str, level: str = "INFO"):
        """Log message if verbose mode is enabled"""
        if self.verbose or level in ["ERROR", "WARNING"]:
            print(f"[{level}] {message}")

    def extract_xml_from_zip(self, zip_path: Path) -> Optional[Path]:
        """Extract XML file from a zip and return its path"""
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                xml_files = [name for name in zf.namelist() if name.endswith('.xml')]
                if not xml_files:
                    self.log(f"No XML file found in {zip_path}", "ERROR")
                    return None
                if len(xml_files) > 1:
                    self.log(f"Multiple XML files found in {zip_path}, using first one", "WARNING")

                xml_file = xml_files[0]
                extract_path = self.extract_temp / f"{zip_path.stem}_{xml_file}"
                zf.extract(xml_file, self.extract_temp)
                # Rename to avoid conflicts
                (self.extract_temp / xml_file).rename(extract_path)
                return extract_path
        except Exception as e:
            self.log(f"Failed to extract XML from {zip_path}: {e}", "ERROR")
            return None

    def parse_dat_xml(self, xml_path: Path) -> Dict[str, Dict]:
        """Parse MAME DAT XML and return game metadata dictionary"""
        games = {}
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()

            # Handle different root element names (datafile vs. mame)
            if root.tag == 'datafile':
                game_elements = root.findall('machine')
            else:
                game_elements = root.findall('game')

            for game_elem in game_elements:
                rom_name = game_elem.get('name')
                if not rom_name:
                    continue

                # Skip BIOS and mechanical if they have appropriate attributes
                is_bios = game_elem.get('isbios') == 'yes'
                is_mechanical = game_elem.get('ismechanical') == 'yes'
                is_device = game_elem.get('isdevice') == 'yes'

                # Extract basic metadata
                game_data = {
                    'name': rom_name,
                    'description': game_elem.findtext('description', ''),
                    'year': game_elem.findtext('year', ''),
                    'manufacturer': game_elem.findtext('manufacturer', ''),
                    'isbios': is_bios,
                    'ismechanical': is_mechanical,
                    'isdevice': is_device,
                }

                # Extract input/players info if available
                input_elem = game_elem.find('input')
                if input_elem is not None:
                    players = input_elem.get('players')
                    if players:
                        game_data['players'] = players

                # Extract driver status if available
                driver_elem = game_elem.find('driver')
                if driver_elem is not None:
                    game_data['driver_status'] = driver_elem.get('status', '')
                    game_data['driver_emulation'] = driver_elem.get('emulation', '')

                games[rom_name] = game_data
                self.log(f"Parsed metadata for {rom_name}")

        except Exception as e:
            self.log(f"Failed to parse DAT XML {xml_path}: {e}", "ERROR")

        return games

    def extract_media_from_zip(self, zip_path: Path, media_type: str) -> Dict[str, str]:
        """Extract media files from zip and return mapping of rom_name -> filename"""
        media_map = {}
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for info in zf.infolist():
                    if info.filename.endswith('.png'):
                        # Extract filename without extension
                        base_name = Path(info.filename).stem

                        # For artwork zip, handle special naming
                        if media_type == 'artwork':
                            # Look for flyer, marquee, snap patterns
                            if 'flyer' in info.filename.lower():
                                media_map[base_name.split('_')[0]] = info.filename
                            elif 'marquee' in info.filename.lower():
                                media_map[f"{base_name.split('_')[0]}_marquee"] = info.filename
                            elif 'bezel' in info.filename.lower() or 'snap' in info.filename.lower():
                                # Skip bezels and snaps from artwork for now
                                continue
                        else:
                            # Direct mapping for snap.zip and flyers.zip
                            media_map[base_name] = info.filename

            self.log(f"Found {len(media_map)} {media_type} images in {zip_path}")
        except Exception as e:
            self.log(f"Failed to process media zip {zip_path}: {e}", "ERROR")

        return media_map

    def get_media_from_extras(self) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
        """Extract and map media files from extras zips"""
        snap_map = {}
        flyer_map = {}
        marquee_map = {}

        # Process snap.zip
        snap_zip = self.extras_dir / "snap.zip"
        if snap_zip.exists():
            snap_map = self.extract_media_from_zip(snap_zip, 'snap')
            # Extract files to screenshots directory
            self._extract_media_files(snap_zip, snap_map, self.screenshots_dir)

        # Process flyers.zip
        flyers_zip = self.extras_dir / "flyers.zip"
        if flyers_zip.exists():
            flyer_map = self.extract_media_from_zip(flyers_zip, 'flyers')
            self._extract_media_files(flyers_zip, flyer_map, self.covers_dir)

        # Process artwork.zip for marquees
        artwork_zip = self.extras_dir / "artwork.zip"
        if artwork_zip.exists():
            artwork_map = self.extract_media_from_zip(artwork_zip, 'artwork')
            # Extract marquee files
            self._extract_artwork_media(artwork_zip, artwork_map, marquee_map)

        return snap_map, flyer_map, marquee_map

    def _extract_media_files(self, zip_path: Path, media_map: Dict[str, str], dest_dir: Path):
        """Extract media files from zip to destination directory"""
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for rom_name, filename in media_map.items():
                    if self.dry_run:
                        self.log(f"Would extract {filename} to {dest_dir}/{rom_name}.png")
                        continue

                    # Extract the file
                    zf.extract(filename, self.extract_temp)
                    temp_file = self.extract_temp / filename

                    # Copy to destination with rom_name as filename
                    dest_file = dest_dir / f"{rom_name}.png"
                    if temp_file.exists():
                        shutil.copy2(temp_file, dest_file)
                        self.log(f"Extracted {filename} to {dest_file}")
                        # Clean up temp file
                        temp_file.unlink()
        except Exception as e:
            self.log(f"Failed to extract media from {zip_path}: {e}", "ERROR")

    def _extract_artwork_media(self, zip_path: Path, artwork_map: Dict[str, str], marquee_map: Dict[str, str]):
        """Extract marquee files from artwork.zip"""
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for rom_name, filename in artwork_map.items():
                    if '_marquee' in rom_name:
                        base_rom_name = rom_name.replace('_marquee', '')
                        if self.dry_run:
                            self.log(f"Would extract {filename} to {self.marquees_dir}/{base_rom_name}.png")
                            continue

                        zf.extract(filename, self.extract_temp)
                        temp_file = self.extract_temp / filename

                        dest_file = self.marquees_dir / f"{base_rom_name}.png"
                        if temp_file.exists():
                            shutil.copy2(temp_file, dest_file)
                            self.log(f"Extracted marquee {filename} to {dest_file}")
                            temp_file.unlink()
                            marquee_map[base_rom_name] = filename
        except Exception as e:
            self.log(f"Failed to extract artwork media: {e}", "ERROR")

    def load_existing_gamelist(self) -> Dict[str, ET.Element]:
        """Load existing gamelist.xml and return dict of rom_name -> game element"""
        existing_games = {}
        gamelist_path = self.roms_dir / "gamelist.xml"

        if not gamelist_path.exists() or self.no_merge:
            return existing_games

        try:
            tree = ET.parse(gamelist_path)
            root = tree.getroot()

            for game_elem in root.findall('game'):
                path_elem = game_elem.find('path')
                if path_elem is not None and path_elem.text:
                    # Extract rom name from path (./romname.zip)
                    path_text = path_elem.text
                    rom_name = Path(path_text).stem
                    existing_games[rom_name] = game_elem

            self.log(f"Loaded {len(existing_games)} existing games from gamelist.xml")
        except Exception as e:
            self.log(f"Failed to load existing gamelist.xml: {e}", "WARNING")

        return existing_games

    def create_gamelist_entry(self, rom_name: str, mame_data: Dict, 
                            snap_map: Dict[str, str], flyer_map: Dict[str, str],
                            marquee_map: Dict[str, str], existing_game: Optional[ET.Element] = None) -> ET.Element:
        """Create a gamelist.xml entry for a game"""
        game_elem = ET.Element('game')

        # Path (always use existing if available)
        path_elem = ET.SubElement(game_elem, 'path')
        if existing_game is not None and existing_game.find('path') is not None:
            path_elem.text = existing_game.find('path').text
        else:
            path_elem.text = f"./{rom_name}.zip"

        # Name/Description - prefer existing, fallback to MAME
        name_elem = ET.SubElement(game_elem, 'name')
        if existing_game is not None and existing_game.find('name') is not None:
            name_elem.text = existing_game.find('name').text
        else:
            name_elem.text = mame_data.get('description', rom_name)

        # Description - prefer existing, fallback to MAME description
        desc_elem = ET.SubElement(game_elem, 'desc')
        if existing_game is not None and existing_game.find('desc') is not None:
            desc_elem.text = existing_game.find('desc').text
        else:
            desc_elem.text = mame_data.get('description', '')

        # Image (screenshot)
        image_elem = ET.SubElement(game_elem, 'image')
        if existing_game is not None and existing_game.find('image') is not None:
            image_elem.text = existing_game.find('image').text
        elif rom_name in snap_map:
            image_elem.text = f"./media/screenshots/{rom_name}.png"

        # Thumbnail (same as image for MAME)
        thumb_elem = ET.SubElement(game_elem, 'thumbnail')
        if existing_game is not None and existing_game.find('thumbnail') is not None:
            thumb_elem.text = existing_game.find('thumbnail').text
        elif rom_name in snap_map:
            thumb_elem.text = f"./media/screenshots/{rom_name}.png"

        # Marquee
        marquee_elem = ET.SubElement(game_elem, 'marquee')
        if existing_game is not None and existing_game.find('marquee') is not None:
            marquee_elem.text = existing_game.find('marquee').text
        elif rom_name in marquee_map:
            marquee_elem.text = f"./media/marquees/{rom_name}.png"

        # Video (placeholder)
        video_elem = ET.SubElement(game_elem, 'video')
        if existing_game is not None and existing_game.find('video') is not None:
            video_elem.text = existing_game.find('video').text

        # Rating - keep existing if available
        rating_elem = ET.SubElement(game_elem, 'rating')
        if existing_game is not None and existing_game.find('rating') is not None:
            rating_elem.text = existing_game.find('rating').text

        # Releasedate
        releasedate_elem = ET.SubElement(game_elem, 'releasedate')
        if existing_game is not None and existing_game.find('releasedate') is not None:
            releasedate_elem.text = existing_game.find('releasedate').text
        elif mame_data.get('year'):
            # Convert year to ISO 8601 format
            year = mame_data['year']
            if year.isdigit() and len(year) == 4:
                releasedate_elem.text = f"{year}0101T000000"
            else:
                # Handle "200?" or other non-standard years
                match = re.match(r'(\d{4})', year)
                if match:
                    releasedate_elem.text = f"{match.group(1)}0101T000000"

        # Developer - prefer existing, fallback to manufacturer
        developer_elem = ET.SubElement(game_elem, 'developer')
        if existing_game is not None and existing_game.find('developer') is not None:
            developer_elem.text = existing_game.find('developer').text
        else:
            developer_elem.text = mame_data.get('manufacturer', '')

        # Publisher - same as developer for arcade games
        publisher_elem = ET.SubElement(game_elem, 'publisher')
        if existing_game is not None and existing_game.find('publisher') is not None:
            publisher_elem.text = existing_game.find('publisher').text
        else:
            publisher_elem.text = mame_data.get('manufacturer', '')

        # Genre - prefer existing, fallback to "Arcade"
        genre_elem = ET.SubElement(game_elem, 'genre')
        if existing_game is not None and existing_game.find('genre') is not None:
            genre_elem.text = existing_game.find('genre').text
        else:
            genre_elem.text = 'Arcade'

        # Players
        players_elem = ET.SubElement(game_elem, 'players')
        if existing_game is not None and existing_game.find('players') is not None:
            players_elem.text = existing_game.find('players').text
        elif 'players' in mame_data:
            players_elem.text = mame_data['players']

        # Hidden flag for non-working games
        if mame_data.get('driver_status') in ['preliminary', 'imperfect']:
            hidden_elem = ET.SubElement(game_elem, 'hidden')
            hidden_elem.text = 'true'

        return game_elem

    def merge_metadata(self, rom_games: Dict, chd_games: Dict, artwork_games: Dict) -> Dict:
        """Merge metadata from ROM, CHD, and artwork DATs"""
        merged = {}

        # Start with ROM games (most complete)
        for rom_name, data in rom_games.items():
            merged[rom_name] = data.copy()

        # Add CHD games not in ROMs
        for rom_name, data in chd_games.items():
            if rom_name not in merged:
                merged[rom_name] = data.copy()
            else:
                # Merge CHD data into existing ROM data (CHD data is usually less complete)
                merged[rom_name].update({k: v for k, v in data.items() if v})

        # Add artwork metadata
        for rom_name, data in artwork_games.items():
            if rom_name not in merged:
                merged[rom_name] = data.copy()
            else:
                # Artwork data is minimal, only add missing fields
                merged[rom_name].update({k: v for k, v in data.items() if v and k not in merged[rom_name]})

        return merged

    def generate_gamelist(self, merged_games: Dict, snap_map: Dict, flyer_map: Dict, marquee_map: Dict):
        """Generate the final gamelist.xml"""
        # Load existing gamelist for merging
        existing_games = self.load_existing_gamelist()

        # Create new gamelist root
        gamelist_root = ET.Element('gameList')

        # Process all games
        for rom_name in sorted(merged_games.keys()):
            game_data = merged_games[rom_name]
            existing_game = existing_games.get(rom_name)

            # Create game entry
            game_elem = self.create_gamelist_entry(
                rom_name, game_data, snap_map, flyer_map, marquee_map, existing_game
            )
            gamelist_root.append(game_elem)
            self.processed_games.add(rom_name)

        # Add any existing games that weren't in MAME DAT (preserve extras)
        if not self.no_merge:
            for rom_name, existing_game in existing_games.items():
                if rom_name not in self.processed_games:
                    gamelist_root.append(existing_game)
                    self.log(f"Preserved existing game not in MAME DAT: {rom_name}")

        # Write gamelist.xml
        gamelist_path = self.roms_dir / "gamelist.xml"
        if self.dry_run:
            self.log(f"Would write gamelist.xml to {gamelist_path}")
            self.log(f"Total games: {len(gamelist_root.findall('game'))}")
            return

        # Pretty print XML
        xml_str = ET.tostring(gamelist_root, encoding='unicode')
        # Add indentation
        xml_str = self._prettify_xml(gamelist_root)

        with open(gamelist_path, 'w', encoding='utf-8') as f:
            f.write(xml_str)

        self.log(f"Successfully wrote gamelist.xml with {len(gamelist_root.findall('game'))} games")

    def _prettify_xml(self, elem: ET.Element, level: int = 0) -> str:
        """Pretty print XML with proper indentation"""
        indent = "  "
        i = "\n" + level * indent

        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + indent
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
            for subelem in elem:
                self._prettify_xml(subelem, level + 1)
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i

        if level == 0:
            # Add XML declaration
            return f'<?xml version="1.0"?>\n{ET.tostring(elem, encoding="unicode")}'
        return ''

    def cleanup(self):
        """Clean up temporary extraction directory"""
        if self.extract_temp.exists() and not self.dry_run:
            shutil.rmtree(self.extract_temp)
            self.log(f"Cleaned up temp directory: {self.extract_temp}")

    def run(self):
        """Main execution method"""
        try:
            self.log("Starting MAME to Batocera conversion...")

            # Step 1: Extract and parse DAT files
            self.log("Extracting and parsing DAT files...")

            # Find DAT zip files
            dat_zips = list(self.dat_zip_path.parent.glob("*.zip")) if self.dat_zip_path.is_file() else []
            if not dat_zips and self.dat_zip_path.is_dir():
                dat_zips = list(self.dat_zip_path.glob("*.zip"))

            rom_dat_path = None
            chd_dat_path = None
            artwork_dat_path = None

            for zip_file in dat_zips:
                if 'rom' in zip_file.name.lower():
                    rom_dat_path = self.extract_xml_from_zip(zip_file)
                elif 'chd' in zip_file.name.lower():
                    chd_dat_path = self.extract_xml_from_zip(zip_file)
                elif 'artwork' in zip_file.name.lower():
                    artwork_dat_path = self.extract_xml_from_zip(zip_file)

            if not rom_dat_path:
                self.log("Could not find ROM DAT file", "ERROR")
                return

            # Parse DAT files
            rom_games = self.parse_dat_xml(rom_dat_path) if rom_dat_path else {}
            chd_games = self.parse_dat_xml(chd_dat_path) if chd_dat_path else {}
            artwork_games = self.parse_dat_xml(artwork_dat_path) if artwork_dat_path else {}

            self.log(f"Parsed {len(rom_games)} ROM games, {len(chd_games)} CHD games, {len(artwork_games)} artwork entries")

            # Step 2: Merge metadata
            merged_games = self.merge_metadata(rom_games, chd_games, artwork_games)
            self.log(f"Total merged games: {len(merged_games)}")

            # Step 3: Extract and map media files
            self.log("Extracting media files...")
            snap_map, flyer_map, marquee_map = self.get_media_from_extras()

            # Step 4: Generate gamelist.xml
            self.log("Generating gamelist.xml...")
            self.generate_gamelist(merged_games, snap_map, flyer_map, marquee_map)

            self.log("Conversion completed successfully!")

        except Exception as e:
            self.log(f"Fatal error: {e}", "ERROR")
            sys.exit(1)
        finally:
            self.cleanup()


def main():
    parser = argparse.ArgumentParser(description="Convert MAME DAT files to Batocera gamelist.xml")
    parser.add_argument('--dat-zip', required=True, help='Path to MAME DAT zip file or directory containing DAT zips')
    parser.add_argument('--extras-dir', required=True, help='Path to MAME EXTRAs directory')
    parser.add_argument('--roms-dir', required=True, help='Path to Batocera ROMs directory')
    parser.add_argument('--extract-temp', help='Temp directory for extraction (optional)')
    parser.add_argument('--no-merge', action='store_true', help='Do not merge with existing gamelist.xml')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')

    args = parser.parse_args()

    converter = MameToBatocera(
        dat_zip_path=args.dat_zip,
        extras_dir=args.extras_dir,
        roms_dir=args.roms_dir,
        extract_temp=args.extract_temp,
        no_merge=args.no_merge,
        dry_run=args.dry_run,
        verbose=args.verbose
    )

    converter.run()


if __name__ == '__main__':
    main()
