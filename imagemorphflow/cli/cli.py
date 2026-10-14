import click
from imagemorphflow.cli.commands.run_pipeline import run_pipeline
from imagemorphflow.cli.commands.run_pipeline import build_config

@click.group()
def cli():
    """Imagemorphflow CLI - Image-based profiling pipelines."""
    pass

cli.add_command(run_pipeline)
cli.add_command(build_config)
