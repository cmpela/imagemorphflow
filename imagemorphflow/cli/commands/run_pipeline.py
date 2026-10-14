import click
import subprocess


@click.group()
def cli():
    """
    Analyze image-based assays with imagemorphflow.

    Usage: imf run --script script_name --config /path/to/config.yaml
    """
    pass


@cli.command("run")
@click.version_option("2.0.0", prog_name="run pipeline")
@click.option(
    "-s", "--script", type=click.STRING, help="Single script to run (e.g. 'load_data')"
)
@click.option(
    "-c",
    "--config",
    type=click.Path(exists=True),
    required=True,
    help="Path to config.yaml",
)
def run_pipeline(script, config):
    """
    Run one or multiple processing steps with the given config file.
    """

    def run_script(script_name, config_path):
        cmd = [
            "python",
            "-m",
            f"imagemorphflow.processing.{script_name}",
            "--config",
            config_path,
        ]
        click.echo(f"Executing: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        click.echo(result.stdout)
        if result.stderr:
            click.echo(click.style(result.stderr, fg="red"))

        if result.returncode != 0:
            raise click.ClickException(
                f"Script '{script_name}' failed with return code {result.returncode}"
            )

    if script:
        run_script(script, config)
    else:
        scripts = [
            "predict_masks",
            "load_data",
            "run_cellprofiler",
            "join_profiles",
        ]
        for step in scripts:
            click.echo(click.style(f"\n🔧 Running step: {step}", fg="cyan"))
            run_script(step, config)


@cli.command("build")
@click.option(
    "-m",
    "--manifest",
    type=click.STRING,
    help="Manifest file to build configuration file (e.g. 'example_manifest.json')",
)
def build_config(manifest):
    """
    Usage: imf build --manifest /path/to/example_manifest.json
    """
    cmd = [
        "python",
        "-m",
        "imagemorphflow.processing.config_builder",
        "--manifest",
        manifest,
    ]
    click.echo(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    click.echo(result.stdout)
    if result.stderr:
        click.echo(click.style(result.stderr, fg="red"))

    if result.returncode != 0:
        raise click.ClickException(
            f"Build config failed with return code {result.returncode}"
        )


if __name__ == "__main__":
    cli()
