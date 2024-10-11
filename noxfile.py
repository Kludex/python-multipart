import nox

nox.needs_version = ">=2024.4.15"
nox.options.default_venv_backend = "uv|virtualenv"

ALL_PYTHONS = [
    c.split()[-1]
    for c in nox.project.load_toml("pyproject.toml")["project"]["classifiers"]
    if c.startswith("Programming Language :: Python :: 3.")
]


@nox.session(python=ALL_PYTHONS)
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
