import inspect

import nox

nox.needs_version = ">=2024.4.15"
nox.options.default_venv_backend = "uv|virtualenv"


@nox.session
def rename(session: nox.Session) -> None:
    session.install(".")
    assert "import python_multipart" in session.run("python", "-c", "import multipart", silent=True)
    assert "import python_multipart" in session.run("python", "-c", "import multipart.exceptions", silent=True)
    assert "import python_multipart" in session.run("python", "-c", "from multipart import exceptions", silent=True)
    assert "import python_multipart" in session.run(
        "python", "-c", "from multipart.exceptions import FormParserError", silent=True
    )

    session.install("multipart")
    assert "import python_multipart" not in session.run(
        "python", "-c", "import multipart; multipart.parse_form_data", silent=True
    )
    assert "import python_multipart" not in session.run(
        "python", "-c", "import python_multipart; python_multipart.parse_form", silent=True
    )


@nox.session
def rename_inline(session: nox.Session) -> None:
    session.install("pip")
    res = session.run(
        "python",
        "-c",
        inspect.cleandoc("""
        import subprocess

        subprocess.run(["pip", "install", "."])

        import multipart
    """),
        silent=True,
    )
    assert "FutureWarning: Please use `import python_multipart` instead." in res
