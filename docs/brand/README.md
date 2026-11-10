# Brand assets

`connectly-logo-horizontal.pdf` is the official Connectly logo, as supplied by Connectly
Technologies. It is the source for everything else here.

| File | Made from the PDF by | Used for |
| --- | --- | --- |
| `frontend/public/brand/connectly-logo-horizontal.svg` | `pdftocairo -svg`, white page background removed, view box cropped to the artwork. Paths and colours unchanged. | Navigation, sign-in page, reports |
| `frontend/public/brand/connectly-mark.svg` | Same file with the view box cropped to the symbol (the two rings). | Browser tab icon (`frontend/src/app/icon.svg`), loading screens, footer |

Rules followed in the application:

- The logo is never recoloured, stretched, outlined or redrawn, and is always shown at its
  own aspect ratio on a light background. There is no dark theme for this reason.
- The product name "Intelligence" is set as text beside the logo, separated by a gold rule;
  it is not merged into the artwork.
- Colours taken from the logo: maroon `#6B1420`, gold `#D9A441`. Gold is not used for text
  on white because its contrast is too low (2.2:1); a darker gold `#7F5A12` is used instead.
- Typefaces: Poppins (display, closest match to the logo lettering) and Inter (text). Both
  are SIL Open Font License fonts installed from npm (`@fontsource`) and served by the app
  itself, so no external font service is called.

Using the symbol on its own (favicon, loading screen) is a crop of the official artwork, not a
modification. If Connectly prefers a different icon, replace `connectly-mark.svg` and
`frontend/src/app/icon.svg`.
