from setuptools import setup, find_packages

setup(
    name="globaler",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[],
    author="Your Name",
    author_email="your.email@example.com",
    description="A package to create and manage a global timer",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/zejia-lin/globaler",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.8',
    requires=["pandas"]
)