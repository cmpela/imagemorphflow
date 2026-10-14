from base64 import b64encode
from html import escape
from io import BytesIO
from string import Template

from rdkit import Chem
from rdkit.Chem import Draw, rdCoordGen


class PreTemplate(Template):
    """Substitute § placeholders while preserving $ placeholders."""

    delimiter = "§"




def mol_img_tag(mol, size=300):
    """Return an HTML tag containing a base64-encoded molecule image."""
    unavailable_html = (
        '<span class="mol-unavailable">'
        "Structure unavailable"
        "</span>"
    )

    if mol is None:
        return unavailable_html

    try:
        if isinstance(mol, str):
            smiles = mol.strip()

            if not smiles or smiles.casefold() in {
                "nan",
                "none",
                "na",
                "n/a",
                "<na>",
            }:
                return unavailable_html

            rdkit_mol = Chem.MolFromSmiles(smiles)
        else:
            # Copy the molecule to avoid modifying the original object.
            rdkit_mol = Chem.Mol(mol)

        if rdkit_mol is None:
            return unavailable_html

        # Reassign stereochemical information before generating coordinates.
        Chem.AssignStereochemistry(
            rdkit_mol,
            cleanIt=True,
            force=True,
        )

        # Generate cleaner 2D coordinates for complex ring systems.
        rdkit_mol.RemoveAllConformers()
        rdCoordGen.AddCoords(rdkit_mol)

        draw_options = Draw.MolDrawOptions()
        draw_options.padding = 0.08

        image = Draw.MolToImage(
            rdkit_mol,
            size=(size, size),
            options=draw_options,
        )

        image_buffer = BytesIO()
        image.save(image_buffer, format="PNG")

        encoded_image = b64encode(
            image_buffer.getvalue()
        ).decode("ascii")

        return (
            '<img class="molecule-image" '
            f'src="data:image/png;base64,{encoded_image}" '
            f'width="{size}" height="{size}" '
            'alt="Molecule structure">'
        )

    except Exception:
        return unavailable_html

def detail_row(label, value):
    """Return a detail-table row, displaying a dash for missing values."""
    if value is None:
        value_text = "—"
    else:
        value_text = str(value).strip()

        if not value_text or value_text.casefold() in {
            "nan",
            "none",
            "na",
            "n/a",
            "<na>",
        }:
            value_text = "—"

    return (
        "<tr>"
        f'<td class="detail-label">{escape(str(label))}</td>'
        f'<td class="detail-value">{escape(value_text)}</td>'
        "</tr>"
    )

def optional_detail_row(label, value):
    """Return a detail-table row, or an empty string for missing values."""
    if value is None:
        return ""

    value_text = str(value).strip()
    if not value_text or value_text.casefold() in {
        "nan",
        "none",
        "na",
        "n/a",
        "<na>",
    }:
        return ""

    return (
        '<tr><td class="noborder">'
        f"{escape(str(label))}:</td>"
        f'<td class="noborder">{escape(value_text)}</td></tr>'
    )

LOGO = ""

