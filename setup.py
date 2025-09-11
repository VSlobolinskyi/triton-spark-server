# Create a simple setup.py file
with open("setup.py", "w") as f:
    f.write("""
from setuptools import setup, find_packages

setup(
    name="sparktts",
    version="0.1.0",
    packages=find_packages(),
)
""")