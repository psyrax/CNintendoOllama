import click


@click.command()
@click.argument("extracted_json")
def analyze(extracted_json):
    """Analiza un JSON extraído usando Ollama."""
    pass
