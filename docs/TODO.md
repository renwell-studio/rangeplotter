
# Functionality
- [x] include logging so we know why it crashed - with a CLI flag to turn on/off, and a config file line
- [x] centralise all user settings in a single, documented config file.
- [x] have an overall -h flag to list the utilities I can call with an explanation of each
- [x] update to viewshed terminology throughout
- [x] revise the input and config flags to be more sensible
- [x] remove the deprecated warning
- [ ] include basic utilities for poly management (e.g. doing unions, colour /shading changes etc.) without recalculating everything - call other functions, ideally
- [ ] have a way to do just one/some sites from an input list of many
- [ ] specify which LOS ranges to do
- [x] output verbosity
- [x] improve meaningfulness of progress statements to command line
 - [ ] have a line confirming that all required DEM tiles are available
 - [x] remove repeated 'Computing viewshed' lines from output
 - [x] improve smoothness of LOS progress bar
- [x] add altitude info to the output polys
- [ ] include a way to specify max range of interest (i.e. a shortcut for implying long range and short range radar capabilities without going through actual radar visibility calcs)
- [x] tell me how long the total download time and computation time was
- [x] fix output file naming to be meaningful
- [ ] get multiple site input and polygon unions working
- [x] get output file structure working inside the kml file so I can import the out structure
- [ ] get basic horizon rings output file naming and structure the same as 'viewshed' output


# Extended feature set:
- [ ] add functionality for true radar visibility (taking radar cross section, frequency, etc as inputs).
 - [ ] or a simpler version that applies a max detection range for an array of target types, and superposes that onto a pre-calculated viewshed, to output a set of viewsheds for different target types, all at a given target altitude, and having only calculated that viewshed once.
 - [ ] does radar diffraction work horizontally as well? i.e. where a small, tall island causes a long thin 'shadow' behind, will the radar bem (and return) refract to allow observation behind it?
- [ ] add functionality to create and visualise a 3d observed volume? Can google earth do this?
 - [ ] probably not directly, but could stack surfaces of difference colour/opacity to represent detections at different altitudes, etc.
 - [ ] ChatGPT says I can: create radar coverage “bubbles” modeled as a set of semi-transparent 3D meshes (.dae models)
- [ ] think about a way to represent detection probability (isosurfaces)?

# For packaging:
- [ ] use git properly
- [ ] make sure it behaves well on any CPU
- [ ] add GPU processing?
- [ ] package utility for download/installation as a snap(?)
- [ ] ensure sensible --help, README and man files
- [ ] set up sensible and secure credential handling
- [ ] understand the technology/utility stack we are using. GDAL?
- [ ] include options to import/export other useful file types