CSS = """
<style>
:root {
    --background: #f4f7fb;
    --surface: #ffffff;
    --surface-muted: #f8fafc;
    --primary: #2563eb;
    --primary-dark: #1e3a8a;
    --primary-soft: #eaf2ff;
    --text: #172033;
    --text-muted: #64748b;
    --border: #dfe7f1;
    --shadow: 0 12px 30px rgba(30, 64, 175, 0.08);
    --radius: 16px;
}

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background: var(--background);
    color: var(--text);
    font-family:
        Inter,
        ui-sans-serif,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        Arial,
        sans-serif;
    font-size: 14px;
    line-height: 1.55;
}

.report-shell {
    width: min(1480px, calc(100% - 48px));
    margin: 0 auto;
    padding: 36px 0 64px;
}

.report-hero {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 24px;
    margin-bottom: 24px;
    padding: 28px 32px;
    color: #ffffff;
    background:
        linear-gradient(135deg, #172554 0%, #1d4ed8 65%, #0ea5e9 100%);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
}

.report-hero h1 {
    margin: 4px 0;
    font-size: 32px;
    line-height: 1.15;
    letter-spacing: -0.03em;
}

.report-eyebrow {
    margin: 0;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    opacity: 0.78;
}

.report-subtitle,
.report-date {
    margin: 4px 0 0;
    opacity: 0.9;
}

.overview-grid {
    display: grid;
    grid-template-columns: minmax(280px, 360px) minmax(500px, 1fr);
    gap: 24px;
    margin-bottom: 24px;
}

.card {
    margin-bottom: 24px;
    padding: 26px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
}

.overview-grid .card {
    margin-bottom: 0;
}

.card h2,
.card h3 {
    margin: 0 0 16px;
    color: var(--primary-dark);
    letter-spacing: -0.015em;
}

.card h2 {
    font-size: 21px;
}

.card h3 {
    font-size: 19px;
}

.section-description {
    margin: -8px 0 18px;
    color: var(--text-muted);
}

.structure-card {
    display: flex;
    flex-direction: column;
}

.structure-container {
    display: flex;
    flex: 1;
    min-height: 300px;
    align-items: center;
    justify-content: center;
    padding: 16px;
    background: var(--surface-muted);
    border: 1px solid var(--border);
    border-radius: 12px;
}

img.molecule-image {
    display: block;
    max-width: 100%;
    height: auto;
    object-fit: contain;
    mix-blend-mode: multiply;
}

.mol-unavailable {
    color: var(--text-muted);
    font-style: italic;
}

.details-table {
    width: 100%;
    border-collapse: collapse;
}

.details-table tr:not(:last-child) {
    border-bottom: 1px solid var(--border);
}

.details-table td {
    padding: 10px 8px;
    border: 0;
    vertical-align: top;
}

.detail-label,
.details-table td:first-child {
    width: 230px;
    color: var(--text-muted);
    font-weight: 600;
    text-align: left;
}

.detail-value,
.details-table td:last-child {
    color: var(--text);
    text-align: left;
}

.table-scroll {
    width: 100%;
    overflow-x: auto;
    border: 1px solid var(--border);
    border-radius: 12px;
}

.data-table,
.table-scroll > table {
    width: 100%;
    min-width: 900px;
    border-collapse: collapse;
    background: var(--surface);
}

.data-table th,
.table-scroll > table th {
    padding: 12px 10px;
    color: var(--primary-dark);
    background: var(--primary-soft);
    border: 0;
    border-bottom: 1px solid #bfd5fa;
    font-size: 12px;
    font-weight: 700;
    text-align: center;
    white-space: nowrap;
}

.data-table td,
.table-scroll > table td {
    padding: 11px 10px;
    border: 0;
    border-bottom: 1px solid var(--border);
    text-align: center;
    vertical-align: middle;
}

.data-table tbody tr:last-child td,
.table-scroll > table tbody tr:last-child td {
    border-bottom: 0;
}

.data-table tbody tr:hover,
.table-scroll > table tbody tr:hover {
    background: #f8fbff;
}

th.left,
td.left {
    text-align: left;
}

.table-scroll img.molecule-image {
    width: 110px;
    height: 110px;
    margin: 0 auto;
}

.heatmap-container {
    overflow-x: auto;
    text-align: center;
}

.heatmap-container img {
    max-width: 100%;
    height: auto;
    border-radius: 10px;
}

.report-footer {
    margin-top: 28px;
    color: var(--text-muted);
    font-size: 12px;
    text-align: right;
}

.similar-table {
    width: 100%;
    min-width: 1050px;
    table-layout: fixed;
}

/* Molecular structure */
.similar-table th:nth-child(1),
.similar-table td:nth-child(1) {
    width: 150px;
}

.similar-table .molecule-image {
    display: block;
    width: 130px;
    min-width: 130px;
    max-width: none;
    height: 130px;
    margin: 0 auto;
    object-fit: contain;
}

/* Well ID */
.similar-table th:nth-child(2),
.similar-table td:nth-child(2) {
    width: 230px;
}

/* Induction */
.similar-table th:nth-child(3),
.similar-table td:nth-child(3) {
    width: 120px;
}

/* Profile similarity */
.similar-table th:nth-child(4),
.similar-table td:nth-child(4) {
    width: 150px;
}

/* Trivial name */
.similar-table th:nth-child(5),
.similar-table td:nth-child(5) {
    width: 160px;
}

/* Known activity */
.similar-table th:nth-child(6),
.similar-table td:nth-child(6) {
    width: 360px;
}

.similar-table td.known-activity {
    color: var(--text-muted);
    font-size: 11px;
    line-height: 1.4;
}

.compound-report-link:hover {
    text-decoration: underline;
}

/* Representative images */
.representative-images-wrap {
    width: 100%;
    overflow-x: auto;
    margin-top: 18px;
    border: 1px solid var(--border);
    border-radius: 12px;
}

.representative-images {
    width: 100%;
    min-width: 1100px;
    table-layout: fixed;
    border-collapse: collapse;
    background: var(--surface);
}

.representative-images th,
.representative-images td {
    padding: 8px;
    border: 0;
    border-right: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
    text-align: center;
    vertical-align: middle;
}

.representative-images th:last-child,
.representative-images td:last-child {
    border-right: 0;
}

.representative-images tbody tr:last-child th,
.representative-images tbody tr:last-child td {
    border-bottom: 0;
}

.representative-images thead th {
    padding: 12px 8px;
    color: var(--primary-dark);
    background: var(--primary-soft);
    font-size: 12px;
    font-weight: 700;
    line-height: 1.35;
}

.representative-images thead th:first-child,
.representative-images tbody th {
    width: 100px;
}

.representative-images tbody th {
    color: var(--primary-dark);
    background: var(--surface-muted);
    font-size: 13px;
    font-weight: 700;
}

.representative-images img {
    display: block;
    width: 100%;
    height: auto;
    margin: 0 auto;
    object-fit: contain;
    border-radius: 6px;
}

.missing-image {
    display: flex;
    min-height: 160px;
    align-items: center;
    justify-content: center;
    padding: 12px;
    color: var(--text-muted);
    background: var(--surface-muted);
    border-radius: 6px;
    font-size: 12px;
}

@media (max-width: 900px) {
    .report-shell {
        width: min(100% - 24px, 1480px);
        padding-top: 16px;
    }

    .overview-grid {
        grid-template-columns: 1fr;
    }

    .report-hero {
        align-items: flex-start;
        flex-direction: column;
    }
}

@media print {
    body {
        background: #ffffff;
    }

    .report-shell {
        width: 100%;
        padding: 0;
    }

    .card,
    .report-hero {
        box-shadow: none;
        break-inside: avoid;
    }

    .table-scroll {
        overflow: visible;
    }
}
</style>
"""


