from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

from blueline import __version__ as version

setup(
    name="blueline",
    version=version,
    description="ERPNext customisation for Blueline Enterprises & General Innovations (Sri Lanka)",
    author="NovixCore — Sohail Zafar",
    author_email="novixcore@gmail.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
