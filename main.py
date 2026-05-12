"""
RISC-V Instruction Set Explorer
=================================
Tier 1: Parse instr_dict.json, group by extension, find overlaps.
Tier 2: Cross-reference extensions against the RISC-V ISA Manual AsciiDoc sources.
Tier 3 (Bonus): Extension overlap graph via networkx/matplotlib.
"""

# ─────────────────────────────────────────────────────────────────────────────
# DEPENDENCY BOOTSTRAP
# Reads requirements.txt and auto-installs any missing packages before the
# rest of the imports run. Works even if Rich itself is not yet installed.
# ─────────────────────────────────────────────────────────────────────────────
import importlib.util
import subprocess
import sys
import os

def _bootstrap_dependencies() -> None:
    req_file = os.path.join(os.path.dirname(__file__), "requirements.txt")

    if not os.path.exists(req_file):
        print("[warn] requirements.txt not found — skipping auto-install.")
        return

    with open(req_file) as fh:
        packages = [
            line.strip()
            for line in fh
            if line.strip() and not line.startswith("#")
        ]

    # Map package names to their importable module names where they differ
    _IMPORT_NAME = {
        "gitpython":  "git",
        "networkx":   "networkx",
        "matplotlib": "matplotlib",
        "pytest":     "pytest",
        "rich":       "rich",
        "requests":   "requests",
    }

    missing = []
    for pkg in packages:
        # Strip version specifiers like "rich>=13.0"
        name = pkg.split(">=")[0].split("<=")[0].split("==")[0].split("!=")[0].strip()
        module = _IMPORT_NAME.get(name.lower(), name.lower())
        if importlib.util.find_spec(module) is None:
            missing.append(pkg)

    if not missing:
        return   # everything already installed — fast path

    print("=" * 60)
    print("  Auto-installing missing dependencies…")
    print("=" * 60)
    for pkg in missing:
        print(f"  installing: {pkg}")

    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--quiet", *missing],
    )
    print("  All dependencies installed.\n")

_bootstrap_dependencies()


import re
from collections import defaultdict

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich import print as rprint

from utils import normalize_extension, load_instr_dict

console = Console()


# ─────────────────────────────────────────────────────────────────────────────
# TIER 1 — Instruction Set Parsing
# ─────────────────────────────────────────────────────────────────────────────