HTML_INTRO = """
<!DOCTYPE html>
<html>
<head>
    <title>$title</title>
    <meta charset="UTF-8">
    §CSS
</head>
<body>
"""

HTML_INTRO = PreTemplate(HTML_INTRO).substitute({"CSS": CSS})


HTML_EXTRO = """
</body>
</html>
"""

TABLE_INTRO = """
<table class="details-table">
<tbody>
"""

TABLE_EXTRO = """
</tbody>
</table>
"""

PARM_TABLE_HEADER = """
<tr>
    <th>#</th>
    <th>Parameter</th>
    <th>Value</th>
</tr>
"""


SIMILAR_COMPOUNDS_TABLE_HEADER = """
<tr>
    <th>Mol</th>
    <th>Well ID</th>
    <th>Induction [%]</th>
    <th>Profile Similarity</th>
    <th>Trivial Name</th>
    <th class="left">Known Activity</th>
</tr>
"""


SIMILAR_COMPOUNDS_TABLE_ROW = """
<tr>
    <td>$mol_img</td>
    <td>
        <a 
            class="compound-report-link"
            href="$Report_Link" 
            target="_blank" 
            rel="noopener noreferrer"
        >
            $Well_Id
        </a>
    </td>
    <td>$Activity</td>
    <td>$Similarity</td>
    <td>$Trivial_Name</td>
    <td class="left known-activity">$Known_Act</td>
</tr>
"""


PARM_TABLE_ROW = """
<tr>
    <td>$idx</td>
    <td class="left">$Parameter</td>
    <td class="left">$Value</td>
</tr>"""


