R19 EDITABLE SCIENTIFIC FIGURES
Definition sensitivity and decision equivalence in science and technology indicators

CONTENTS AND USE

This component contains the five figures as editable LibreOffice Draw documents,
editable SVG and flat OpenDocument sources, vector PDF and EPS exports, PNG images
and RGB TIFF files. The 35 primary artwork files and all seven public input files
are byte-identical to the R18 component. R19 removes the final full stop from each
of the five caption strings and updates the package documentation and audit.
Internal caption punctuation and all alternative text are preserved.
Historical audit wrappers and disposable edit probes are
retained in the separate R17 package, not repeated in this component.

ODG_NATIVE/Fig1.odg ... Fig5.odg          Editable master drawings
NATIVE_SOURCE/Fig1.fodg ... Fig5.fodg    Flat OpenDocument generation sources
SVG_EDITABLE/Fig1.svg ... Fig5.svg      Editable text and vector primitives
PDF_VECTOR/Fig1.pdf ... Fig5.pdf        Font-embedded vector previews
EPS_VECTOR/Fig1.eps ... Fig5.eps        Vector exports
PNG_600/Fig1.png ... Fig5.png           Manuscript insertion images at 600 dpi
TIFF/Fig1.tif ... Fig5.tif              RGB raster exports
SOURCE_DATA/                           Preserved public CSV and JSON inputs
CONTROL/                               Caption registry, object/value dictionaries
                                       and structural verification records
code/                                  Generation and verification programs

Figure 1 has a 1200 dpi TIFF; Figures 2-5 have 600 dpi TIFFs. All figures are
119 mm wide, with heights of 111, 145, 191, 110 and 143 mm. The font is Liberation
Sans; text sizes range from 8 to 9 pt. The width is a retained design choice.
The ODG is an editable authoring format; portal acceptance of ODG is not assumed.

The caption and alternative-text registry is
CONTROL/FIGURE_CAPTIONS_AND_ALT_TEXT_EN_GB.json. Captions are separate from the
artwork. The manuscript provides the displayed Fig. number before each caption.
The registry includes both scientific source notes and descriptive alternative
text. Source numbers, plotting geometry, rounding and visual encodings are retained.

EDITING

Open an ODG in LibreOffice Draw and save an editing copy. Use F5 for Navigator,
F2 to edit a selected text frame and F4 for position and size. Each primitive has
a stable name, listed in CONTROL/FigN_OBJECTS_AND_VALUES.json. A patterned bar is
a native group of its rectangle, hatch strokes and outline. Use Enter Group or
F3 to edit a component and Ctrl+F3 to leave the group. F8 exposes point editing
where the object type supports it. Install Liberation Sans before editing to
preserve the existing layout.

The drawings are not linked spreadsheet charts. A manual change to a bar does
not update the label or its source number. For a scientific revision, update the
authorised source data and generator together, then rerun the checks and inspect
the exports. A frozen source-identity guard must only be changed as part of a
documented scientific revision. For layout changes, preserve values and encodings.

CHECKING THE DELIVERED PACKAGE

From the extracted component directory, run:

    python verify_package.py

This standard-library program compares the complete file list, sizes and SHA-256
identities with MANIFEST_SHA256.json. Extra, missing or altered files cause failure.
It does not regenerate evidence or certify changed figures.

For structural and source-value checks, first copy the component to a working
directory, install the packages in requirements_figures.txt and run:

    python -m pip install -r requirements_figures.txt
    python code/verify_figures.py

The check reads the native objects, source values, SVG text and PDF fonts and
dimensions. It writes CONTROL/NATIVE_STRUCTURE_AND_VALUES.json. The delivered
record is retained byte for byte from R18 and reports that structural invocation;
it does not claim a fresh GUI
or native application roundtrip. The structure contains 935 native primitives,
162 real text frames and 34 bar groups. Forty numerical entries are traced to
the preserved inputs. The drawing content contains no raster or OLE objects.

OPTIONAL REBUILD AND NATIVE EDIT PROBES

Use a separate working copy because these commands replace exports or create
temporary test outputs. External programs required on PATH are soffice, pdftops,
inkscape and gs. The retained generator uses the original scene schema and source
identity guards. Report filenames were updated for the current component.

    python code/build_figures.py
    python code/verify_figures.py --edit-probes
    python code/verify_exports.py

The first command rebuilds the five figures. The second edits disposable copies
and performs actual LibreOffice reopen/save/export operations. The third renders
SVG and EPS through independent programs and checks raster metadata. None of
these commands performs a scientific simulation or downloads research data.
Package installation may contact the configured package index. A new visual
review is required after changes; a previous visual review does not certify a
new export. Newly generated files will not match the original delivery manifest.

SCIENTIFIC PROVENANCE AND VERIFICATION LIMITS

Figures 1-4 retain the public figure material recovered from the R11 supplement;
the six CSV inputs retain their recorded R9 identities. Figure 1 uses the approved
general terminology and the separate declared-objective/common-rule branch.
Figure 5 uses nine exact rational entries from the R14.1 OA reporting JSON.
Its semantic and action panels measure different objects. The source history is
recorded in CONTROL/SOURCE_PROVENANCE.json.

The previous native edit/save/export and cross-renderer visual evidence remains
in R17. The R18 structural record is retained without modification. R19 compares
the complete file identities with R18 and verifies the five caption edits and
closed package manifest. It does not add a new Monte Carlo run, private FAT input
or native Windows
acceptance test. No project-wide licence has been assigned by this component;
third-party conditions remain applicable to their respective material.

REFERENCE GUIDANCE

The Document Foundation. Shortcut keys for drawings.
https://help.libreoffice.org/latest/en-GB/text/sdraw/04/01020000.html

The Document Foundation. Working with groups.
https://help.libreoffice.org/latest/en-GB/text/shared/guide/groups.html?DbPAR=SHARED

Scientometrics. Submission guidelines.
https://link.springer.com/journal/11192/submission-guidelines