def tier1_parser(data: dict) -> tuple[dict, dict, list]:
    """
    Parse instr_dict.json entries.

    Returns
    -------
    ext_to_instrs : dict[str, list[str]]
        Maps each extension tag -> list of instruction mnemonics.
    instr_to_exts : dict[str, list[str]]
        Maps each mnemonic -> list of extension tags it belongs to.
    overlaps : list[tuple[str, list[str]]]
        Instructions that belong to more than one extension.
    """
    ext_to_instrs: dict[str, list] = defaultdict(list)
    instr_to_exts: dict[str, list] = {}
    overlaps: list = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]Parsing instructions…"),
        transient=True,
        console=console,
    ) as progress:
        task = progress.add_task("parse", total=len(data))
        for mnemonic, info in data.items():
            extensions = info.get("extension", [])
            instr_to_exts[mnemonic] = extensions
            for ext in extensions:
                ext_to_instrs[ext].append(mnemonic)
            if len(extensions) > 1:
                overlaps.append((mnemonic, extensions))
            progress.advance(task)

    # ── Summary table ────────────────────────────────────────────────────────
    console.print()
    console.print(Rule("[bold yellow]TIER 1 — EXTENSION SUMMARY[/bold yellow]", style="yellow"))

    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
        border_style="bright_black",
        row_styles=["", "dim"],          # alternating row shading
        expand=False,
        title="[bold]Extension Groups from [cyan]instr_dict.json[/cyan][/bold]",
        title_justify="left",
    )
    table.add_column("Extension", style="cyan", no_wrap=True, min_width=22)
    table.add_column("# Instructions", justify="right", style="green", min_width=14)
    table.add_column("Example Mnemonic", style="bold white", min_width=20)

    for ext in sorted(ext_to_instrs.keys()):
        instrs = ext_to_instrs[ext]
        example = instrs[0].upper() if instrs else "N/A"
        count = str(len(instrs))
        table.add_row(ext, count, f"e.g. [bold]{example}[/bold]")

    console.print(table)

    # ── Stats bar ────────────────────────────────────────────────────────────
    stats = Table.grid(padding=(0, 2))
    stats.add_row(
        f"[bold green]{len(ext_to_instrs)}[/bold green] [dim]extensions[/dim]",
        f"[bold green]{len(instr_to_exts)}[/bold green] [dim]instructions[/dim]",
        f"[bold yellow]{len(overlaps)}[/bold yellow] [dim]multi-extension[/dim]",
    )
    console.print(Panel(stats, title="[bold]Stats[/bold]", border_style="green", expand=False))

    # ── Multi-extension instructions ─────────────────────────────────────────
    if overlaps:
        console.print(
            Rule(
                f"[bold yellow]Instructions in Multiple Extensions "
                f"([green]{len(overlaps)}[/green] total)[/bold yellow]",
                style="yellow",
            )
        )
        ov_table = Table(
            box=box.SIMPLE_HEAVY,
            header_style="bold magenta",
            border_style="bright_black",
            expand=False,
        )
        ov_table.add_column("Mnemonic", style="bold cyan", no_wrap=True, min_width=18)
        ov_table.add_column("Extensions", style="yellow")

        for mnemonic, exts in overlaps[:25]:
            ov_table.add_row(
                mnemonic.upper(),
                "[dim],[/dim] ".join(f"[cyan]{e}[/cyan]" for e in exts),
            )

        if len(overlaps) > 25:
            ov_table.add_row(
                "[dim]…[/dim]",
                f"[dim]and {len(overlaps) - 25} more[/dim]",
            )
        console.print(ov_table)

    return dict(ext_to_instrs), instr_to_exts, overlaps


# ─────────────────────────────────────────────────────────────────────────────
# TIER 2 — Cross-Reference with the ISA Manual
# ─────────────────────────────────────────────────────────────────────────────

def clone_isa_manual(dest: str = "riscv-isa-manual") -> None:
    """Clone the RISC-V ISA manual repository (shallow clone) if not present."""
    if not os.path.exists(dest):
        console.print(f"[bold cyan]Cloning RISC-V ISA Manual[/bold cyan] (shallow) …")
        subprocess.run(
            ["git", "clone", "--depth", "1",
             "https://github.com/riscv/riscv-isa-manual.git", dest],
            check=True,
        )
    else:
        console.print(f"[dim]ISA Manual already present at '{dest}/'.[/dim]")


def find_extensions_in_manual(src_dir: str = "riscv-isa-manual/src") -> set[str]:
    """
    Scan AsciiDoc source files for extension references.

    We search the *original-case* content so that the patterns can catch
    capital letters (M, F, D, …) and mixed-case names (Zba, Zicsr, …).
    Each match is then normalised with normalize_extension().
    """
    extensions: set[str] = set()

    patterns = [
        r'\b(Z[a-zA-Z][a-z0-9]*)\b',
        r'\b(S[a-zA-Z][a-z0-9]*)\b',
        r'\b([MAFDQCVBHJTP])\b',
        r'ext:([a-zA-Z][a-z0-9]*)',
        r'\[\[ext:([a-zA-Z][a-z0-9]+)\]\]',
    ]

    if not os.path.isdir(src_dir):
        console.print(f"[bold red]Warning:[/bold red] manual src directory not found at '{src_dir}'")
        return extensions

    adoc_files = [
        os.path.join(root, fname)
        for root, _, files in os.walk(src_dir)
        for fname in files
        if fname.endswith(".adoc")
    ]

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]Scanning AsciiDoc files…"),
        BarColumn(bar_width=30),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("[dim]{task.completed}/{task.total} files[/dim]"),
        transient=True,
        console=console,
    ) as progress:
        task = progress.add_task("scan", total=len(adoc_files))
        for fpath in adoc_files:
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
                for pattern in patterns:
                    for m in re.findall(pattern, content):
                        norm = normalize_extension(m)
                        if norm:
                            extensions.add(norm)
            except OSError:
                pass
            progress.advance(task)

    return extensions


