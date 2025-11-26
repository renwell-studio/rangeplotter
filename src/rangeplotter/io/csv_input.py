import csv
from pathlib import Path
from typing import List
from rangeplotter.models.radar_site import RadarSite

def parse_csv_radars(csv_path: Path, default_sensor_height_m: float) -> List[RadarSite]:
    """
    Parse a CSV file containing radar site definitions.
    Expected columns: Name, Latitude, Longitude, [Height_AGL]
    Headers are case-insensitive.
    """
    radars = []
    if not csv_path.exists():
        return []

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []
            
        # Create a map of normalized headers to actual headers
        header_map = {h.strip().lower(): h for h in reader.fieldnames}
        
        # Check required columns
        required = ['name', 'latitude', 'longitude']
        if not all(r in header_map for r in required):
            # Try looking for 'lat' and 'lon' aliases
            if 'lat' in header_map: header_map['latitude'] = header_map['lat']
            if 'lon' in header_map: header_map['longitude'] = header_map['lon']
            
            if not all(r in header_map for r in required):
                print(f"Warning: CSV {csv_path.name} missing required columns (Name, Latitude, Longitude)")
                return []

        for row in reader:
            try:
                name = row[header_map['name']].strip()
                lat = float(row[header_map['latitude']])
                lon = float(row[header_map['longitude']])
                
                # Optional height
                height_agl = default_sensor_height_m
                if 'height_agl' in header_map and row[header_map['height_agl']]:
                    try:
                        val = float(row[header_map['height_agl']])
                        height_agl = val
                    except ValueError:
                        pass # Use default
                
                # Create site
                # We use clampToGround with the specified sensor height
                site = RadarSite(
                    name=name,
                    latitude=lat,
                    longitude=lon,
                    altitude_mode="clampToGround",
                    input_altitude=0.0,
                    sensor_height_m_agl=height_agl
                )
                radars.append(site)
                
            except (ValueError, KeyError) as e:
                print(f"Skipping invalid row in {csv_path.name}: {e}")
                continue
                
    return radars
