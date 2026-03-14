import click
from cnintendo.commands import inspect, extract, analyze, export, run as run_cmd


@click.group()
@click.version_option("0.1.0")
def main():
    """Herramientas CLI para extraer datos de revistas de videojuegos en PDF."""
    pass


main.add_command(inspect.inspect)
main.add_command(extract.extract)
main.add_command(analyze.analyze)
main.add_command(export.export)
main.add_command(run_cmd.run)
