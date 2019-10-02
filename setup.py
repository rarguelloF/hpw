# -*- coding: utf-8 -*-

from setuptools import find_packages
from setuptools import setup

setup(
    name='hpw',
    version='0.1.0',
    description='hpw is a command line utility for running and retrying any command using HTTP proxies',
    author='Rodrigo Argüello Flores',
    author_email='rarguellof91@gmail.com',
    packages=find_packages(),
    install_requires=[
        'requests',
        'requests-html',
    ],
    entry_points={
        'console_scripts': [
            'hpw = http_proxy_wrapper:main',
        ],
    },
)
