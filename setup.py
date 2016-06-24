import os

from pip.download import PipSession
from pip.req import parse_requirements
from setuptools import setup

here = os.path.abspath(os.path.dirname(__file__))
install_requirements = parse_requirements(
    os.path.join(here, 'requirements.txt'), session=PipSession())
requirements = [str(ir.req) for ir in install_requirements]
version = open(os.path.join(here, 'VERSION')).readlines()[0].strip()

data_dir = 'deploy/'
data_files = [[os.path.join(root, f) for f in files]
              for root, dirs, files in os.walk(data_dir)]
data_files = [item.replace(data_dir, '') for l in data_files for item in l]
data_files.append("../cell-os-base.yaml")

setup(
    name='cellos',
    version=version,
    author='metal-cell-dev@adobe.com',
    py_modules=['cell'],
    packages=['deploy'],
    install_requires=requirements,
    package_data={'deploy': data_files},
    include_package_data=True,
    exclude_package_data={'deploy': ['aws/build*']},
    entry_points={
        'console_scripts': [
            'cell=cell:main',
        ],
    }
)
