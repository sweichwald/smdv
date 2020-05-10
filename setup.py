import os
from setuptools import setup


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def parse_requirements_file(filename):
    with open(filename) as f:
        return f.read().splitlines()


if __name__ == "__main__":
    install_requires = parse_requirements_file("requirements.txt")

    with open(os.path.join(BASE_DIR, "README.md")) as f:
        long_description = f.read()

    setup(
        name="pmpm",
        version="0.1.2",
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
        packages=['pmpm'],
        include_package_data=True,
        data_files=[
            "pmpm/pmpm.html",
            "pmpm/pmpm.css",
        ]
    )
