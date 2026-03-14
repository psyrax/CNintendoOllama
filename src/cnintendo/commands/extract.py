import click


@click.command()
@click.argument("pdf_path")
def extract(pdf_path):
    """Extrae texto e imágenes de un PDF."""
    pass
