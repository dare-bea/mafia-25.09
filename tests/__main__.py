import logging
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from sys import argv, stderr, stdout
from sys import exit as sys_exit
from traceback import print_exception

from __init__ import TESTS, logger  # type: ignore[import-not-found]

logger.addHandler(logging.StreamHandler(stderr))

def main() -> int:
    verbose = "--verbose" in argv or "-v" in argv
    mypy_abort_if_error = "--mypy-abort" in argv or "-ma" in argv
    mypy_verbose = "--mypy-verbose" in argv or "-mv" in argv
    use_mypy = "--mypy" in argv or "-m" in argv or mypy_abort_if_error or mypy_verbose
    mypy_verbose = mypy_verbose or verbose
    if "--all" in argv or "-a" in argv:
        verbose = True
        use_mypy = True
        mypy_verbose = True
    if (
        "-mav" in argv
        or "-mva" in argv
        or "--mypy-abort-verbose" in argv
        or "--mypy-verbose-abort" in argv
    ):
        use_mypy = True
        mypy_verbose = True
        mypy_abort_if_error = True

    successes: int = 0
    failed_tests: list[str] = []
    directory = Path(__file__).parent
    for test_name, test_func in TESTS.items():
        log_path = directory / f"{test_name}.log"
        if verbose:
            print(f"## TESTING: {test_name}() ##")
        try:
            with log_path.open("w") as f, redirect_stdout(f), redirect_stderr(f):
                test_func()
        except Exception as e:  # noqa: BLE001
            if verbose:
                with log_path.open() as f:
                    print(f.read())
                print_exception(e)
            with log_path.open("a") as f:
                print_exception(e, file=f)
            print(f"## TEST {test_name} FAILED ##")
            failed_tests.append(test_name)
        else:
            if verbose:
                with log_path.open() as f:
                    print(f.read())
            print(f"## TEST {test_name} PASSED ##")
            successes += 1
        if verbose:
            print()

    print(f"{successes}/{len(TESTS)} tests succeeded! ({successes / len(TESTS):.1%})")
    if failed_tests:
        print("Failed tests:", file=stderr)
        for test_name in failed_tests:
            print(f"    {test_name}", file=stderr)
    print()

    if use_mypy:
        try:
            import mypy.api  # noqa: PLC0415  # type: ignore[import-not-found]
        except ImportError:
            print("Could not find module 'mypy.api'. Skipping type-checking...")
        else:
            for x in range(11, 15):
                print(f"Type-checking Python 3.{x}:")
                result = mypy.api.run(
                    [
                        "--python-version",
                        f"3.{x}",
                        "--strict",
                        "--pretty",
                        str(directory),
                    ]
                    if mypy_verbose
                    else [
                        "--python-version",
                        f"3.{x}",
                        "--strict",
                        "--no-pretty",
                        str(directory),
                    ],
                )
                if result[0]:
                    print(result[0].rstrip(), file=stdout)

                if result[1]:
                    print(result[1].rstrip(), file=stderr)

                if result[2] and mypy_abort_if_error:
                    print("Type-checking failed.")
                    return 1

    if successes != len(TESTS):
        return 1
    return 0


if __name__ == "__main__":
    sys_exit(main())
