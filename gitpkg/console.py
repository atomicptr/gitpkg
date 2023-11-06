from rich.console import Console

console = Console()


def fatal(*args, **kwargs) -> None:
    console.print(":cross_mark:  ERROR:", *args, **kwargs)
    exit(1)


def success(*args, **kwargs) -> None:
    console.print(":white_check_mark:  ", *args, **kwargs)