def tier2_cross_reference(ext_to_instrs: dict) -> tuple[set, set, set]:
    """
    Cross-reference extensions in instr_dict.json with ISA manual mentions.

    Returns
    -------
    matched    : extensions found in both sources
    json_only  : extensions only in instr_dict.json
    manual_only: extensions only in the ISA manual
    """
    console.print()
    console.print(Rule("[bold yellow]TIER 2 — CROSS-REFERENCE WITH ISA MANUAL[/bold yellow]", style="yellow"))

    clone_isa_manual()
    manual_exts = find_extensions_in_manual()

    json_normalized = {normalize_extension(ext) for ext in ext_to_instrs}

    matched = json_normalized & manual_exts
    json_only = json_normalized - manual_exts
    manual_only = manual_exts - json_normalized

    # ── Summary counts ───────────────────────────────────────────────────────
    summary_table = Table(
        box=box.ROUNDED,
        show_header=False,
        border_style="bright_black",
        expand=False,
        title="[bold]Cross-Reference Results[/bold]",
        title_justify="left",
    )
    summary_table.add_column("Label", style="bold white", min_width=38)
    summary_table.add_column("Count", justify="right", min_width=6)

    summary_table.add_row(
        "[bold green]Matched[/bold green] [dim](in both sources)[/dim]",
        f"[bold green]{len(matched)}[/bold green]",
    )
    summary_table.add_row(
        "[bold yellow]Only in instr_dict.json[/bold yellow]",
        f"[bold yellow]{len(json_only)}[/bold yellow]",
    )
    summary_table.add_row(
        "[bold red]Only in ISA Manual[/bold red]",
        f"[bold red]{len(manual_only)}[/bold red]",
    )
    console.print(summary_table)

    # Pretty summary line
    console.print(
        Panel(
            f"[green]{len(matched)} matched[/green]  |  "
            f"[yellow]{len(json_only)} in JSON only[/yellow]  |  "
            f"[red]{len(manual_only)} in manual only[/red]",
            title="[bold]Summary[/bold]",
            border_style="cyan",
            expand=False,
        )
    )

    # ── Detail lists ─────────────────────────────────────────────────────────
    _rich_show_list(
        "Extensions in [cyan]instr_dict.json[/cyan] but [bold red]NOT[/bold red] in ISA Manual",
        json_only,
        color="yellow",
    )
    _rich_show_list(
        "Extensions in ISA Manual but [bold red]NOT[/bold red] in [cyan]instr_dict.json[/cyan]",
        manual_only,
        color="red",
    )

    return matched, json_only, manual_only


