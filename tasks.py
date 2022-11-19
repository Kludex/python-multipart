import os
import re
import sys

from invoke import task, run


version_file = os.path.join('multipart', '__init__.py')
version_regex = re.compile(r'((?:\d+)\.(?:\d+)\.(?:\d+))')

# Get around Python 2.X's lack of 'nonlocal' keyword
class g:
    test_success = False


@task
def test(ctx, all=False):
    test_cmd = [
        'pytest',                       # Test command
        '--cov-report term-missing',    # Print only uncovered lines to stdout
        '--cov-config .coveragerc',     # Use this file for configuration
        '--cov multipart',              # Test only this module
        '--timeout=30'                  # Each test should timeout after 30 sec
    ]

    # Default to not running the slow tests.
    if not all:
        test_cmd.append('-m "not slow_test"')

    # Test in this directory
    test_cmd.append(os.path.join("multipart", "tests"))

    # Run the command.
    # TODO: why does this fail with pty=True?
    res = run(' '.join(test_cmd), pty=False)
    g.test_success = res.ok


@task
def bump(ctx, type):
    # Read and parse version.
    with open(version_file, 'r') as f:
        file_data = f.read().replace('\r\n', '\n')

    m = version_regex.search(file_data)
    if m is None:
        print(f"Could not find version in '{version_file}'!", file=sys.stderr)
        return

    version = m.group(0)
    before = file_data[0:m.start(0)]
    after = file_data[m.end(0):]

    # Bump properly.
    ver_nums = [int(x) for x in version.split('.')]

    if type == 'patch':
        ver_nums[2] += 1
    elif type == 'minor':
        ver_nums[1] += 1
    elif type == 'major':
        ver_nums[0] += 1
    else:
        print(f"Invalid version type: '{type}'", file=sys.stderr)
        return

    # Construct new data and write to file.
    new_ver = ".".join(str(x) for x in ver_nums)
    new_data = before + new_ver + after

    with open(version_file, 'w') as f:
        f.write(new_data)

    # Print information.
    print(f"Bumped version from: {version} --> {new_ver}")


@task(pre=[test])
def deploy(ctx):
    if not g.test_success:
        print("Tests must pass before deploying!", file=sys.stderr)
        return

    # # Build source distribution and wheel
    run('hatch build')
    #
    # # Upload distributions from last step to pypi
    run('hatch publish')
