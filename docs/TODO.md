
# Completed TODOs
- [x] include logging so we know why it crashed - with a CLI flag to turn on/off, and a config file line
- [x] centralise all user settings in a single, documented config file.
- [x] have an overall -h flag to list the utilities I can call with an explanation of each
- [x] update to viewshed terminology throughout
- [x] revise the input and config flags to be more sensible
- [x] remove the deprecated warning
- [x] output verbosity
- [x] improve meaningfulness of progress statements to command line
 - [x] remove repeated 'Computing viewshed' lines from output
 - [x] improve smoothness of LOS progress bar
- [x] add altitude info to the output polys
- [x] include a way to specify max range of interest (i.e. a shortcut for implying long range and short range radar capabilities without going through actual radar visibility calcs)
- [x] tell me how long the total download time and computation time was
- [x] fix output file naming to be meaningful
- [x] get output file structure working inside the kml file so I can import the out structure
- [x] make output kml inherit polygon style from input
- [x] make detection-range function save output correctly
- [x] fix double nested folders in imported kml
- [x] fix output file/folder naming:
 - top level - site(s) name - same name as input kml
 - next level - individual sites and union folder (this level only exists if necessary)
 - next level - max sensor ranges
 - next level - target altitudes
- [x] review CPU usage - see if we can get the machine working harder.

# Minor New Features
- [ ] new feature - unions
 - [ ] refine working file locations. Remove input/ and output/. Replace with working_files/ with input/ viewshed/ and detection_range/ as children
 - [ ] change default styling of output kmls to follow config
 - [ ] add detection range array to config for default behaviour
 - [ ] allow use of /* to specify multiple input files
 - [ ] outputs should not include placemarks - we already have this information in the original input file
- [ ] find a way to capture and save viewshed execution progress if we have to pause halfway through
- [x] redo output structure to generate a set of independent raw viewshed kml files I can reuse later (these are the expensive part), then use 'detection-range' to build custom multi-part kmls and unions
- [ ] new feature - change target altitudes to agl throughout (a user option to swithc between msl and agl)
- [x] get multiple site inputworking
- [ ] get basic horizon rings output file naming and structure the same as 'viewshed' output
- [x] create basic utilities for poly management (e.g. doing unions, colour /shading changes etc.) without recalculating everything - call other functions, ideally
- [ ] have a way to do just one/some sites from an input list of many - is this necessary?
- [ ] have a download only flag for viewshed to just get the files. Also a soft check function - see how much data will be required to download?

# Minor refinements:
- [ ] general review for deprecated/redundant code and commands
- [ ] make -h work as well as --help
- [ ] have a line confirming that all required DEM tiles are available
- [ ] CLI flag to specify which viewshed ranges to do (optional, to override config file)
- [ ] revise explanatory text in viewshed --help to remove 'radar' terminology and specify that this produces a raw, geometric viewshed only
- [ ] tidy up whether defaults such as output file locations are hardcoded or stored in config.yaml. We want all defaults to be kept (and editable in config.yaml), with this default referenced in --help, etc, but overridable by command line flags
 - [ ] adjust commands so input flag assumes path is input/


# Documentation:
- [ ] user documentation to explain the primary workflow and behaviour: viewshed -> detection-range

# Major New Features:
- [ ] add functionality for true radar visibility (taking radar cross section, frequency, etc as inputs).
 - [x] or a simpler version that applies a max detection range for an array of target types, and superposes that onto a pre-calculated viewshed, to output a set of viewsheds for different target types, all at a given target altitude, and having only calculated that viewshed once.
 - [ ] does radar diffraction work horizontally as well? i.e. where a small, tall island causes a long thin 'shadow' behind, will the radar bem (and return) refract to allow observation behind it?
- [ ] add functionality to create and visualise a 3d observed volume? Can google earth do this?
 - [ ] probably not directly, but could stack surfaces of difference colour/opacity to represent detections at different altitudes, etc.
 - [ ] ChatGPT says I can: create radar coverage “bubbles” modeled as a set of semi-transparent 3D meshes (.dae models)
- [ ] think about a way to represent detection probability (isosurfaces)?

# For packaging:
- [x] use git properly
- [ ] make sure it behaves well on any CPU
- [ ] add GPU processing?
- [ ] package utility for download/installation as a snap(?)
- [ ] ensure sensible --help, README and man files
- [ ] set up sensible and secure credential handling
- [ ] understand the technology/utility stack we are using. GDAL?
- [ ] include options to import/export other useful file types