#!/usr/bin/env python3
"""
Test dialogue prompts against news seeds.

Usage:
    python test_prompts.py                        # Run all prompts
    python test_prompts.py -p prompt-5            # Test only prompt-5
    python test_prompts.py -s seed-1 seed-2       # Test specific seeds
    python test_prompts.py --no-refine            # Skip refinement step
"""

import argparse
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from generate_dialogue import generate_dialogue, refine_dialogue
from perplexity_search import run_perplexity_enrichment

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_REFINE_PROMPT = PROJECT_ROOT / "data" / "dialogue-prompt" / "prompt-5-step-2.md"


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


def enrich_seed(seed_path: Path, output_path: Path) -> dict:
    """Convert a seed file to enriched news data via Perplexity."""
    run_perplexity_enrichment(input_path=seed_path, output_path=output_path)
    with open(output_path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_tests(
    prompts_dir: Path,
    seeds_dir: Path,
    output_dir: Path,
    model: str = "gpt-4o",
    prompt_filter: list[str] | None = None,
    seed_filter: list[str] | None = None,
    refine: bool = True,
    refine_prompt: Path = DEFAULT_REFINE_PROMPT,
) -> dict:
    """Run selected prompts against news seeds with optional refinement."""

    # Find all prompts and seed files
    all_prompts = sorted(prompts_dir.glob("*.md"))
    # Exclude step-2 refinement prompts from main prompt list
    all_prompts = [p for p in all_prompts if "step-2" not in p.stem]
    all_seeds = sorted(seeds_dir.glob("*.json"))

    # Apply filters
    prompts = filter_files(all_prompts, prompt_filter)
    seeds = filter_files(all_seeds, seed_filter)

    if not prompts:
        if prompt_filter:
            print(f"Error: No prompts matching {prompt_filter} in {prompts_dir}", file=sys.stderr)
        else:
            print(f"Error: No prompt files found in {prompts_dir}", file=sys.stderr)
        sys.exit(1)

    if not seeds:
        if seed_filter:
            print(f"Error: No seeds matching {seed_filter} in {seeds_dir}", file=sys.stderr)
        else:
            print(f"Error: No seed files found in {seeds_dir}", file=sys.stderr)
        sys.exit(1)

    mode = "generate + refine" if refine else "generate only"
    print(f"Testing {len(prompts)} prompts × {len(seeds)} seeds ({mode})", file=sys.stderr)
    if prompt_filter:
        print(f"  Selected prompts: {[p.stem for p in prompts]}", file=sys.stderr)
    if seed_filter:
        print(f"  Selected seeds: {[s.stem for s in seeds]}", file=sys.stderr)
    print(f"Running {len(prompts) * len(seeds)} test combinations...\n", file=sys.stderr)

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "refine": refine,
        "prompts": [p.name for p in prompts],
        "seeds": [s.name for s in seeds],
        "tests": [],
    }

    test_num = 0
    total_tests = len(prompts) * len(seeds)

    # Cache enriched news data per seed
    enriched_cache: dict[str, dict] = {}

    for prompt_path in prompts:
        for seed_path in seeds:
            test_num += 1
            prompt_name = prompt_path.stem
            seed_name = seed_path.stem
            output_name = f"{prompt_name}_{seed_name}.json"
            output_path = output_dir / output_name

            print(f"[{test_num}/{total_tests}] {prompt_name} × {seed_name}", file=sys.stderr)

            test_result = {
                "prompt": prompt_name,
                "seed": seed_name,
                "output_file": output_name,
                "success": False,
                "error": None,
                "refined": refine,
            }

            try:
                # Get enriched news data (cached per seed)
                if seed_name not in enriched_cache:
                    print(f"    Enriching seed via Perplexity...", file=sys.stderr)
                    enriched_path = output_dir / f"_enriched_{seed_name}.json"
                    enriched_cache[seed_name] = enrich_seed(seed_path, enriched_path)

                news_data = enriched_cache[seed_name]

                # Step 1: Generate dialogue
                print(f"    Generating dialogue...", file=sys.stderr)
                dialogue_data = generate_dialogue(news_data, prompt_path, model)

                # Step 2: Refine dialogue (optional)
                if refine:
                    print(f"    Refining dialogue...", file=sys.stderr)
                    # Save pre-refinement version
                    pre_refine_path = output_dir / f"{prompt_name}_{seed_name}_pre_refine.json"
                    with open(pre_refine_path, "w", encoding="utf-8") as f:
                        json.dump(dialogue_data, f, ensure_ascii=False, indent=2)

                    dialogue_data = refine_dialogue(dialogue_data, news_data, refine_prompt, model)

                # Save final result
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(dialogue_data, f, ensure_ascii=False, indent=2)

                test_result["success"] = True
                test_result["script_count"] = len(dialogue_data.get("script", []))
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
        description="Test dialogue prompts against news seeds",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_prompts.py                           # Run all prompts × all seeds
  python test_prompts.py -p prompt-5               # Test only prompt-5
  python test_prompts.py -s seed-1 seed-2          # Test specific seeds
  python test_prompts.py --no-refine               # Skip refinement step
  python test_prompts.py -p prompt-5 -s seed-1     # Single combination
"""
    )
    parser.add_argument(
        "-p", "--prompt", nargs="+", dest="prompt_filter",
        help="Select prompts by name (can specify multiple)"
    )
    parser.add_argument(
        "-s", "--seed", nargs="+", dest="seed_filter",
        help="Select seeds by name (can specify multiple)"
    )
    parser.add_argument(
        "--prompts-dir", type=Path, default=Path("data/dialogue-prompt"),
        help="Directory containing prompt .md files"
    )
    parser.add_argument(
        "--seeds-dir", type=Path, default=Path("data/news-seeds"),
        help="Directory containing seed .json files"
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("output/prompt-test-results"),
        help="Output directory for test results"
    )
    parser.add_argument(
        "-m", "--model", default="gpt-4o",
        help="OpenAI model to use (default: gpt-4o)"
    )
    parser.add_argument(
        "--no-refine", action="store_true",
        help="Skip the refinement step (generate only)"
    )
    parser.add_argument(
        "--refine-prompt", type=Path, default=DEFAULT_REFINE_PROMPT,
        help="Path to refinement prompt (default: prompt-5-step-2.md)"
    )

    args = parser.parse_args()

    if not args.prompts_dir.exists():
        print(f"Error: Prompts directory not found: {args.prompts_dir}", file=sys.stderr)
        sys.exit(1)

    if not args.seeds_dir.exists():
        print(f"Error: Seeds directory not found: {args.seeds_dir}", file=sys.stderr)
        sys.exit(1)

    run_tests(
        args.prompts_dir,
        args.seeds_dir,
        args.output,
        args.model,
        args.prompt_filter,
        args.seed_filter,
        refine=not args.no_refine,
        refine_prompt=args.refine_prompt,
    )


if __name__ == "__main__":
    main()
