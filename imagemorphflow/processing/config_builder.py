#!/usr/bin/env python3
"""
Config Builder - Generates effective configuration from manifests and config overlays
Preserves placeholders in the YAML content but resolves them for file paths
"""

import json
import yaml
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import warnings


DEFAULT_CONFIGS_DIR = (Path(__file__).resolve().parent / "configs")


class ConfigBuilder:
    def __init__(self, configs_dir: str, base_config: str = "base.yaml"):
        self.configs_dir = Path(configs_dir)
        self.base_config_path = self.configs_dir / base_config
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def load_yaml(self, filepath: Path) -> Dict[str, Any]:
        """Load YAML file"""
        with open(filepath, "r") as f:
            return yaml.safe_load(f)

    def save_yaml(self, data: Dict[str, Any], filepath: Path):
        """Save YAML file preserving list formatting as inline"""

        class InlineListDumper(yaml.Dumper):
            def represent_list(self, data):
                return self.represent_sequence(
                    "tag:yaml.org,2002:seq", data, flow_style=True
                )

        InlineListDumper.add_representer(list, InlineListDumper.represent_list)

        with open(filepath, "w") as f:
            yaml.dump(
                data,
                f,
                Dumper=InlineListDumper,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

    def load_manifest(self, manifest_path: str) -> Dict[str, Any]:
        """Load manifest JSON file"""
        with open(manifest_path, "r") as f:
            return json.load(f)

    def resolve_placeholders_for_paths(
        self, text: str, username: str, project_name: str
    ) -> str:
        """Resolve placeholders only for determining file system paths"""
        if not isinstance(text, str):
            return text
        return text.replace("{username}", username).replace(
            "{project_name}", project_name
        )

    def deep_merge(
        self, base: Dict[str, Any], override: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Recursively merge two dictionaries"""
        result = base.copy()

        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self.deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def build_config(
        self,
        manifest: Dict[str, Any],
        step: str,
        cli_overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build effective configuration based on manifest and step"""

        # Start with base config
        config = self.load_yaml(self.base_config_path)

        # Apply modality and microscope specific configs
        modality = manifest["modality"]
        microscope = manifest["microscope"]
        mask_predict = manifest.get("mask_predict", False)
        join_profile = manifest.get("join_profile", "basic")

        # Modality config
        if modality == "brightfield":
            modality_config = self.configs_dir / "modality" / "brightfield.yaml"
        elif modality == "cellpainting" and microscope == "imagexpress":
            modality_config = (
                self.configs_dir / "modality" / "cellpainting.imagexpress.yaml"
            )
        elif modality == "cellpainting" and microscope == "endeavor":
            modality_config = (
                self.configs_dir / "modality" / "cellpainting.endeavor.yaml"
            )
        else:
            raise ValueError(
                f"Unsupported modality/microscope: {modality}/{microscope}"
            )

        if modality_config.exists():
            modality_data = self.load_yaml(modality_config)
            config = self.deep_merge(config, modality_data)

        # Mask config
        mask_config = (
            self.configs_dir / "mask" / ("on.yaml" if mask_predict else "off.yaml")
        )
        if mask_config.exists():
            mask_data = self.load_yaml(mask_config)
            config = self.deep_merge(config, mask_data)

        # Step-specific configs
        if step == "illum":
            if modality == "cellpainting":
                illum_config = (
                    self.configs_dir / "illum" / f"cellpainting.{microscope}.yaml"
                )
                if illum_config.exists():
                    illum_data = self.load_yaml(illum_config)
                    config = self.deep_merge(config, illum_data)
            else:
                illum_config = (
                    self.configs_dir / "illum" / f"illum.dummy.yaml"
                )
                if illum_config.exists():
                    illum_data = self.load_yaml(illum_config)
                    config = self.deep_merge(config, illum_data)
                # raise ValueError("'illum' is only valid for cellpainting")
                warnings.warn("Verify if illum is really needed!", UserWarning)

        elif step == "analysis":
            analysis_config = self.configs_dir / f"analysis.{microscope}.yaml"
            if analysis_config.exists():
                analysis_data = self.load_yaml(analysis_config)
                config = self.deep_merge(config, analysis_data)
            else:
                raise ValueError(f"Unknown microscope for analysis: {microscope}")

        elif step == "join":
            join_config = self.configs_dir / f"join.{join_profile}.yaml"
            if join_config.exists():
                join_data = self.load_yaml(join_config)
                config = self.deep_merge(config, join_data)

        # Set illumination correction based on manifest steps
        has_illum_step = "illum" in manifest.get("steps", [])
        if step == "illum":
            config["correct_illumination"] = False
        else:
            config["correct_illumination"] = has_illum_step

        # Apply manifest overrides com merge recursivo
        if "overrides" in manifest:
            config = self.deep_merge(config, manifest["overrides"])

        # Apply CLI overrides com merge recursivo
        if cli_overrides:
            config = self.deep_merge(config, cli_overrides)

        return config

    def generate_effective_config(
        self,
        manifest_path: str,
        step: str,
        output_dir: Optional[str] = None,
        cli_overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate effective configuration"""

        manifest = self.load_manifest(manifest_path)
        config = self.build_config(manifest, step, cli_overrides)

        # Determine output directory
        if output_dir:
            effective_dir = Path(output_dir)
        else:
            username = os.getenv("USERNAME") or os.getenv("USER") or "unknown_user"
            project_name = config.get("project_name", "unknown_project")

            base_path_template = config.get("base_path", "/tmp")
            base_path_resolved = self.resolve_placeholders_for_paths(
                base_path_template, username, project_name
            )

            effective_dir = Path(base_path_resolved) / "configs" / "effective"

        effective_dir.mkdir(parents=True, exist_ok=True)

        # Save effective config (COM PLACEHOLDERS INTACTOS)
        config_filename = effective_dir / f"{self.timestamp}_{step}.yaml"
        self.save_yaml(config, config_filename)

        # Create symlink
        latest_link = effective_dir / f"latest_{step}.yaml"
        if latest_link.exists():
            latest_link.unlink()
        latest_link.symlink_to(config_filename)

        # Save manifest copy
        manifest_copy = effective_dir / f"{self.timestamp}_manifest.json"
        with open(manifest_copy, "w") as f:
            json.dump(manifest, f, indent=2)

        print(f"[INFO] Effective config -> {config_filename}")
        print(f"[INFO] Latest symlink   -> {latest_link}")
        print(f"[INFO] Manifest copy    -> {manifest_copy}")

        return config


def main():
    parser = argparse.ArgumentParser(
        description="Build effective configuration from manifest"
    )
    parser.add_argument(
        "-m", "--manifest", required=True, help="Path to manifest JSON file"
    )
    parser.add_argument(
        "-s",
        "--step",
        choices=["init", "load_data", "illum", "analysis", "ingest", "join"],
        help="Specific step to build config for (default: all steps from manifest)",
    )
    parser.add_argument(
        "-c",
        "--configs-dir",
        default=str(DEFAULT_CONFIGS_DIR),
        help="Directory containing configuration files",
    )
    parser.add_argument(
        "-o", "--output-dir", help="Output directory for effective configs"
    )
    parser.add_argument(
        "-O", "--override", action="append", help="CLI override in key=value format"
    )

    args = parser.parse_args()

    # Parse CLI overrides
    cli_overrides = {}
    if args.override:
        for ovr in args.override:
            key, value = ovr.split("=", 1)
            # Try to convert to appropriate type
            try:
                if value.lower() in ("true", "false"):
                    value = value.lower() == "true"
                elif value.isdigit():
                    value = int(value)
                elif value.replace(".", "").isdigit():
                    value = float(value)
            except:
                pass  # Keep as string if conversion fails
            cli_overrides[key] = value

    # Build configuration
    builder = ConfigBuilder(args.configs_dir)
    manifest = builder.load_manifest(args.manifest)

    # Determine which steps to process
    if args.step:
        steps = [args.step]  # Use step from CLI if provided
    else:
        steps = manifest.get("steps", [])  # Use steps from manifest

    if not steps:
        print(
            "[ERROR] No steps specified in manifest and no --step provided",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        for step in steps:
            print(f"\n[INFO] Building configuration for step: {step}")
            config = builder.generate_effective_config(
                manifest_path=args.manifest,
                step=step,
                output_dir=args.output_dir,
                cli_overrides=cli_overrides if cli_overrides else None,
            )

        print(f"\n[INFO] Successfully generated {len(steps)} configuration files")

    except Exception as e:
        print(f"[ERROR] Failed to build configuration: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
