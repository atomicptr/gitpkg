from rich.console import Console

console = Console()


def fatal(*args, **kwargs) -> None:
    console.print(":cross_mark:  ERROR:", *args, **kwargs)
    exit(1)