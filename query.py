#!/usr/bin/env python3
"""Download data from Materials Project.

This script:
1) Queries Materials Project for Gd2Co17 materials.
2) Filters to hexagonal phases.
3) Selects the phase with the lowest energy above hull.
4) Creates an output folder and writes:
   - final structure files (CIF + POSCAR)
   - summary/task JSON files
   - README.md with mp-id, DFT-energy, energy_above_hull,
     xc-functional, and POTCAR info

Usage:
    export MP_API_KEY="<your_api_key>"
    python query.py --formula Gd2Co17 --space-group-type hexagonal --xc scan --potcar-root /projects/mmi/potcarFiles/VASP5.2/potpaw_PBE/
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from mp_api.client import MPRester
from pymatgen.io.vasp import Poscar


SUMMARY_FIELDS = [
    "material_id",
    "formula_pretty",
    "nsites",
    "energy_per_atom",
    "uncorrected_energy_per_atom",
    "energy_above_hull",
    "symmetry",
    "calc_types",
    "origins",
    "task_ids",
    "structure",
]

TASK_FIELDS = [
    "task_id",
    "calc_type",
    "orig_inputs",
    "input",
]


def to_jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    if hasattr(value, "model_dump"):
        return to_jsonable(value.model_dump())
    if hasattr(value, "as_dict"):
        return to_jsonable(value.as_dict())
    if hasattr(value, "__dict__"):
        return to_jsonable(vars(value))
    return str(value)


def crystal_system_matches(summary_doc: Any, target_space_group_type: str) -> bool:
    symmetry = getattr(summary_doc, "symmetry", None)
    crystal_system = getattr(symmetry, "crystal_system", None)
    if crystal_system is None:
        return False
    return str(crystal_system).lower() == target_space_group_type.strip().lower()


def pick_representative_task_id(summary_doc: Any) -> str | None:
    calc_types = getattr(summary_doc, "calc_types", None)
    if calc_types:
        items = list(calc_types.items())
        static_candidates = [
            task_id for task_id, calc_type in items if "static" in str(calc_type).lower()
        ]
        if static_candidates:
            return static_candidates[0]

        return items[0][0]

    origins = getattr(summary_doc, "origins", None) or []
    for origin in origins:
        task_id = getattr(origin, "task_id", None)
        if task_id:
            return str(task_id)

    task_ids = getattr(summary_doc, "task_ids", None) or []
    if task_ids:
        return str(task_ids[0])

    return None


def sanitize_tag(value: Any) -> str:
    text = str(value).strip()
    if not text:
        return "NA"
    cleaned = []
    for ch in text:
        if ch.isalnum() or ch in {"-", "_", "."}:
            cleaned.append(ch)
        elif ch.isspace() or ch in {"=", "/", "(", ")", ":", ";", ","}:
            cleaned.append("-")
    result = "".join(cleaned).strip("-")
    while "--" in result:
        result = result.replace("--", "-")
    return result or "NA"


def extract_xc_info(task_doc: Any | None) -> tuple[str, str, Any]:
    xc_display = "N/A (not returned by this task document)"
    xc_tag = "NA"
    potcar_info = None

    if task_doc is None:
        return xc_display, xc_tag, potcar_info

    task_input = getattr(task_doc, "input", None)
    potcar_info = getattr(task_input, "potcar_spec", None)

    orig_inputs = getattr(task_doc, "orig_inputs", None)
    orig_incar = getattr(orig_inputs, "incar", None) if orig_inputs is not None else None
    if isinstance(orig_incar, dict):
        meta_gga = orig_incar.get("METAGGA")
        gga = orig_incar.get("GGA")
        if meta_gga and str(meta_gga).strip() not in {"", "--", "None"}:
            xc_display = f"METAGGA={meta_gga} (from orig_inputs.incar)"
            xc_tag = sanitize_tag(meta_gga)
            return xc_display, xc_tag, potcar_info
        if gga and str(gga).strip() not in {"", "--", "None"}:
            xc_display = f"GGA={gga} (from orig_inputs.incar)"
            xc_tag = sanitize_tag(gga)
            return xc_display, xc_tag, potcar_info

    parameters = getattr(task_input, "parameters", None)
    if isinstance(parameters, dict):
        meta_gga = parameters.get("METAGGA")
        gga = parameters.get("GGA")
        if meta_gga and str(meta_gga).strip() not in {"", "--", "None"}:
            xc_display = f"METAGGA={meta_gga} (from input.parameters)"
            xc_tag = sanitize_tag(meta_gga)
            potcar_info = getattr(task_input, "potcar_spec", None)
            return xc_display, xc_tag, potcar_info
        if gga and str(gga).strip() not in {"", "--", "None"}:
            xc_display = f"GGA={gga} (from input.parameters)"
            xc_tag = sanitize_tag(gga)
            potcar_info = getattr(task_input, "potcar_spec", None)
            return xc_display, xc_tag, potcar_info
    elif hasattr(parameters, "get"):
        meta_gga = parameters.get("METAGGA")
        gga = parameters.get("GGA")
        if meta_gga and str(meta_gga).strip() not in {"", "--", "None"}:
            xc_display = f"METAGGA={meta_gga} (from input.parameters)"
            xc_tag = sanitize_tag(meta_gga)
            potcar_info = getattr(task_input, "potcar_spec", None)
            return xc_display, xc_tag, potcar_info
        if gga and str(gga).strip() not in {"", "--", "None"}:
            xc_display = f"GGA={gga} (from input.parameters)"
            xc_tag = sanitize_tag(gga)
            potcar_info = getattr(task_input, "potcar_spec", None)
            return xc_display, xc_tag, potcar_info

    potcar_info = getattr(task_input, "potcar_spec", None)
    if potcar_info:
        potcar_text = " ".join(str(getattr(spec, "titel", "")) for spec in potcar_info).upper()
        if "PBE" in potcar_text:
            return "PBE (inferred from POTCAR titel)", "PBE", potcar_info
        if "LDA" in potcar_text:
            return "LDA (inferred from POTCAR titel)", "LDA", potcar_info

    return xc_display, xc_tag, potcar_info


def xc_class(task_doc: Any | None) -> str:
    if task_doc is None:
        return "unknown"

    xc_display, xc_tag, _ = extract_xc_info(task_doc)
    combined = f"{xc_display} {xc_tag}".lower()

    if "scan" in combined:
        return "scan"

    if any(token in combined for token in ["pbe", "gga", "lda", "pe", "ps", "pw91"]):
        return "gga"

    return "unknown"


def pick_task_for_xc(task_docs: list[Any], requested_xc: str) -> Any | None:
    if not task_docs:
        return None

    if requested_xc == "auto":
        with_potcar = [
            doc for doc in task_docs if getattr(getattr(doc, "input", None), "potcar_spec", None)
        ]
        return with_potcar[0] if with_potcar else task_docs[0]

    matches = [doc for doc in task_docs if xc_class(doc) == requested_xc]
    if not matches:
        return None

    with_potcar = [
        doc for doc in matches if getattr(getattr(doc, "input", None), "potcar_spec", None)
    ]
    return with_potcar[0] if with_potcar else matches[0]


def write_readme(
    out_dir: Path,
    summary_doc: Any,
    task_doc: Any | None,
    formula: str,
    space_group_type: str,
    kspacing_value: Any | None,
    kpoints_written: bool,
) -> None:
    material_id = str(getattr(summary_doc, "material_id", "unknown"))
    nsites = getattr(summary_doc, "nsites", None)
    energy_above_hull = getattr(summary_doc, "energy_above_hull", None)
    dft_energy = getattr(summary_doc, "uncorrected_energy_per_atom", None)
    if dft_energy is None:
        dft_energy = getattr(summary_doc, "energy_per_atom", None)
    total_energy = None
    if dft_energy is not None and nsites is not None:
        total_energy = dft_energy * nsites

    xc_functional, _, potcar_info = extract_xc_info(task_doc)

    if potcar_info is None:
        potcar_text = "N/A (not returned by this task document)"
    else:
        potcar_text = json.dumps(to_jsonable(potcar_info), indent=2)

    readme = f"""# {space_group_type.capitalize()} {formula} (Materials Project)

