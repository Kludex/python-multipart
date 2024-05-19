import os
import re
import sys

from invoke import run, task

version_file = os.path.join("multipart", "__init__.py")
version_regex = re.compile(r"((?:\d+)\.(?:\d+)\.(?:\d+))")


# Get around Python 2.X's lack of 'nonlocal' keyword
class g:
    test_success = False


@task
def test(ctx, all=False):
    test_cmd = [
        "pytest",  # Test command
        "--cov-report term-missing",  # Print only uncovered lines to stdout
        "--cov-config pyproject.toml",  # Use this file for configuration
        "--cov multipart",  # Test only this module
        "--timeout=30",  # Each test should timeout after 30 sec
    ]

    # Test in this directory
    test_cmd.append("tests")

    # Run the command.
    # TODO: why does this fail with pty=True?
    res = run(" ".join(test_cmd), pty=False)
    g.test_success = res.ok


@task(pre=[test])
def deploy(ctx):
    if not g.test_success:
        print("Tests must pass before deploying!", file=sys.stderr)
        return

    # # Build source distribution and wheel
    run("hatch build")
    #
    # # Upload distributions from last step to pypi
    run("hatch publish")
