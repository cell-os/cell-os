import os

from pip.download import PipSession
from pip.req import parse_requirements
from setuptools import setup

here = os.path.abspath(os.path.dirname(__file__))
install_requirements = parse_requirements(
    os.path.join(here, 'requirements.txt'), session=PipSession())
requirements = [str(ir.req) for ir in install_requirements]
version = open(os.path.join(here, 'VERSION')).readlines()[0].strip()

def get_all_files(data_dir):
    data_files = [[os.path.join(root, f) for f in files]
                for root, dirs, files in os.walk(data_dir)]
    data_files = [item.replace(data_dir, '') for l in data_files for item in l]
    return data_files

setup(
    name='cellos',
    version=version,
    author='metal-cell-dev@adobe.com',
    py_modules=['cell'],
    install_requires=requirements,
    include_package_data=True,
    zip_safe=False,
    packages=['', 'deploy', 'config'],
    package_dir={"deploy": "deploy", "config": "config"},
    package_data = {
        '': [ 'cell-os-base.yaml', 'VERSION', 'README.md', 'Dockerfile', 'requirements.txt'],
        'deploy': get_all_files('deploy'),
        'config': get_all_files('config')
    },
    entry_points={
        'console_scripts': [
            'cell=cell:entrypoint',
        ],
    }
)
