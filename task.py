import subprocess
import sys


def run_command(args: list[str]) -> int:
    """Run a command and print output."""
    print(f"Running: {' '.join(args)}")
    try:
        result = subprocess.run(args, check=False)
        return result.returncode
    except Exception as e:
        print(f"Failed to execute {' '.join(args)}: {e}", file=sys.stderr)
        return 1


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: uv run task {format,lint,typecheck,ci}", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]
    exit_code = 0

    if command == "format":
        exit_code = run_command(["ruff", "format", "."])
    elif command == "lint":
        exit_code = run_command(["ruff", "check", "."])
    elif command == "typecheck":
        exit_code = run_command(["mypy", "."])
    elif command == "ci":
        print("=== Running CI Pipeline (Format, Lint, Typecheck) ===")
        fmt_res = run_command(["ruff", "format", "."])
        lint_res = run_command(["ruff", "check", "."])
        type_res = run_command(["mypy", "."])

        if fmt_res != 0 or lint_res != 0 or type_res != 0:
            print("\nCI Pipeline FAILED!", file=sys.stderr)
            exit_code = 1
        else:
            print("\nCI Pipeline PASSED!")
    else:
        print(f"Unknown command: {command}. Expected format, lint, typecheck, or ci.", file=sys.stderr)
        sys.exit(1)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
