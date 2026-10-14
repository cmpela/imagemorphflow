#!/usr/bin/env python3

# 2025-09-19 Historically the cellpainting transfer was done one plate after the other, manually more or less.
# With the automation of the Echo transfer on the Burrito, the transfer files have a different structure.
# This code is just to transform the new file version to the old file version, also maintain the same filename pattern,
# so the cellpainting3 function which join the destination layout will be able to still read this XML.

#!/usr/bin/env python3
import argparse
import re
import logging
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

# ---------------------------
# Logger setup
# ---------------------------
def setup_logger(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"echo_batch_{stamp}.log"

    logger = logging.getLogger("echo_batch")
    logger.setLevel(logging.INFO)
    logger.handlers[:] = []  # clear duplicate handlers if re-run in notebook

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    fh = logging.FileHandler(str(log_path), encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    logger.info(f"Logging to {log_path}")
    return logger

# ---------------------------
# Convert Transfer to E5XX
# ---------------------------
def convert_transfer_to_e5xx(input_xml: str, output_xml: str) -> None:
    src_tree = ET.parse(input_xml)
    src_root = src_tree.getroot()

    run_dt = src_root.get("date", "")
    if run_dt:
        try:
            dt = datetime.strptime(run_dt, "%Y-%m-%d %H:%M:%S.%f")
            run_dt_norm = dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            run_dt_norm = run_dt
    else:
        run_dt_norm = ""

    plate_info = src_root.find("plateInfo")
    def _plate_attr(ptype, attr):
        if plate_info is None:
            return ""
        node = plate_info.find(f".//plate[@type='{ptype}']")
        return (node.get(attr) if node is not None else "") or ""

    src_plate_type = _plate_attr("source", "name")
    dest_plate_type = _plate_attr("destination", "name")
    src_plate_barcode = _plate_attr("source", "barcode")
    dest_plate_barcode = _plate_attr("destination", "barcode")

    def add(parent, tag, name_attr, text=""):
        el = ET.SubElement(parent, tag, {"name": name_attr})
        el.text = "" if text is None else str(text)
        return el

    rep = ET.Element("report")

    proto_text = (dest_plate_barcode.strip() + ".edr") if dest_plate_barcode and dest_plate_barcode.strip() else "Echo_Transfer.edr"

    hdr = ET.SubElement(rep, "reportheader")
    add(hdr, "RunID", "Run ID", "")
    add(hdr, "RunDateTime", "Run Date/Time", run_dt_norm)
    add(hdr, "AppName", "Application Name", "")
    add(hdr, "AppVersion", "Application Version", "")
    add(hdr, "ProtocolName", "Protocol Name", proto_text)
    add(hdr, "UserName", "User Name", "")

    def emit_record(parent, w_attrib, include_status: bool):
        rec = ET.SubElement(parent, "record")
        add(rec, "SrcPlateName", "Source Plate Name", "Source Plate[1]")
        add(rec, "SrcPlateBarcode", "Source Plate Barcode", src_plate_barcode)
        add(rec, "SrcPlateType", "Source Plate Type", src_plate_type)
        add(rec, "SrcWell", "Source Well", w_attrib.get("n", ""))
        add(rec, "SrcConc", "Source Concentration", "")
        add(rec, "SrcConcUnits", "Source Concentration Units", "")

        add(rec, "DestPlateName", "Destination Plate Name", "Destination Plate[1]")
        add(rec, "DestPlateBarcode", "Destination Plate Barcode", dest_plate_barcode)
        add(rec, "DestPlateType", "Destination Plate Type", dest_plate_type)
        add(rec, "DestWell", "Destination Well", w_attrib.get("dn", w_attrib.get("n", "")))
        add(rec, "DestConc", "Destination Concentration", "")
        add(rec, "DestConcUnits", "Destination Concentration Units", "")

        add(rec, "SampleID", "Sample ID", "")
        add(rec, "SampleName", "Sample Name", "")

        add(rec, "XferVol", "Transfer Volume", w_attrib.get("vt", ""))
        add(rec, "ActualVol", "Actual Volume", w_attrib.get("avt", ""))
        add(rec, "CurrentFluidVolume", "Current Fluid Volume", w_attrib.get("cvl", ""))
        add(rec, "FluidComposition", "Fluid Composition", "")
        add(rec, "FluidUnits", "Fluid Units", w_attrib.get("fldu", ""))
        add(rec, "FluidType", "Fluid Type", w_attrib.get("fld", ""))

        status_text = (w_attrib.get("reason", "") if include_status else "")
        add(rec, "XferStatus", "Transfer Status", status_text)
        return rec

    rep_ex = ET.SubElement(rep, "reportexceptions")
    skipped = src_root.find("skippedwells")
    if skipped is not None:
        for w in skipped.findall("w"):
            emit_record(rep_ex, dict(w.attrib), include_status=True)

    rep_body = ET.SubElement(rep, "reportbody")
    printmap = src_root.find("printmap")
    if printmap is not None:
        for w in printmap.findall("w"):
            wat = dict(w.attrib)
            wat.pop("reason", None)
            emit_record(rep_body, wat, include_status=False)

    ftr = ET.SubElement(rep, "reportfooter")
    serial = src_root.get("serial_number", "")
    add(ftr, "InstrName", "Instrument Name", serial)
    add(ftr, "InstrModel", "Instrument Model", "")
    add(ftr, "InstrSN", "Instrument Serial Number", serial)
    add(ftr, "InstrSWVersion", "Instrument Software Version", "")

    def _indent(elem, level=0):
        i = "\n" + level * "     "
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "     "
            for e in elem:
                _indent(e, level + 1)
                if not e.tail or not e.tail.strip():
                    e.tail = i + "     "
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i

    _indent(rep)
    ET.ElementTree(rep).write(output_xml, encoding="utf-8",
                              xml_declaration=True, short_empty_elements=False)

# ---------------------------
# Batch driver
# ---------------------------
LETTER_ORDER = {"a": 1, "b": 2, "c": 3}

LETTER_RE = re.compile(
    r"^(Transfer_Data.*)_([a-z])\d?\.xml$",
    re.IGNORECASE,
)

GENERATED_RE = re.compile(
    r"^.+_Transfer_\d+\.xml$",
    re.IGNORECASE,
)


def detect_serial(input_xml: Path) -> str:
    try:
        root = ET.parse(str(input_xml)).getroot()
        return root.get("serial_number", "") or "E5XX-UNKNOWN"
    except Exception:
        return "E5XX-UNKNOWN"


def detect_run_datetime(input_xml: Path) -> datetime:
    """
    Return the Echo run datetime stored inside the XML.

    Falls back to a timestamp in the filename and then to the file
    modification time if the XML date is unavailable.
    """
    try:
        root = ET.parse(str(input_xml)).getroot()
        run_dt = root.get("date", "")

        if run_dt:
            for fmt in (
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S",
            ):
                try:
                    return datetime.strptime(run_dt, fmt)
                except ValueError:
                    pass
    except Exception:
        pass

    # Example:
    # 2026-08-27_10-35-01_UnknownBarCode_print.xml
    match = re.search(
        r"(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})",
        input_xml.name,
    )

    if match:
        try:
            return datetime.strptime(
                f"{match.group(1)}_{match.group(2)}",
                "%Y-%m-%d_%H-%M-%S",
            )
        except ValueError:
            pass

    return datetime.fromtimestamp(input_xml.stat().st_mtime)


def batch_convert_standard(
    base_dir: Path,
    logger: logging.Logger,
    dry_run: bool = False,
    overwrite: bool = False,
) -> None:
    """
    Standard Cell Painting mode.

    Looks for Transfer_Data XML files ending in _a, _b or _c and converts
    them to Transfer_1, Transfer_2 and Transfer_3.
    """
    files = list(base_dir.rglob("Transfer_Data*.xml"))

    if not files:
        logger.warning(
            f"No 'Transfer_Data*.xml' files found under: {base_dir}"
        )
        return

    by_dir = {}

    for f in files:
        by_dir.setdefault(f.parent, []).append(f)

    for folder, flist in sorted(by_dir.items()):
        per_letter = {}
        ignored = []

        for f in flist:
            m = LETTER_RE.match(f.name)

            if not m:
                ignored.append(f.name)
                continue

            letter = m.group(2).lower()

            if letter not in LETTER_ORDER:
                ignored.append(f.name)
                continue

            if letter in per_letter:
                logger.warning(
                    f"[{folder}] Duplicate letter '{letter}': "
                    f"{per_letter[letter].name} & {f.name}. "
                    f"Keeping the first, ignoring the second."
                )
                continue

            per_letter[letter] = f

        if not per_letter:
            logger.info(
                f"[{folder}] No _a/_b/_c files found. "
                f"Ignored this folder."
            )

            if ignored:
                logger.info(
                    f"[{folder}] Ignored (no letter suffix): "
                    f"{', '.join(sorted(ignored))}"
                )

            continue

        expected = set(LETTER_ORDER.keys())
        found = set(per_letter.keys())
        missing = expected - found

        if missing:
            logger.warning(
                f"[{folder}] Missing letters: "
                f"{', '.join(sorted(missing))}. "
                f"Found: {', '.join(sorted(found))}"
            )

        if ignored:
            logger.info(
                f"[{folder}] Ignored files "
                f"(pattern didn't match _a/_b/_c): "
                f"{', '.join(sorted(ignored))}"
            )

        for letter in sorted(
            per_letter.keys(),
            key=lambda x: LETTER_ORDER[x],
        ):
            f = per_letter[letter]
            num = LETTER_ORDER[letter]
            serial = detect_serial(f)

            out_name = f"{serial}_Transfer_{num}.xml"
            out_path = folder / out_name

            if out_path.exists() and not dry_run and not overwrite:
                logger.info(
                    f"[{folder}] {out_name} already exists -> SKIP "
                    f"(use --overwrite to force)."
                )
                continue

            logger.info(
                f"[{folder}] {f.name} -> {out_name}"
            )

            if not dry_run:
                convert_transfer_to_e5xx(
                    str(f),
                    str(out_path),
                )


def batch_convert_chronological(
    base_dir: Path,
    logger: logging.Logger,
    dry_run: bool = False,
    overwrite: bool = False,
) -> None:
    """
    Chronological mode.

    Recursively finds XML files, groups them by directory, sorts each group
    by Echo run datetime, and numbers them Transfer_1, Transfer_2, etc.
    """
    files = [
        f
        for f in base_dir.rglob("*.xml")
        if not GENERATED_RE.match(f.name)
    ]

    if not files:
        logger.warning(
            f"No XML files found under: {base_dir}"
        )
        return

    by_dir = {}

    for f in files:
        by_dir.setdefault(f.parent, []).append(f)

    for folder, flist in sorted(by_dir.items()):
        ordered_files = sorted(
            flist,
            key=detect_run_datetime,
        )

        logger.info(
            f"[{folder}] Found {len(ordered_files)} XML file(s)."
        )

        for num, f in enumerate(ordered_files, start=1):
            serial = detect_serial(f)
            run_dt = detect_run_datetime(f)

            out_name = f"{serial}_Transfer_{num}.xml"
            out_path = folder / out_name

            if out_path.exists() and not dry_run and not overwrite:
                logger.info(
                    f"[{folder}] {out_name} already exists -> SKIP "
                    f"(use --overwrite to force)."
                )
                continue

            logger.info(
                f"[{folder}] "
                f"{run_dt.strftime('%Y-%m-%d %H:%M:%S')} | "
                f"{f.name} -> {out_name}"
            )

            if not dry_run:
                convert_transfer_to_e5xx(
                    str(f),
                    str(out_path),
                )


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Batch-convert Echo XML files to E5XX-style XMLs."
        )
    )

    ap.add_argument(
        "--base-dir",
        required=True,
        help="Root directory containing Echo XML files.",
    )

    ap.add_argument(
        "--log-dir",
        default=None,
        help="Directory to write the log file (default: base-dir).",
    )

    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="List actions without writing outputs.",
    )

    ap.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing converted XML files.",
    )

    ap.add_argument(
        "--chronological",
        action="store_true",
        help=(
            "Ignore the standard Transfer_Data _a/_b/_c naming scheme. "
            "Convert all XML files found recursively and number them "
            "chronologically within each directory."
        ),
    )

    args = ap.parse_args()

    base = Path(args.base_dir).expanduser().resolve()

    if not base.exists():
        raise SystemExit(
            f"Base directory not found: {base}"
        )

    log_dir = (
        Path(args.log_dir).expanduser().resolve()
        if args.log_dir
        else base
    )

    logger = setup_logger(log_dir)

    logger.info(f"Base dir: {base}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(
        f"Mode: "
        f"{'chronological' if args.chronological else 'standard'}"
    )

    if args.chronological:
        batch_convert_chronological(
            base,
            logger=logger,
            dry_run=args.dry_run,
            overwrite=args.overwrite,
        )
    else:
        batch_convert_standard(
            base,
            logger=logger,
            dry_run=args.dry_run,
            overwrite=args.overwrite,
        )

    logger.info("Done.")


if __name__ == "__main__":
    main()