DETAILS_TEMPL = """
§LOGO

<main class="report-shell">
    <header class="report-hero">
        <div>
            <p class="report-eyebrow">Cell Painting Report</p>
            <h1>Compound Profile</h1>
            <p class="report-subtitle">
                Compound ID <strong>$Compound_Id</strong>
            </p>
        </div>
        <p class="report-date">Generated $Date</p>
    </header>

    <section class="overview-grid">
        <article class="card structure-card">
            <h2>Molecular Structure</h2>
            <div class="structure-container">
                $mol_img
            </div>
        </article>

        <article class="card">
            <h2>Compound Details</h2>

            <table class="details-table">
                <tbody>
                    <tr>
                        <td class="detail-label">Well ID</td>
                        <td class="detail-value">$Well_Id</td>
                    </tr>

                    $Condition_Row
                    $Manual_Cluster_Row
                    $Trivial_Name_Row
                    $Known_Act_Row
                    $Extra_Report_Rows

                    <tr>
                        <td class="detail-label">Producer</td>
                        <td class="detail-value">$Producer</td>
                    </tr>
                    <tr>
                        <td class="detail-label">Batch ID</td>
                        <td class="detail-value">$Batch_Id</td>
                    </tr>
                    <tr>
                        <td class="detail-label">Supplier ID</td>
                        <td class="detail-value">$Supplier_Id</td>
                    </tr>
                    <tr>
                        <td class="detail-label">Chiral</td>
                        <td class="detail-value">$Chiral</td>
                    </tr>
                    <tr>
                        <td class="detail-label">Purity Flag</td>
                        <td class="detail-value">$Pure_Flag</td>
                    </tr>
                    <tr>
                        <td class="detail-label">Concentration</td>
                        <td class="detail-value">${Conc_uM} &micro;M</td>
                    </tr>
                    <tr>
                        <td class="detail-label">Time Point</td>
                        <td class="detail-value">${TP}h</td>
                    </tr>
                    <tr>
                        <td class="detail-label">Induction</td>
                        <td class="detail-value">$Activity%</td>
                    </tr>
                    <tr>
                        <td class="detail-label">Cell Count</td>
                        <td class="detail-value">$Rel_Cell_Count% Ctrl</td>
                    </tr>

                    $Reference
                </tbody>
            </table>
        </article>
    </section>

    <section class="card">
        <h3>Most Similar Compounds</h3>
        <p class="section-description">
            Compounds with the most similar morphological profiles in the
            current dataset.
        </p>

        <div class="table-scroll">
            $Similar_Compounds_Table
        </div>
    </section>

    <section class="card">
        <h3>Feature Heatmaps</h3>
        <p class="section-description">
            Z-score feature values for $Well_Id and the top $Top_N most
            similar compounds.
        </p>

        <div class="heatmap-container">
            $Heatmap
        </div>
    </section>

    <section class="card">
        <h3>Images</h3>
        $Images_Description
        $Images
    </section>

    <section class="card">
        <h3>Feature Z-Scores</h3>
        <p class="section-description">
            Feature values normalized relative to the corresponding controls
            using the median and median absolute deviation (MAD).
        </p>

        <div class="table-scroll">
            <table class="data-table">
                <tbody>
                    §PARM_TABLE_HEADER
                    $Parm_Table
                </tbody>
            </table>
        </div>
    </section>

    <footer class="report-footer">
        Cell Painting compound report · $Date
    </footer>
</main>
"""

IMAGES_TABLE = """
<div class="representative-images-wrap">
<table class="representative-images">
    <thead>
        <tr>
            <th></th>
            <th>Nuclei</th>
            <th>Endoplasmic<br>Reticulum</th>
            <th>Cytoplasmic RNA<br>/ Nucleoli</th>
            <th>Golgi / Cell Membrane<br>/ Cytoskeleton</th>
            <th>Mitochondria</th>         
        </tr>
    </thead>
    <tbody>
        <tr>
            <th scope="row">Compound</th>
            <td>$Img_1_Cpd</td>
            <td>$Img_2_Cpd</td>
            <td>$Img_3_Cpd</td>
            <td>$Img_4_Cpd</td>
            <td>$Img_5_Cpd</td>
        </tr>
        <tr>
            <th scope="row">Control</th>
            <td>$Img_1_Ctrl</td>
            <td>$Img_2_Ctrl</td>
            <td>$Img_3_Ctrl</td>
            <td>$Img_4_Ctrl</td>
            <td>$Img_5_Ctrl</td>
        </tr>
    </tbody>
</table>
</div>
"""


_details_values = {
    "LOGO": LOGO,
    "TABLE_INTRO": TABLE_INTRO,
    "TABLE_EXTRO": TABLE_EXTRO,
    "PARM_TABLE_HEADER": PARM_TABLE_HEADER,
}
DETAILS_TEMPL = PreTemplate(DETAILS_TEMPL).substitute(_details_values)