def _rich_show_list(title: str, items: set, color: str = "white", limit: int = 20) -> None:
    """Render a sorted set as a Rich panel with bullet items."""
    if not items:
        return

    sorted_items = sorted(items)
    display = sorted_items[:limit]
    remainder = len(items) - limit

    # Build two-column layout from the bullet list
    bullets = [Text(f"  • {item}", style=color) for item in display]
    if remainder > 0:
        bullets.append(Text(f"  … and {remainder} more", style="dim"))

    console.print()
    console.print(
        Panel(
            "\n".join(str(b) for b in bullets),
            title=f"[bold]{title}[/bold] [dim]({len(items)} total)[/dim]",
            border_style=color,
            expand=False,
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
# TIER 3 BONUS — Extension Overlap Graph
# ─────────────────────────────────────────────────────────────────────────────

def generate_overlap_graph(
    ext_to_instrs: dict,
    instr_to_exts: dict,
    output_path: str = "output/extension_overlap_graph.png",
) -> None:
    """
    Build and render a graph where nodes are extensions and an edge connects
    two extensions if they share at least one instruction.

    Requires: networkx, matplotlib
    """
    console.print()
    console.print(Rule("[bold yellow]TIER 3 BONUS — Extension Overlap Graph[/bold yellow]", style="yellow"))

    try:
        import networkx as nx
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        console.print(
            Panel(
                "[yellow]Install [bold]networkx[/bold] + [bold]matplotlib[/bold] to generate the overlap graph.[/yellow]",
                title="[bold]Bonus Graph[/bold]",
                border_style="yellow",
            )
        )
        return

    G = nx.Graph()
    G.add_nodes_from(ext_to_instrs.keys())

    for mnemonic, exts in instr_to_exts.items():
        if len(exts) > 1:
            for i in range(len(exts)):
                for j in range(i + 1, len(exts)):
                    G.add_edge(exts[i], exts[j])

    graph_info = Table.grid(padding=(0, 3))
    graph_info.add_row(
        f"[bold green]{G.number_of_nodes()}[/bold green] [dim]nodes (extensions)[/dim]",
        f"[bold green]{G.number_of_edges()}[/bold green] [dim]edges (shared instructions)[/dim]",
    )
    console.print(Panel(graph_info, title="[bold]Graph Stats[/bold]", border_style="green", expand=False))

    if G.number_of_nodes() == 0:
        console.print("[dim]No nodes — skipping graph render.[/dim]")
        return

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]Rendering graph…"),
        transient=True,
        console=console,
    ) as progress:
        progress.add_task("render", total=None)

        fig, ax = plt.subplots(figsize=(18, 14))
        pos = nx.spring_layout(G, seed=42, k=1.5)
        node_sizes = [300 + 50 * len(ext_to_instrs.get(n, [])) for n in G.nodes()]
        nx.draw_networkx(
            G, pos=pos, ax=ax,
            node_size=node_sizes,
            node_color="#4C72B0",
            font_color="white",
            font_size=7,
            edge_color="#AAAAAA",
            width=0.8,
            with_labels=True,
        )
        ax.set_title("RISC-V Extension Instruction-Overlap Graph", fontsize=14)
        ax.axis("off")
        plt.tight_layout()
        plt.savefig(output_path, dpi=150)
        plt.close()

    console.print(f"[bold green]Graph saved to:[/bold green] [underline]{output_path}[/underline]")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]RISC-V Instruction Set Explorer[/bold cyan]\n"
            "[dim]Tiers 1 · 2 · 3 | github.com/riscv[/dim]",
            border_style="cyan",
            padding=(1, 4),
        )
    )

    # ── Load data ────────────────────────────────────────────────────────────
    DATA_PATH = "data/instr_dict.json"
    try:
        data = load_instr_dict(DATA_PATH)
    except FileNotFoundError:
        console.print(
            Panel(
                f"[bold red]File not found:[/bold red] [yellow]{DATA_PATH}[/yellow]\n\n"
                "Download it from:\n"
                "[underline cyan]https://github.com/rpsene/riscv-extensions-landscape/blob/main/src/instr_dict.json[/underline cyan]",
                title="[bold red]Error[/bold red]",
                border_style="red",
            )
        )
        raise SystemExit(1)

    console.print(
        f"[dim]Loaded [bold green]{len(data)}[/bold green] instructions from "
        f"[cyan]{DATA_PATH}[/cyan][/dim]"
    )

    # ── Tier 1 ───────────────────────────────────────────────────────────────
    ext_to_instrs, instr_to_exts, overlaps = tier1_parser(data)

    # ── Tier 2 ───────────────────────────────────────────────────────────────
    matched, json_only, manual_only = tier2_cross_reference(ext_to_instrs)

    # ── Tier 3 Bonus — Graph ─────────────────────────────────────────────────
    generate_overlap_graph(ext_to_instrs, instr_to_exts)

    console.print()
    console.print(
        Panel(
            "[bold green]All tiers completed successfully![/bold green]",
            border_style="green",
            expand=False,
        )
    )