#!/usr/bin/env python3
"""
Test dialogue prompts against all news files.

Usage:
    python test_prompts.py                        # Run all prompts
    python test_prompts.py -p prompt-1            # Test only prompt-1
    python test_prompts.py -p prompt-1 prompt-2   # Test specific prompts
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from generate_dialogue import generate_dialogue


def filter_files(files: list[Path], patterns: list[str] | None) -> list[Path]:
    """Filter files by name patterns. If patterns is None, return all files."""
    if not patterns:
        return files

    filtered = []
    for f in files:
        for pattern in patterns:
            if pattern in f.stem or f.stem == pattern:
                filtered.append(f)
                break
    return filtered


def run_tests(
    prompts_dir: Path,
    news_dir: Path,
    output_dir: Path,
    model: str = "gpt-4o",
    prompt_filter: list[str] | None = None,
) -> dict:
    """Run selected prompts against all news files."""

    # Find all prompts and news files
    all_prompts = sorted(prompts_dir.glob("*.md"))
    news_files = sorted(news_dir.glob("*.json"))

    # Apply prompt filter
    prompts = filter_files(all_prompts, prompt_filter)

    if not prompts:
        if prompt_filter:
            print(f"Error: No prompts matching {prompt_filter} in {prompts_dir}", file=sys.stderr)
        else:
            print(f"Error: No prompt files found in {prompts_dir}", file=sys.stderr)
        sys.exit(1)

    if not news_files:
        print(f"Error: No news files found in {news_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Testing {len(prompts)} prompts × {len(news_files)} news files", file=sys.stderr)
    if prompt_filter:
        print(f"  Selected prompts: {[p.stem for p in prompts]}", file=sys.stderr)
    print(f"Running {len(prompts) * len(news_files)} test combinations...\n", file=sys.stderr)

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "prompts": [p.name for p in prompts],
        "news_files": [n.name for n in news_files],
        "tests": [],
    }

    test_num = 0
    total_tests = len(prompts) * len(news_files)

    for prompt_path in prompts:
        for news_path in news_files:
            test_num += 1
            prompt_name = prompt_path.stem
            news_name = news_path.stem
            output_name = f"{prompt_name}_{news_name}.json"
            output_path = output_dir / output_name

            print(f"[{test_num}/{total_tests}] {prompt_name} × {news_name}", file=sys.stderr)

            test_result = {
                "prompt": prompt_name,
                "news": news_name,
                "output_file": output_name,
                "success": False,
                "error": None,
            }

            try:
                # Generate dialogue
                dialogue_data = generate_dialogue(news_path, prompt_path, model)

                # Save result
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(dialogue_data, f, ensure_ascii=False, indent=2)

                test_result["success"] = True
                test_result["segments_count"] = len(dialogue_data.get("dialogue", []))
                print(f"    ✓ Saved to {output_path}", file=sys.stderr)

            except Exception as e:
                test_result["error"] = str(e)
                print(f"    ✗ Error: {e}", file=sys.stderr)

            results["tests"].append(test_result)

    # Summary
    successful = sum(1 for t in results["tests"] if t["success"])
    print(f"\n{'='*50}", file=sys.stderr)
    print(f"Results: {successful}/{total_tests} tests passed", file=sys.stderr)

    # Save summary
    summary_path = output_dir / "_test_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Summary saved to: {summary_path}", file=sys.stderr)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Test dialogue prompts against all news files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_prompts.py                           # Run all prompts
  python test_prompts.py -p prompt-1               # Test only prompt-1
  python test_prompts.py -p prompt-1 prompt-2      # Test specific prompts
"""
    )
    parser.add_argument(
        "-p", "--prompt", nargs="+", dest="prompt_filter",
        help="Select prompts by name (can specify multiple)"
    )
    parser.add_argument(
        "--prompts-dir", type=Path, default=Path("data/dialogue-prompt"),
        help="Directory containing prompt .md files"
    )
    parser.add_argument(
        "--news-dir", type=Path, default=Path("data/news-storage"),
        help="Directory containing news .json files"
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("output/prompt-test-results"),
        help="Output directory for test results"
    )
    parser.add_argument(
        "-m", "--model", default="gpt-4o",
        help="OpenAI model to use (default: gpt-4o)"
    )

    args = parser.parse_args()

    if not args.prompts_dir.exists():
        print(f"Error: Prompts directory not found: {args.prompts_dir}", file=sys.stderr)
        sys.exit(1)

    if not args.news_dir.exists():
        print(f"Error: News directory not found: {args.news_dir}", file=sys.stderr)
        sys.exit(1)

    run_tests(
        args.prompts_dir,
        args.news_dir,
        args.output,
        args.model,
        args.prompt_filter,
    )


if __name__ == "__main__":
    main()
