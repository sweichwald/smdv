from pathlib import Path
from setuptools import setup


BASE_DIR = Path(__file__).parent


def parse_requirements_file(filename):
    with Path(BASE_DIR / filename).open('r') as f:
        return f.read().splitlines()


if __name__ == "__main__":
    install_requires = parse_requirements_file("requirements.txt")

    with Path(BASE_DIR / 'README.md').open('r') as f:
        long_description = f.read()

    setup(
        name="pmpm",
        version="0.1.3",
        description=("pmpm: pandoc markdown preview machine, "
                     "a simple markdown previewer"),
        long_description=long_description,
        long_description_content_type="text/markdown",
        url="https://github.com/sweichwald/pmpm",
        license="GPLv3",
        entry_points={"console_scripts": [
            "pmpm = pmpm.pmpm:main",
            "pmpm-websocket = pmpm.websocket:run_websocket_server"]},
        python_requires=">=3.6",
        install_requires=install_requires,
        classifiers=[
            "Topic :: Utilities",
            "Intended Audience :: End Users/Desktop",
            "Intended Audience :: Developers",
            "Programming Language :: Python :: 3",
            "Operating System :: POSIX :: Linux",
            "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        ],
        packages=['pmpm', 'client'],
        include_package_data=True,
    )