## Key metadata
- mp-id: {material_id}
- formula: {formula}
- space-group type: {space_group_type}
- DFT-energy (eV/atom): {dft_energy}
- total-energy (eV/cell): {total_energy}
- energy_above_hull (eV/atom): {energy_above_hull}
- xc-functional: {xc_functional}
- KSPACING: {kspacing_value if kspacing_value is not None else "N/A"}

## POTCAR info
```json
{potcar_text}
```

## Notes
- `DFT-energy` is taken from `uncorrected_energy_per_atom` when available; otherwise `energy_per_atom`.
- `total-energy` is computed as `DFT-energy (eV/atom) * nsites`.
- Values are fetched directly from the MP API at runtime.
- `KPOINTS` file written: {kpoints_written}
{('- `KPOINTS` is intentionally skipped because `KSPACING` is present in `INCAR`.' if kspacing_value is not None else '')}
"""

    (out_dir / "README.md").write_text(readme, encoding="utf-8")


def format_incar_value(value: Any) -> str:
    if isinstance(value, bool):
        return ".TRUE." if value else ".FALSE."
    if isinstance(value, (list, tuple)):
        return " ".join(str(v) for v in value)
    return str(value)


def get_incar_params(task_doc: Any | None) -> dict[str, Any] | None:
    if task_doc is None:
        return None

    orig_inputs = getattr(task_doc, "orig_inputs", None)
    if orig_inputs is not None:
        orig_incar = getattr(orig_inputs, "incar", None)
        if isinstance(orig_incar, dict) and orig_incar:
            return orig_incar

    task_input = getattr(task_doc, "input", None)
    parameters = getattr(task_input, "parameters", None) if task_input else None
    if isinstance(parameters, dict) and parameters:
        return parameters

    return None


def write_incar(out_dir: Path, task_doc: Any | None) -> dict[str, Any] | None:
    incar_params = get_incar_params(task_doc)
    if not isinstance(incar_params, dict):
        return None

    lines = []
    for key, value in incar_params.items():
        lines.append(f"{key} = {format_incar_value(value)}")

    if lines:
        (out_dir / "INCAR").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return incar_params


def write_kpoints(out_dir: Path, task_doc: Any | None) -> None:
    if task_doc is None:
        return

    task_input = getattr(task_doc, "input", None)
    kpoints_obj = getattr(task_input, "kpoints", None) if task_input else None

    if kpoints_obj is None:
        orig_inputs = getattr(task_doc, "orig_inputs", None)
        if orig_inputs is not None:
            kpoints_obj = getattr(orig_inputs, "kpoints", None)
            if kpoints_obj is None and isinstance(orig_inputs, dict):
                kpoints_obj = orig_inputs.get("kpoints")

    if kpoints_obj is None:
        return

    if hasattr(kpoints_obj, "write_file"):
        kpoints_obj.write_file(str(out_dir / "KPOINTS"))
        return

    kpoints_data = to_jsonable(kpoints_obj)
    if not isinstance(kpoints_data, dict):
        return

    comment = kpoints_data.get("comment") or "KPOINTS generated from Materials Project"
    num_kpts = int(kpoints_data.get("num_kpts", 0) or 0)
    style = str(kpoints_data.get("style") or "Gamma").upper()
    kpts = kpoints_data.get("kpoints") or []
    usershift = kpoints_data.get("usershift") or [0, 0, 0]

    lines = [comment, str(num_kpts), style]

    if num_kpts == 0:
        if kpts:
            first = kpts[0]
            lines.append(" ".join(str(v) for v in first))
        else:
            lines.append("1 1 1")
        lines.append(" ".join(str(v) for v in usershift))
    else:
        for point in kpts:
            lines.append(" ".join(str(v) for v in point))

        weights = kpoints_data.get("kpts_weights") or []
        if weights and len(weights) == len(kpts):
            for weight in weights:
                lines.append(str(weight))

    (out_dir / "KPOINTS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def task_has_kpoints(task_doc: Any | None) -> bool:
    if task_doc is None:
        return False

    task_input = getattr(task_doc, "input", None)
    if task_input is not None and getattr(task_input, "kpoints", None) is not None:
        return True

    orig_inputs = getattr(task_doc, "orig_inputs", None)
    if orig_inputs is not None and getattr(orig_inputs, "kpoints", None) is not None:
        return True

    return False


def parse_potcar_label(potcar_spec_item: Any) -> str | None:
    titel = str(getattr(potcar_spec_item, "titel", "")).strip()
    if not titel:
        return None
    parts = titel.split()
    if len(parts) < 2:
        return None
    return parts[1]


def write_potcar(
    out_dir: Path,
    structure: Any,
    task_doc: Any | None,
    potcar_root: Path,
) -> None:
    if task_doc is None or structure is None:
        return

    task_input = getattr(task_doc, "input", None)
    potcar_spec = getattr(task_input, "potcar_spec", None) if task_input else None
    if not potcar_spec:
        return

    labels = [label for label in (parse_potcar_label(spec) for spec in potcar_spec) if label]
    if not labels:
        return

    poscar = Poscar(structure)
    species_order = list(poscar.site_symbols)

    assembled_chunks: list[bytes] = []
    missing_entries: list[str] = []

    for symbol in species_order:
        matching_label = None
        for label in labels:
            if label == symbol or label.startswith(f"{symbol}_"):
                matching_label = label
                break

        if matching_label is None:
            missing_entries.append(f"{symbol}: no matching label in potcar_spec={labels}")
            continue

        candidates = [
            potcar_root / matching_label / "POTCAR",
            potcar_root / symbol / "POTCAR",
        ]

        found_path = next((path for path in candidates if path.is_file()), None)
        if found_path is None:
            missing_entries.append(
                f"{symbol}: missing POTCAR file (tried {', '.join(str(p) for p in candidates)})"
            )
            continue

        assembled_chunks.append(found_path.read_bytes())

    if missing_entries:
        (out_dir / "POTCAR.missing.txt").write_text(
            "\n".join(missing_entries) + "\n", encoding="utf-8"
        )
        return

    normalized_chunks = [chunk.rstrip(b"\n") for chunk in assembled_chunks]
    potcar_bytes = b"\n".join(normalized_chunks)
    (out_dir / "POTCAR").write_bytes(potcar_bytes)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--api-key",
        default=os.environ.get("MP_API_KEY"),
        help="Materials Project API key (or set MP_API_KEY)",
    )
    parser.add_argument(
        "--formula", "-f",
        default="Gd2Co17",
        help="Chemical formula to query, e.g. Gd2Co17",
    )
    parser.add_argument(
        "--space-group-type", "-s",
        default="hexagonal",
        help="Crystal system type to filter, e.g. hexagonal, cubic, tetragonal",
    )
    parser.add_argument(
        "--potcar-root",
        default="/projects/mmi/potcarFiles/VASP5.2/potpaw_PBE/",
        help="Root directory containing VASP POTCAR folders",
    )
    parser.add_argument(
        "--xc",
        default="auto",
        choices=["auto", "gga", "scan"],
        help="Target XC family for task selection: auto, gga, or scan",
    )
    
    args = parser.parse_args()

    if not args.api_key:
        raise SystemExit("Missing API key. Provide --api-key or set MP_API_KEY.")

    with MPRester(args.api_key) as mpr:
        docs = mpr.materials.summary.search(
            formula=args.formula,
            fields=SUMMARY_FIELDS,
        )

        matching_docs = [
            doc for doc in docs if crystal_system_matches(doc, args.space_group_type)
        ]
        if not matching_docs:
            raise SystemExit(
                f"No {args.space_group_type} {args.formula} entries found on Materials Project."
            )

        target_doc = min(
            matching_docs,
            key=lambda d: getattr(d, "energy_above_hull", float("inf")),
        )
        material_id = str(target_doc.material_id)

        task_docs_all: list[Any] = []

        task_id = pick_representative_task_id(target_doc)
        if task_id is not None:
            preferred_docs = mpr.materials.tasks.search(task_ids=[str(task_id)], fields=TASK_FIELDS)
            task_docs_all.extend(preferred_docs)

        fallback_task_ids = [str(tid) for tid in (getattr(target_doc, "task_ids", None) or [])]
        if fallback_task_ids:
            fallback_docs = mpr.materials.tasks.search(task_ids=fallback_task_ids, fields=TASK_FIELDS)
            seen = {str(getattr(doc, "task_id", "")) for doc in task_docs_all}
            for doc in fallback_docs:
                doc_id = str(getattr(doc, "task_id", ""))
                if doc_id not in seen:
                    task_docs_all.append(doc)
                    seen.add(doc_id)

        task_doc = pick_task_for_xc(task_docs_all, args.xc)
        if args.xc != "auto" and task_doc is None:
            raise SystemExit(
                f"No task with XC='{args.xc}' found for {args.formula} ({material_id})."
            )

        kpoints_task_doc = task_doc
        if not task_has_kpoints(kpoints_task_doc):
            with_kpoints = [doc for doc in task_docs_all if task_has_kpoints(doc)]
            if with_kpoints:
                if args.xc == "auto":
                    kpoints_task_doc = with_kpoints[0]
                else:
                    with_kpoints_xc = [doc for doc in with_kpoints if xc_class(doc) == args.xc]
                    if with_kpoints_xc:
                        kpoints_task_doc = with_kpoints_xc[0]
                    else:
                        kpoints_task_doc = with_kpoints[0]

    formula_tag = args.formula.replace(" ", "")
    space_group_tag = args.space_group_type.lower().replace(" ", "-")
    _, xc_tag, _ = extract_xc_info(task_doc)
    output_dir = Path(f"{formula_tag}-{space_group_tag}-{material_id}-{xc_tag}").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    incar_params = None
    if task_doc is not None:
        incar_params = write_incar(output_dir, task_doc)

    kspacing_value = None
    if isinstance(incar_params, dict):
        for key, value in incar_params.items():
            if str(key).upper() == "KSPACING":
                kspacing_value = value
                break

    kpoints_written = False
    if kspacing_value is None:
        write_kpoints(output_dir, kpoints_task_doc)
        kpoints_written = (output_dir / "KPOINTS").is_file()
    else:
        kpoints_path = output_dir / "KPOINTS"
        if kpoints_path.is_file():
            kpoints_path.unlink()

    structure = getattr(target_doc, "structure", None)
    if structure is not None:
        structure.to(filename=str(output_dir / "final_structure.cif"))
        Poscar(structure).write_file(str(output_dir / "POSCAR"))

    write_potcar(output_dir, structure, task_doc, Path(args.potcar_root))

    write_readme(
        output_dir,
        target_doc,
        task_doc,
        args.formula,
        args.space_group_type,
        kspacing_value,
        kpoints_written,
    )

    print(f"Saved files in: {output_dir}")


if __name__ == "__main__":
    main()
