#!/usr/bin/env python3
"""
Build benchmark dashboard charts from a results JSON.

Currently generates two charts:
  1. Cost per Prompt   (cost_usd)
  2. Duration per Prompt (elapsed_seconds)

Both charts are fully data-driven: tools, prompts, and ordering are all
derived from the JSON at runtime. Adding a new tool to the benchmark data
is enough for it to appear in the charts — no edits to this script required.

USAGE
-----
    python3 tools/build_chart.py evaluations/2026-06-23/run-average.json
    python3 tools/build_chart.py <input.json> --output-dir ./charts
    python3 tools/build_chart.py <input.json> --title-prefix "June 23"

By default PNGs are written next to the input JSON as:
  - cost-per-prompt.png
  - duration-per-prompt.png

Tools with no data for a given prompt are drawn as zero-height bars
labelled "N/A". A tool is omitted entirely only if it has no data for ANY
prompt in that metric.

Run from the repo root. Requires Python 3.8+ and matplotlib.
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import matplotlib

    matplotlib.use("Agg")  # headless / no display required
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter
except ImportError:
    sys.exit(
        "matplotlib is required. Install it with:\n"
        "    python3 -m pip install matplotlib"
    )


# A colour-blind-friendly palette (Tableau 10). Tools are assigned colours by
# their order of appearance in the data, so any number of tools is supported.
PALETTE = [
    "#1f77b4",  # blue
    "#2ca02c",  # green
    "#ff7f0e",  # orange
    "#9467bd",  # purple
    "#d62728",  # red
    "#17becf",  # cyan
    "#8c564b",  # brown
    "#e377c2",  # pink
    "#7f7f7f",  # grey
    "#bcbd22",  # olive
]


def load_data(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        sys.exit(f"Input file not found: {path}")
    except json.JSONDecodeError as exc:
        sys.exit(f"Could not parse JSON in {path}: {exc}")


def extract_metric(data: dict, metric_key: str):
    """Return (prompts, tools, values) for a given metric key.

    prompts : ordered list of evaluation ids
    tools   : ordered list of tool names that have at least one value
    values  : dict[tool][prompt] -> float | None
    """
    results = data.get("results", [])
    if not results:
        sys.exit("No 'results' array found in the input JSON.")

    # Preserve first-seen order for both prompts and tools.
    prompts, tools = [], []
    values = {}

    for row in results:
        prompt = row.get("evaluation_id")
        tool = row.get("tool")
        if prompt is None or tool is None:
            continue
        if prompt not in prompts:
            prompts.append(prompt)
        if tool not in tools:
            tools.append(tool)
        values.setdefault(tool, {})[prompt] = row.get(metric_key)

    # If the JSON declares an evaluation order, honour it.
    declared = [e.get("id") for e in data.get("evaluations", []) if e.get("id")]
    if declared:
        ordered = [p for p in declared if p in prompts]
        ordered += [p for p in prompts if p not in ordered]
        prompts = ordered

    # Drop tools that have no data for any prompt (for this metric).
    tools = [
        t
        for t in tools
        if any(values.get(t, {}).get(p) is not None for p in prompts)
    ]

    return prompts, tools, values


def build_chart(
    prompts,
    tools,
    values,
    title: str,
    y_label: str,
    value_fmt: str,
    y_axis_fmt,
    output: Path,
):
    """Render and save a grouped bar chart."""
    n_tools = len(tools)
    n_prompts = len(prompts)

    group_width = 0.8
    bar_width = group_width / n_tools
    x = list(range(n_prompts))

    fig, ax = plt.subplots(figsize=(max(8, 2.2 * n_prompts), 6))

    max_val = 0.0
    for i, tool in enumerate(tools):
        colour = PALETTE[i % len(PALETTE)]
        offsets = [xi - group_width / 2 + bar_width * (i + 0.5) for xi in x]
        bar_values = []
        for p in prompts:
            c = values.get(tool, {}).get(p)
            bar_values.append(c if c is not None else 0.0)
            if c is not None:
                max_val = max(max_val, c)

        bars = ax.bar(offsets, bar_values, bar_width, label=tool, color=colour)

        # Value labels above each bar; "N/A" where there is no data.
        for bar, p in zip(bars, prompts):
            c = values.get(tool, {}).get(p)
            label = "N/A" if c is None else value_fmt.format(c)
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                label,
                ha="center",
                va="bottom",
                fontsize=8,
                rotation=0,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(prompts)
    ax.set_xlabel("Prompt")
    ax.set_ylabel(y_label)
    ax.set_title(title)

    # Headroom for the value labels.
    ax.set_ylim(0, max_val * 1.18 if max_val > 0 else 1)
    ax.yaxis.set_major_formatter(y_axis_fmt)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left")

    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Chart definitions — add new metrics here and they'll be generated.
# ---------------------------------------------------------------------------

CHARTS = [
    {
        "metric_key": "cost_usd",
        "filename": "cost-per-prompt.png",
        "title_suffix": "Cost per Prompt",
        "y_label": "Cost (USD)",
        "value_fmt": "${:.4f}",
        "y_axis_fmt": FuncFormatter(lambda v, _: f"${v:.2f}"),
    },
    {
        "metric_key": "elapsed_seconds",
        "filename": "duration-per-prompt.png",
        "title_suffix": "Duration per Prompt",
        "y_label": "Duration (seconds)",
        "value_fmt": "{:.1f}s",
        "y_axis_fmt": FuncFormatter(lambda v, _: f"{v:.0f}s"),
    },
]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build benchmark dashboard charts from a results JSON."
    )
    parser.add_argument("input", type=Path, help="Path to a run-*.json file.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for output PNGs (default: same dir as input).",
    )
    parser.add_argument(
        "--title-prefix",
        default="AI Coding Tools Benchmark",
        help="Prefix for chart titles.",
    )
    args = parser.parse_args(argv)

    data = load_data(args.input)
    output_dir = args.output_dir or args.input.parent

    generated = []
    for chart in CHARTS:
        prompts, tools, values = extract_metric(data, chart["metric_key"])
        if not tools:
            print(
                f"Skipping {chart['filename']}: no data for metric "
                f"'{chart['metric_key']}'."
            )
            continue

        title = f"{args.title_prefix} \u2014 {chart['title_suffix']}"
        output = output_dir / chart["filename"]

        build_chart(
            prompts,
            tools,
            values,
            title,
            chart["y_label"],
            chart["value_fmt"],
            chart["y_axis_fmt"],
            output,
        )

        missing = [
            (t, p)
            for t in tools
            for p in prompts
            if values.get(t, {}).get(p) is None
        ]
        generated.append(output)
        print(f"✓ {output}")
        print(f"  Tools   : {', '.join(tools)}")
        print(f"  Prompts : {', '.join(prompts)}")
        if missing:
            na = ", ".join(f"{t}/{p}" for t, p in missing)
            print(f"  N/A     : {na}")

    if not generated:
        sys.exit("No charts generated — check the input data.")
    print(f"\n{len(generated)} chart(s) written.")


if __name__ == "__main__":
    main()
