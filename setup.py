from setuptools import setup, find_packages
from setuptools.command.install import install

from sys import path

path.insert(0, './')

from mentat import __version__

class PostInstallCommand(install):
    """Post-installation for installation mode."""
    def run(self):
        install.run(self)

setup(
    name='mentat',
    packages=['mentat'],
    package_data={'mentat': ['py.typed']},
    version=__version__,
    description='HUB / Router / Conductor for OSC / MIDI capable softwares',
    url='https://github.com/jean-emmanuel/mentat',
    author='Jean-Emmanuel Doucet',
    classifiers=[
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)'
    ],
    python_requires='>=3',
    install_requires=[],
    cmdclass={
        'install': PostInstallCommand,
    }
)
