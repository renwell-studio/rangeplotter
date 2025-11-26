# RangePlotter Examples

This directory contains example input files for RangePlotter.

## CSV Format (`radars.csv`)
You can define radar sites using a simple CSV file.
Required columns: `name`, `lat`, `lon`.
Optional columns: `height_m` (radar height AGL), `radius_km` (max analysis radius).

```csv
name,lat,lon,height_m,radius_km
"Site Alpha",51.5074,-0.1278,15,50
"Site Beta",48.8566,2.3522,20,
```

## KML Format (`radars.kml`)
You can also use Google Earth KML files containing Placemarks.
The altitude of the Point is treated as the radar height (AGL).

## Usage
You can pass these files directly to the `viewshed` or `network run` commands:

```bash
# Run viewshed analysis on CSV
rangeplotter viewshed --input examples/radars.csv

# Run full network analysis on KML
rangeplotter network run --input examples/radars.kml --output output/example_network
```
